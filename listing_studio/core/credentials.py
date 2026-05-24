"""OAuth credential storage.

Strategy: try the OS keyring first (Windows Credential Manager / macOS
Keychain / Linux Secret Service). If that fails - most commonly Windows
WinError 1783 "The stub received bad data" raised when the blob exceeds
~2560 bytes - fall back to a file under ``%LOCALAPPDATA%\\ListingStudio\\
credentials\\``. Files there inherit the user-only ACL Windows applies to
LOCALAPPDATA, so the security model is the same as keyring for a personal
single-user install.

For each platform we store one JSON blob containing access_token,
refresh_token, expires_at, and any platform-specific metadata. The blob
format is intentionally flexible because the platforms have different
token shapes. Blobs are gzip+base64 encoded before storage to keep small
ones inside the keyring limit when possible.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import keyring
import keyring.errors

from listing_studio.config import settings
from listing_studio.core.models import Platform

logger = logging.getLogger(__name__)


# Windows Credential Manager has a ~2560 byte limit on credential blob values
# (raised as WinError 1783 "The stub received bad data" when exceeded). eBay's
# OAuth user_access_token + user_refresh_token together easily exceed this -
# refresh tokens alone can be 2-3 KB. We compress every blob before storing
# so the encoded value stays well under the limit. On load, we transparently
# decompress; entries from older app versions (no prefix) keep working.
_GZIP_PREFIX = "gz:"


def _serialize(payload: dict[str, Any]) -> str:
    """JSON-encode + gzip + base64 the payload for keyring storage.

    Gzip cuts eBay's token blob to ~30% of original size, well under the
    Windows Credential Manager limit. The "gz:" prefix lets load_credentials
    distinguish compressed payloads from older plain-JSON entries.
    """
    raw = json.dumps(payload, default=str).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    return _GZIP_PREFIX + base64.b64encode(compressed).decode("ascii")


def _deserialize(stored: str) -> dict[str, Any] | None:
    """Inverse of _serialize. Handles both new (gz:) and legacy (plain JSON)."""
    if stored.startswith(_GZIP_PREFIX):
        try:
            compressed = base64.b64decode(stored[len(_GZIP_PREFIX):])
            raw = gzip.decompress(compressed)
            return json.loads(raw)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not decode compressed credentials: %s", exc)
            return None
    # Backward compatibility: anything stored before we introduced
    # compression is plain JSON.
    try:
        return json.loads(stored)
    except json.JSONDecodeError:
        return None


def _key_for(platform: Platform) -> str:
    """Build the keyring "username" used to identify a platform's credentials."""
    return f"oauth_token::{platform.value}"


def _service_key_for(service_name: str) -> str:
    """Build the keyring "username" for a non-platform service credential.

    Used for things like image-host API keys (ImgBB, Cloudinary) that aren't
    marketplace platforms but still belong in the OS credential store rather
    than the SQLite DB.

    Uses a distinct prefix from the platform scheme so the two namespaces
    can't collide (e.g. a hypothetical platform named "imgbb" would key as
    ``oauth_token::imgbb`` while the image host keys as ``service::imgbb``).
    """
    return f"service::{service_name}"


_keyring_warned = False


# ---------------------------------------------------------------------------
# File-based storage fallback
# ---------------------------------------------------------------------------
#
# Used when the OS keyring rejects the write (most common cause: Windows's
# 2560-byte limit on credential values, raised as WinError 1783). One file
# per credential name under <data_dir>/credentials/. On Windows the parent
# data dir is %LOCALAPPDATA%/ListingStudio/ which inherits user-only ACLs.


def _credentials_dir() -> Path:
    d = settings.data_dir / "credentials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path_for(name: str) -> Path:
    # The keyring "username" can contain characters that aren't safe for
    # filesystem paths (colons, slashes). Replace them with underscores
    # so the path is portable.
    safe = name.replace("::", "__").replace(":", "_").replace("/", "_")
    return _credentials_dir() / f"{safe}.cred"


def _write_file_credentials(name: str, serialized: str) -> None:
    path = _file_path_for(name)
    path.write_text(serialized, encoding="utf-8")


def _read_file_credentials(name: str) -> str | None:
    path = _file_path_for(name)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Couldn't read credentials file %s: %s", path, exc)
        return None


def _delete_file_credentials(name: str) -> None:
    path = _file_path_for(name)
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Couldn't delete credentials file %s: %s", path, exc)


def _store_with_fallback(name: str, serialized: str) -> None:
    """Try keyring first; on ANY failure fall back to file storage.

    The keyring path is preferred when it works (OS-level encryption on
    Windows/macOS), but when it doesn't - notably for eBay's chunky OAuth
    tokens that exceed Windows's 2560-byte CredentialBlob limit - we land
    on a file in the user's LOCALAPPDATA. Files there have the same
    user-only ACL as the rest of the app's data; no extra exposure for a
    single-user desktop install.
    """
    try:
        keyring.set_password(settings.keyring_service, name, serialized)
        # Keyring write worked - clean up any old file fallback so we
        # don't have two sources of truth.
        _delete_file_credentials(name)
        return
    except Exception as exc:  # noqa: BLE001 - any keyring failure triggers file fallback
        logger.info(
            "Keyring write failed for %s (%s: %s); falling back to file storage.",
            name, type(exc).__name__, exc,
        )

    # Fallback path
    try:
        _write_file_credentials(name, serialized)
        # Try to clean up any partial/stale keyring entry too
        try:
            keyring.delete_password(settings.keyring_service, name)
        except Exception:  # noqa: BLE001 - best effort
            pass
    except OSError as exc:
        raise RuntimeError(
            f"Cannot save credentials for {name}: keyring failed and file "
            f"write to {_credentials_dir()} also failed ({exc})"
        ) from exc


def _load_with_fallback(name: str) -> str | None:
    """Read credentials. File fallback takes precedence over keyring.

    Rationale: if file fallback was used at write time (because keyring
    rejected the size), the keyring entry will either be missing or stale.
    Always read file first so we get the authoritative value.
    """
    file_value = _read_file_credentials(name)
    if file_value is not None:
        return file_value
    return _safe_get(settings.keyring_service, name)


def _delete_with_fallback(name: str) -> None:
    """Delete from both stores (one of them might be empty already)."""
    try:
        keyring.delete_password(settings.keyring_service, name)
    except (keyring.errors.PasswordDeleteError, keyring.errors.NoKeyringError):
        pass
    _delete_file_credentials(name)


def _safe_get(service: str, username: str) -> str | None:
    """Wrap keyring.get_password to handle environments without a keyring backend.

    On developer/test machines (e.g. headless Linux containers) there may be no
    keyring backend installed. We treat that the same as "no credentials" rather
    than crashing, so the settings screen can still render and prompt the user
    to connect.
    """
    global _keyring_warned
    try:
        return keyring.get_password(service, username)
    except keyring.errors.NoKeyringError:
        if not _keyring_warned:
            logger.warning(
                "No keyring backend available; treating all platforms as not connected. "
                "On a real desktop (Windows/macOS) this works automatically."
            )
            _keyring_warned = True
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Keyring read failed: %s", exc)
        return None


def store_credentials(platform: Platform, payload: dict[str, Any]) -> None:
    """Store credentials for a platform.

    ``payload`` is a free-form dict. Common keys:
      - ``access_token`` (str)
      - ``refresh_token`` (str | None)
      - ``expires_at`` (ISO timestamp str)
      - ``account_label`` (str) - shop name or seller ID for display

    Anything else the platform needs (eBay's seller account ID, Etsy's shop ID,
    Squarespace's site UUID) goes into the same blob.

    Raises RuntimeError only if both keyring AND file fallback fail.
    The fallback covers the common case of Windows rejecting an oversized
    eBay token blob (WinError 1783).
    """
    serialized = _serialize(payload)
    _store_with_fallback(_key_for(platform), serialized)


def load_credentials(platform: Platform) -> dict[str, Any] | None:
    """Retrieve credentials for a platform, or None if not connected."""
    raw = _load_with_fallback(_key_for(platform))
    if raw is None:
        return None
    return _deserialize(raw)


def clear_credentials(platform: Platform) -> None:
    """Delete credentials from both keyring and file fallback."""
    _delete_with_fallback(_key_for(platform))


def is_connected(platform: Platform) -> bool:
    """Quick yes/no check for the settings screen."""
    return load_credentials(platform) is not None


def expires_in(platform: Platform) -> timedelta | None:
    """Return time until the access token expires.

    Returns:
      - timedelta: when the token has a known expiry
      - None: when the platform either isn't connected or has no expiry tracking

    Negative values mean the token has already expired.
    """
    creds = load_credentials(platform)
    if creds is None:
        return None
    expires_at = creds.get("expires_at")
    if expires_at is None:
        return None
    try:
        expiry = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return None
    return expiry - datetime.now(tz=expiry.tzinfo)


def account_label(platform: Platform) -> str | None:
    """Convenience accessor for the human-readable account label."""
    creds = load_credentials(platform)
    if creds is None:
        return None
    return creds.get("account_label")


# ---------------------------------------------------------------------------
# Service credentials (non-platform: image hosts, future webhooks, etc.)
# ---------------------------------------------------------------------------
#
# Same keyring backend as platform credentials, separate namespace so a
# hypothetical platform with the same string name doesn't collide. The API
# mirrors the platform functions so callers feel familiar.


def store_service_credentials(service_name: str, payload: dict[str, Any]) -> None:
    """Store service credentials. Same keyring-then-file fallback as platforms."""
    serialized = _serialize(payload)
    _store_with_fallback(_service_key_for(service_name), serialized)


def load_service_credentials(service_name: str) -> dict[str, Any] | None:
    """Retrieve service credentials, or None if not configured."""
    raw = _load_with_fallback(_service_key_for(service_name))
    if raw is None:
        return None
    return _deserialize(raw)


def clear_service_credentials(service_name: str) -> None:
    """Delete service credentials from both keyring and file fallback."""
    _delete_with_fallback(_service_key_for(service_name))


def is_service_connected(service_name: str) -> bool:
    """Quick yes/no for the settings screen."""
    return load_service_credentials(service_name) is not None

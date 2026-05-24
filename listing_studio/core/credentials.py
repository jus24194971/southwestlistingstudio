"""OAuth credential storage via the OS keyring.

Tokens never touch the filesystem. On Windows they go in Credential Manager,
on macOS the Keychain, and on Linux Secret Service (gnome-keyring/KWallet).

For each platform we store one JSON blob containing access_token, refresh_token,
expires_at, and any platform-specific metadata. The blob format is intentionally
flexible because the four platforms have different token shapes.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
from datetime import datetime, timedelta
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

    Raises RuntimeError if no keyring backend is available - storing creds is
    a deliberate user action and silently failing would be very confusing.
    """
    serialized = _serialize(payload)
    try:
        keyring.set_password(settings.keyring_service, _key_for(platform), serialized)
    except keyring.errors.NoKeyringError as exc:
        raise RuntimeError(
            "Cannot save credentials: no keyring backend available. "
            "On Windows this should work out of the box; on Linux you may need "
            "to install 'gnome-keyring' or equivalent."
        ) from exc


def load_credentials(platform: Platform) -> dict[str, Any] | None:
    """Retrieve credentials for a platform, or None if not connected."""
    raw = _safe_get(settings.keyring_service, _key_for(platform))
    if raw is None:
        return None
    return _deserialize(raw)


def clear_credentials(platform: Platform) -> None:
    """Delete credentials for a platform (user clicked Disconnect)."""
    try:
        keyring.delete_password(settings.keyring_service, _key_for(platform))
    except (keyring.errors.PasswordDeleteError, keyring.errors.NoKeyringError):
        # Already missing or no backend - nothing to do
        pass


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
    """Store credentials for a non-platform service (e.g. an image host).

    Raises RuntimeError if no keyring backend is available - same contract
    as the platform version, since this is also a user-initiated save.
    """
    serialized = _serialize(payload)
    try:
        keyring.set_password(settings.keyring_service, _service_key_for(service_name), serialized)
    except keyring.errors.NoKeyringError as exc:
        raise RuntimeError(
            "Cannot save credentials: no keyring backend available."
        ) from exc


def load_service_credentials(service_name: str) -> dict[str, Any] | None:
    """Retrieve service credentials, or None if not configured."""
    raw = _safe_get(settings.keyring_service, _service_key_for(service_name))
    if raw is None:
        return None
    return _deserialize(raw)


def clear_service_credentials(service_name: str) -> None:
    """Delete service credentials (user clicked Disconnect on the host card)."""
    try:
        keyring.delete_password(settings.keyring_service, _service_key_for(service_name))
    except (keyring.errors.PasswordDeleteError, keyring.errors.NoKeyringError):
        pass


def is_service_connected(service_name: str) -> bool:
    """Quick yes/no for the settings screen."""
    return load_service_credentials(service_name) is not None

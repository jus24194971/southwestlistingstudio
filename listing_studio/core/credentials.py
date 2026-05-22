"""OAuth credential storage via the OS keyring.

Tokens never touch the filesystem. On Windows they go in Credential Manager,
on macOS the Keychain, and on Linux Secret Service (gnome-keyring/KWallet).

For each platform we store one JSON blob containing access_token, refresh_token,
expires_at, and any platform-specific metadata. The blob format is intentionally
flexible because the four platforms have different token shapes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import keyring
import keyring.errors

from listing_studio.config import settings
from listing_studio.core.models import Platform

logger = logging.getLogger(__name__)


def _key_for(platform: Platform) -> str:
    """Build the keyring "username" used to identify a platform's credentials."""
    return f"oauth_token::{platform.value}"


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
    serialized = json.dumps(payload, default=str)
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
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Corrupt entry - treat as missing rather than crashing
        return None


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

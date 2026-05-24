"""Photo hosting for marketplaces that require public URLs (Reverb).

Reverb's API doesn't accept binary photo uploads - it accepts URLs and fetches
the image server-side. Our previous attempt at ``POST /listings/{id}/images``
with multipart bodies returned 405; that endpoint doesn't exist. So instead we
upload to a public image host first, then hand Reverb the URL.

This module isolates that pattern behind a tiny abstract interface so we can
swap hosts (start with ImgBB, add Cloudinary later) without touching the
calling code in ``ui/api.py``.

Storage contract: API keys live in the OS keyring under the "service::<name>"
keyring namespace (see core/credentials.py). Plain text on disk is avoided.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod

import httpx

from listing_studio import __version__
from listing_studio.core.credentials import (
    is_service_connected,
    load_service_credentials,
)

logger = logging.getLogger(__name__)


# Service name used in the keyring. Matches the "host" identifier the UI
# sends to /api/settings/photo-host/<name>/connect.
IMGBB_SERVICE_NAME = "imgbb"

# Tiny transparent 1x1 PNG used for connection tests. Base64-encoded inline
# so we don't carry a binary asset around. Real upload bytes use the photo
# processor; this is only for "does the API key work" pings.
_TEST_PING_PNG_BYTES = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class PhotoHostError(Exception):
    """Raised when a photo upload to the host fails.

    The message is intended to be surfaced in the UI's per-photo error list,
    so keep it short and concrete (e.g. "ImgBB: invalid API key", not a stack
    trace).
    """


class PhotoHost(ABC):
    """Abstract photo host.

    Implementations upload a single normalized image and return a public URL
    that a marketplace (Reverb) can fetch server-side.
    """

    #: Service identifier used in keyring + UI routes. Must match exactly the
    #: name passed to load_service_credentials().
    service_name: str = ""

    #: Human label shown in the Settings UI.
    display_name: str = ""

    @abstractmethod
    async def upload(self, image_bytes: bytes, filename: str) -> str:
        """Upload ``image_bytes`` and return a publicly fetchable URL.

        Raises PhotoHostError on any failure (network, auth, validation).
        The caller is responsible for retries; this method doesn't retry.
        """

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str | None]:
        """Validate the stored credentials by uploading a tiny test image.

        Returns (True, account_label) on success, (False, error_message)
        otherwise. Matches the signature of platform connectors'
        test_connection() so the UI can treat them uniformly.
        """


# ---------------------------------------------------------------------------
# ImgBB implementation
# ---------------------------------------------------------------------------


class ImgBBHost(PhotoHost):
    """ImgBB image host.

    API docs: https://api.imgbb.com/

    Auth: a single API key, passed as a query param. We don't store an
    account label because ImgBB's free tier doesn't return one - the API
    just confirms the key was accepted.

    Public-by-URL note: ImgBB images are accessible to anyone with the URL.
    That's fine for product photos that will be public on Reverb anyway,
    but worth knowing if we ever consider it for private/staged content.
    """

    service_name = IMGBB_SERVICE_NAME
    display_name = "ImgBB"

    BASE_URL = "https://api.imgbb.com/1/upload"
    USER_AGENT = f"ListingStudio/{__version__}"

    # Per-photo upload timeout. Generous because ImgBB occasionally takes
    # 10+ seconds for large images during their peak hours.
    TIMEOUT_SECONDS = 60.0

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("ImgBB API key cannot be empty")
        self._api_key = api_key

    async def upload(self, image_bytes: bytes, filename: str) -> str:
        # ImgBB accepts the image as a base64 form field. We tried multipart
        # too; base64 is more reliable behind some corporate proxies and
        # the per-image overhead (~33% size inflation) is fine at our scale.
        encoded = base64.b64encode(image_bytes).decode("ascii")

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.BASE_URL,
                    params={"key": self._api_key},
                    data={"image": encoded, "name": filename},
                    headers={"User-Agent": self.USER_AGENT},
                )
        except httpx.TimeoutException as exc:
            raise PhotoHostError(
                f"ImgBB upload timed out after {self.TIMEOUT_SECONDS:.0f}s"
            ) from exc
        except httpx.RequestError as exc:
            raise PhotoHostError(f"ImgBB network error: {exc}") from exc

        if response.status_code == 400:
            # ImgBB returns 400 for invalid keys *and* for rejected images.
            # Their error JSON is the cleanest source of detail.
            detail = _extract_imgbb_error(response) or "bad request"
            raise PhotoHostError(f"ImgBB rejected upload: {detail}")
        if response.status_code == 403:
            raise PhotoHostError("ImgBB rejected the API key (403)")
        if response.status_code >= 500:
            raise PhotoHostError(f"ImgBB server error {response.status_code}")
        if response.status_code != 200:
            raise PhotoHostError(f"ImgBB unexpected status {response.status_code}")

        try:
            data = response.json()
        except Exception as exc:
            raise PhotoHostError("ImgBB returned malformed response") from exc

        # Expected shape: {"data": {"url": "...", "display_url": "..."}, "success": true}
        if not data.get("success"):
            detail = _extract_imgbb_error(response) or "unknown error"
            raise PhotoHostError(f"ImgBB upload failed: {detail}")

        url = (data.get("data") or {}).get("url")
        if not url:
            raise PhotoHostError("ImgBB response missing image URL")

        return url

    async def test_connection(self) -> tuple[bool, str | None]:
        try:
            url = await self.upload(_TEST_PING_PNG_BYTES, "listing-studio-ping.png")
        except PhotoHostError as exc:
            return False, str(exc)
        # ImgBB doesn't return an account label; the successful URL is proof
        # enough that the key works.
        logger.info("ImgBB test upload succeeded: %s", url)
        return True, "ImgBB (free tier)"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_configured_host() -> PhotoHost | None:
    """Return the currently configured photo host, or None if none is set up.

    Reads keyring; doesn't validate connectivity (use ``host.test_connection()``
    for that). Returns None for fast "is the post-with-photos path available?"
    checks in the UI and posting flow.

    For now there's only one possible host (ImgBB), but the abstraction is
    here so we can add Cloudinary etc. without breaking callers.
    """
    if is_service_connected(IMGBB_SERVICE_NAME):
        creds = load_service_credentials(IMGBB_SERVICE_NAME) or {}
        api_key = creds.get("api_key")
        if api_key:
            return ImgBBHost(api_key=api_key)
    return None


def get_status() -> dict[str, object]:
    """Return a JSON-friendly dict describing the host config, for the UI.

    Shape:
        {
            "connected": bool,
            "service_name": "imgbb" | null,
            "display_name": "ImgBB" | null,
        }
    """
    host = get_configured_host()
    if host is None:
        return {"connected": False, "service_name": None, "display_name": None}
    return {
        "connected": True,
        "service_name": host.service_name,
        "display_name": host.display_name,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_imgbb_error(response: httpx.Response) -> str | None:
    """Pull a human-readable error string out of an ImgBB error response.

    ImgBB error JSON shapes seen in the wild:
        {"status_code": 400, "error": {"message": "Invalid API key", "code": 100}}
        {"status_code": 400, "status_txt": "Bad Request"}
    """
    try:
        data = response.json()
    except Exception:
        return response.text[:200] if response.text else None

    err = data.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    if isinstance(err, str):
        return err
    if data.get("status_txt"):
        return str(data["status_txt"])
    return None

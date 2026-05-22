"""Abstract base class for platform connectors.

Each platform (Reverb, eBay, Etsy, Squarespace, Facebook) implements this
interface. The posting orchestrator iterates over connectors uniformly.

Design decisions:

1. **Async methods.** httpx supports async, and posting to 4 platforms in
   parallel is the explicit "fast" feature. Connectors are async by default.

2. **Connectors are stateless.** They don't hold connections, sessions, or
   tokens between calls. State lives in the keyring (tokens) and database
   (listings, attempts). This makes them easy to test and reason about.

3. **The connector's job is shape-mapping.** Convert our internal
   ``Template`` to the platform's JSON, send the request, convert the
   response to a ``PostResult``. The orchestrator handles retries,
   parallelism, and error aggregation.

4. **Facebook is special.** It implements the same interface but its
   ``post()`` returns a ``PostResult`` with status=MANUAL and includes
   the copy-paste package in the response.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from listing_studio.core.models import Platform, PostStatus

if TYPE_CHECKING:
    from listing_studio.core.models import Template


class PostingError(Exception):
    """Raised when a platform refuses a posting attempt.

    The orchestrator catches this, logs the error, and continues with other
    platforms (when best-effort mode is on). The exception carries the
    platform-provided error message for display in the UI.
    """

    def __init__(self, platform: Platform, message: str, *, is_auth_error: bool = False) -> None:
        self.platform = platform
        self.message = message
        self.is_auth_error = is_auth_error
        super().__init__(f"{platform.display_name}: {message}")


@dataclass
class PostOutcome:
    """The result of a single post() call, returned by connectors.

    Distinct from the schema ``PostResult`` so connectors aren't coupled to
    the API layer. The orchestrator converts this to a PostResult.
    """

    status: PostStatus
    external_listing_id: str | None = None
    external_listing_url: str | None = None
    error_message: str | None = None

    # Used for Facebook only
    facebook_package: dict | None = None


class PlatformConnector(ABC):
    """Abstract interface every platform connector implements."""

    #: The platform this connector handles.
    platform: Platform

    @abstractmethod
    async def is_connected(self) -> bool:
        """Return True if we have valid credentials for this platform."""

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str | None]:
        """Make a no-op API call to verify the connection works.

        Returns (True, None) on success or (False, error_message) on failure.
        The settings screen's "Test" button calls this.
        """

    @abstractmethod
    async def post(self, template: "Template", price_cents: int, quantity: int) -> PostOutcome:
        """Create a new listing on this platform.

        Raises ``PostingError`` on failure (the orchestrator catches it).
        """

    @abstractmethod
    async def update_inventory(
        self, external_listing_id: str, new_quantity: int
    ) -> bool:
        """Update the quantity of an existing listing.

        Called when a sale on platform A should reduce inventory on platforms B+.
        Returns True on success.
        """

    @abstractmethod
    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        """Fetch orders/sales placed since the given timestamp.

        Used by the inventory sync poller (currently only Squarespace polls;
        other connectors return [] for now).
        """

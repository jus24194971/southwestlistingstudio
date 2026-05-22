"""Etsy platform connector.

Currently a stub. Real implementation uses Etsy's Open API v3.
Auth: OAuth 2.0 with 90-day access token (requires periodic reconnection - the
one platform where Dad will need to redo the connection regularly).

Key endpoints:
  POST /v3/application/shops/{shop_id}/listings
  PUT  /v3/application/shops/{shop_id}/listings/{listing_id}
  GET  /v3/application/shops/{shop_id}/receipts (sales)
"""

from __future__ import annotations

from datetime import datetime

from listing_studio.core.credentials import is_connected as _has_creds
from listing_studio.core.models import Platform, Template
from listing_studio.platforms.base import PlatformConnector, PostOutcome, PostingError


class EtsyConnector(PlatformConnector):
    """Etsy API v3 connector (stub)."""

    platform = Platform.ETSY

    BASE_URL = "https://openapi.etsy.com/v3"

    async def is_connected(self) -> bool:
        return _has_creds(self.platform)

    async def test_connection(self) -> tuple[bool, str | None]:
        if not await self.is_connected():
            return False, "Not connected"
        return True, None

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        raise PostingError(self.platform, "Etsy connector not yet implemented")

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        return False

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        return []

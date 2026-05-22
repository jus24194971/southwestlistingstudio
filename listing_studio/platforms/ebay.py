"""eBay platform connector.

Currently a stub. Real implementation uses eBay's Sell APIs (REST).
Auth requires an eBay Developer Program account (multi-day approval).

Key APIs:
  Inventory API     - manage inventory items
  Listing API       - create offers (listings)
  Fulfillment API   - order/sale notifications

eBay's API is by far the most complex of the four. Category mapping for
musical instruments is particularly thorny (Guitar Tuners is category 33034).
"""

from __future__ import annotations

from datetime import datetime

from listing_studio.core.credentials import is_connected as _has_creds
from listing_studio.core.models import Platform, Template
from listing_studio.platforms.base import PlatformConnector, PostOutcome, PostingError


class EbayConnector(PlatformConnector):
    """eBay API connector (stub - blocked on dev account approval)."""

    platform = Platform.EBAY

    BASE_URL = "https://api.ebay.com"

    async def is_connected(self) -> bool:
        return _has_creds(self.platform)

    async def test_connection(self) -> tuple[bool, str | None]:
        if not await self.is_connected():
            return False, "Not connected. Get an eBay Developer account first."
        return True, None

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        raise PostingError(self.platform, "eBay connector not yet implemented")

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        return False

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        return []

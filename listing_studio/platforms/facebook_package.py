"""Facebook Marketplace 'connector'.

Facebook doesn't allow third-party posting to Marketplace, so we implement
the same interface but ``post()`` returns a copy-paste package (status=MANUAL)
instead of actually creating a listing. The user is responsible for opening
Marketplace in their browser and pasting the prepared text and photos.

Photos are resized to ``settings.fb_max_image_size`` (default 2048px on the
long edge) and copied to ``settings.fb_temp_dir`` so the user can drag them
into the Marketplace form.
"""

from __future__ import annotations

from datetime import datetime

from listing_studio.core.models import Platform, PostStatus, Template
from listing_studio.platforms.base import PlatformConnector, PostOutcome


class FacebookConnector(PlatformConnector):
    """Facebook Marketplace 'connector' (manual mode only)."""

    platform = Platform.FACEBOOK

    async def is_connected(self) -> bool:
        # Facebook is always "available" - no auth required for the manual workflow
        return True

    async def test_connection(self) -> tuple[bool, str | None]:
        return True, None

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        """Generate the copy-paste package. Returns status=MANUAL."""
        # TODO: Implement
        #   1. Resize template's photos to settings.fb_max_image_size
        #   2. Save them to settings.fb_temp_dir
        #   3. Build a FacebookPackage dict for the UI to display
        package = {
            "title": template.title,
            "price_cents": price_cents,
            "description": template.description,
            "photo_paths": [],  # Will be filled after resize step is implemented
            "photo_temp_dir": "",  # Will point at settings.fb_temp_dir / template_id
        }
        return PostOutcome(
            status=PostStatus.MANUAL,
            facebook_package=package,
        )

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        # Can't update FB listings programmatically
        return False

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        return []

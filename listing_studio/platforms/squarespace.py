"""Squarespace Commerce platform connector.

Auth model: **API key** (not OAuth).

For OAuth, Squarespace requires a manual review by their team to issue
credentials - meant for vendors publishing Squarespace Extensions. For a
personal integration with your own store, API keys are the right fit:

  * Self-serve generation in Settings > Advanced > Developer API Keys
  * Permission-scoped (we use: Products R/W, Inventory R/W, Orders R/O)
  * Never expire as long as the site is active
  * Used as a Bearer token: ``Authorization: Bearer <api_key>``

API endpoints we hit:

  GET    /1.0/authorization/website            - test/validate; returns site info
  GET    /1.0/commerce/products?cursor=...    - list products (for matching to templates)
  POST   /1.0/commerce/products               - create a product
  PATCH  /1.0/commerce/products/{id}          - update product fields
  POST   /1.0/commerce/products/{id}/variants/{variant_id}/image - attach image
  POST   /1.0/commerce/inventory/adjustments  - adjust stock levels
  GET    /1.0/commerce/orders?modifiedAfter=  - list orders (used for polling)

Squarespace API quirks worth knowing:

  * Every request requires a User-Agent header. Squarespace rejects requests
    without one with a 400. We set it to "ListingStudio/<version>".
  * Rate limit: 60 req/min sliding window. Cool-down on 429 is 60 seconds.
  * Inventory endpoints use SKUs to identify items, not product IDs.
  * Product creation requires variantAttributes even for single-variant products.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from listing_studio import __version__
from listing_studio.core.credentials import (
    is_connected as _has_creds,
    load_credentials,
)
from listing_studio.core.models import Platform, Template
from listing_studio.platforms.base import PlatformConnector, PostOutcome, PostingError

logger = logging.getLogger(__name__)


class SquarespaceConnector(PlatformConnector):
    """Squarespace Commerce API connector (API key auth)."""

    platform = Platform.SQUARESPACE

    BASE_URL = "https://api.squarespace.com/1.0"
    USER_AGENT = f"ListingStudio/{__version__}"
    TIMEOUT_SECONDS = 30.0

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    async def is_connected(self) -> bool:
        return _has_creds(self.platform)

    def _get_api_key(self) -> str | None:
        """Read the stored API key, or None if not connected."""
        creds = load_credentials(self.platform)
        if creds is None:
            return None
        return creds.get("api_key")

    def _headers(self, api_key: str) -> dict[str, str]:
        """Build the standard auth + UA headers."""
        return {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    async def test_connection(self) -> tuple[bool, str | None]:
        """Validate the stored API key by calling /authorization/website.

        Returns (True, account_label) on success, (False, error_message) on failure.
        Per Squarespace's docs, GET /1.0/authorization/website returns the site
        that owns the API key - it's the canonical "who am I" endpoint and works
        with any valid key regardless of which Commerce scopes are granted.
        """
        api_key = self._get_api_key()
        if not api_key:
            return False, "Not connected - no API key stored"

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self.BASE_URL}/authorization/website",
                    headers=self._headers(api_key),
                )
        except httpx.RequestError as exc:
            return False, f"Network error: {exc}"

        if response.status_code == 401:
            return False, "Invalid API key (Squarespace rejected the credentials)"
        if response.status_code == 403:
            return False, "API key lacks required permissions"
        if response.status_code != 200:
            return False, f"Squarespace error {response.status_code}: {response.text[:200]}"

        try:
            data = response.json()
        except Exception:
            return False, "Squarespace returned malformed response"

        site_title = data.get("title") or data.get("siteId") or "Unknown site"
        return True, site_title

    # ------------------------------------------------------------------
    # Posting / product creation
    # ------------------------------------------------------------------

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        """Create a product on Squarespace from the given template.

        Returns a PostOutcome with the new product's URL and ID on success.
        Raises PostingError on failure (auth issues, validation errors, etc.).

        Note: Squarespace requires SKU uniqueness across the store. We use the
        template's auto-generated SKU (or a derivative if needed). If the SKU
        already exists, this will fail with a 400; the caller should treat that
        as a sign the product is already on Squarespace and consider updating
        instead.
        """
        api_key = self._get_api_key()
        if not api_key:
            raise PostingError(
                self.platform, "Not connected. Add API key on the Settings screen.",
                is_auth_error=True,
            )

        # Build the product payload per Squarespace's POST /commerce/products schema.
        # Required fields: type, storePageId (or "storePageUrlId"), name,
        # description, isVisible, variantAttributes, variants.
        payload = {
            "type": "PHYSICAL",
            "name": template.title or template.name,
            "description": _markdown_to_squarespace_html(template.description or ""),
            "isVisible": True,
            # Squarespace requires at least one variantAttribute even for
            # single-variant products. We use "Default" as a placeholder.
            "variantAttributes": ["Default"],
            "variants": [
                {
                    "sku": _build_sku(template),
                    "pricing": {
                        "basePrice": {
                            "currency": "USD",
                            "value": _cents_to_decimal_str(price_cents),
                        },
                        "onSale": False,
                    },
                    "stock": {
                        "quantity": quantity,
                        "unlimited": False,
                    },
                    "attributes": {"Default": "Default"},
                    "shippingMeasurements": _shipping_measurements(template),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self.BASE_URL}/commerce/products",
                    headers={**self._headers(api_key), "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise PostingError(self.platform, f"Network error: {exc}") from exc

        if response.status_code == 401:
            raise PostingError(
                self.platform, "Squarespace rejected the API key. Reconnect on Settings.",
                is_auth_error=True,
            )
        if response.status_code == 403:
            raise PostingError(
                self.platform,
                "API key lacks Products Read/Write permission. Regenerate on Squarespace.",
                is_auth_error=True,
            )
        if response.status_code == 429:
            raise PostingError(
                self.platform,
                "Squarespace rate limit hit. Try again in a minute.",
            )
        if response.status_code not in (200, 201):
            # Try to extract a useful error from Squarespace's response body
            detail = _extract_error_message(response)
            raise PostingError(
                self.platform,
                f"Squarespace error ({response.status_code}): {detail}",
            )

        try:
            data = response.json()
        except Exception as exc:
            raise PostingError(
                self.platform, "Squarespace returned malformed response",
            ) from exc

        product_id = data.get("id")
        product_url = data.get("url") or data.get("urlSlug")
        if not product_id:
            raise PostingError(
                self.platform, "Squarespace didn't return a product ID",
            )

        # Build the full URL if we got back just a slug
        if product_url and not product_url.startswith("http"):
            # We don't know Dad's domain at this layer; the caller can construct
            # the full URL using the site info from /sites/me. For now we store
            # just the slug or full URL as returned.
            pass

        return PostOutcome(
            external_listing_id=str(product_id),
            external_listing_url=product_url or "",
        )

    # ------------------------------------------------------------------
    # Inventory updates
    # ------------------------------------------------------------------

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        """Set the stock level for a Squarespace product variant.

        Squarespace's inventory API works on SKUs, not product IDs. We first
        fetch the product to get its variant SKU, then call the inventory
        adjustment endpoint.

        Returns True on success, False on any failure.
        """
        api_key = self._get_api_key()
        if not api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                # First: get the product to find its variant SKU
                product_response = await client.get(
                    f"{self.BASE_URL}/commerce/products/{external_listing_id}",
                    headers=self._headers(api_key),
                )
                if product_response.status_code != 200:
                    logger.warning(
                        "Couldn't fetch product %s for inventory update: %d",
                        external_listing_id, product_response.status_code,
                    )
                    return False

                product = product_response.json()
                variants = product.get("variants", [])
                if not variants:
                    return False
                sku = variants[0].get("sku")
                if not sku:
                    return False

                # Now adjust inventory by absolute set (not delta)
                inv_response = await client.post(
                    f"{self.BASE_URL}/commerce/inventory/adjustments",
                    headers={**self._headers(api_key), "Content-Type": "application/json"},
                    json={
                        "incrementOperations": [
                            {"variantId": variants[0].get("id"), "quantity": new_quantity},
                        ],
                    },
                )
                return inv_response.status_code in (200, 204)

        except httpx.RequestError as exc:
            logger.warning("Network error updating Squarespace inventory: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Order polling (drives inventory sync to other marketplaces)
    # ------------------------------------------------------------------

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        """Fetch orders modified since the given timestamp.

        Used by the polling service to detect new sales on Squarespace and
        decrement inventory on the other marketplaces.

        Returns a list of order dicts in Squarespace's native format. Caller
        is responsible for matching line items to our templates by SKU.
        """
        api_key = self._get_api_key()
        if not api_key:
            return []

        # ISO-format timestamp for the API filter
        since_iso = since.isoformat()
        if not since_iso.endswith("Z") and "+" not in since_iso:
            since_iso += "Z"

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self.BASE_URL}/commerce/orders",
                    params={"modifiedAfter": since_iso, "fulfillmentStatus": "FULFILLED,PENDING"},
                    headers=self._headers(api_key),
                )
        except httpx.RequestError as exc:
            logger.warning("Network error polling Squarespace orders: %s", exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "Squarespace order polling failed: %d %s",
                response.status_code, response.text[:200],
            )
            return []

        try:
            data = response.json()
        except Exception:
            return []

        return data.get("result", [])


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _cents_to_decimal_str(cents: int) -> str:
    """Convert 8500 -> '85.00' (Squarespace wants string decimals not floats)."""
    return f"{cents / 100:.2f}"


def _build_sku(template: Template) -> str:
    """Generate a SKU for the template.

    Squarespace requires SKU uniqueness across the store. We use the template
    name in slug form, plus the ID for uniqueness in case names collide.
    """
    slug = "".join(c for c in (template.name or "item").upper() if c.isalnum() or c in "-_")[:24]
    return f"LS-{slug}-{template.id}"


def _shipping_measurements(template: Template) -> dict:
    """Return Squarespace shipping measurements from template fields.

    Squarespace expects weight in pounds. Our weight_oz is in ounces.
    """
    weight_lb = (template.weight_oz or 0) / 16.0
    return {
        "weight": {"unit": "POUND", "value": round(weight_lb, 4)},
        # Dimensions are optional and we don't currently track them
    }


def _markdown_to_squarespace_html(markdown_text: str) -> str:
    """Convert basic markdown-like text to the HTML Squarespace expects.

    Squarespace's description field accepts HTML. For now we do minimal
    conversion - paragraph breaks and line breaks. Later we could plug in
    a real markdown library if templates start using formatting.
    """
    if not markdown_text:
        return ""
    # Paragraph breaks: two newlines -> </p><p>
    paragraphs = [p.strip() for p in markdown_text.split("\n\n") if p.strip()]
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)


def _extract_error_message(response: httpx.Response) -> str:
    """Pull a useful error message from a Squarespace error response."""
    try:
        data = response.json()
    except Exception:
        return response.text[:200]

    # Squarespace error shape: {"type": "...", "message": "...", "details": [...]}
    msg = data.get("message", "")
    details = data.get("details")
    if details and isinstance(details, list):
        detail_msgs = []
        for d in details:
            if isinstance(d, dict):
                detail_msgs.append(d.get("description") or d.get("message") or "")
        if detail_msgs:
            return f"{msg} ({'; '.join(detail_msgs)})"
    return msg or response.text[:200]

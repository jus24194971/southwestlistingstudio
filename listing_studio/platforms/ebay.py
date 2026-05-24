"""eBay platform connector.

Auth model is two-tier:

  * **App token** (client_credentials grant) — issued from the developer
    app's client_id + client_secret. Read-only; lets us fetch the public
    taxonomy without any user consent. Lives in memory only, refreshed
    every ~2 hours.
  * **User token** (authorization_code grant via OAuth redirect) — required
    for inventory and listing endpoints. Tied to Dad's actual eBay seller
    account. Stored in the keyring like other platform credentials. Not
    needed for taxonomy reads, so we don't require it just to populate the
    category picker.

The credentials blob stored in the keyring carries:

    {
        "client_id":  "<app id>",
        "client_secret": "<cert id>",
        "dev_id":     "<dev id>",         # optional, used for some legacy APIs
        "user_access_token": "...",        # populated after the user OAuth dance
        "user_refresh_token": "...",
        "user_token_expires_at": "ISO timestamp",
        "account_label": "<eBay user id>"
    }

The taxonomy-only methods used to populate the category picker (search,
get_recent) only need client_id + client_secret to be present. Posting
listings will need the user token, but that's a separate flow.

Listing creation is NOT implemented yet — see the post() stub at the
bottom. The taxonomy + connection-test infrastructure here is the
foundation for tomorrow's work.

References:
  Taxonomy API:  https://developer.ebay.com/api-docs/commerce/taxonomy/overview.html
  App tokens:    https://developer.ebay.com/api-docs/static/oauth-client-credentials-grant.html
  Sell APIs:     https://developer.ebay.com/api-docs/sell/static/overview.html
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from listing_studio import __version__
from listing_studio.core import credentials as creds
from listing_studio.core.models import Platform, Template
from listing_studio.platforms.base import PlatformConnector, PostingError, PostOutcome

logger = logging.getLogger(__name__)


# US default category tree. eBay maintains separate trees per marketplace
# (US, UK, DE, etc.); for Southwest Acoustics we only care about US.
EBAY_US_TREE_ID = "0"


class EbayConnector(PlatformConnector):
    """eBay API connector."""

    platform = Platform.EBAY

    BASE_URL = "https://api.ebay.com"
    USER_AGENT = f"ListingStudio/{__version__}"
    TIMEOUT_SECONDS = 30.0

    # In-memory caches. App-token cache is per-process; taxonomy cache is
    # module-level so any connector instance in this process reuses it
    # (taxonomy is ~24k entries, expensive to fetch).
    _app_token_cache: dict[str, Any] = {}     # {"token": str, "expires_at": float}
    _taxonomy_cache: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    async def is_connected(self) -> bool:
        """True if the *app-level* credentials are stored.

        Note: posting requires a user OAuth token too, but for taxonomy
        reads (category picker, suggestions) app creds are enough. We
        report 'connected' based on the minimum-viable state so the UI
        renders the search box.
        """
        stored = creds.load_credentials(self.platform)
        if stored is None:
            return False
        return bool(stored.get("client_id") and stored.get("client_secret"))

    def _get_app_creds(self) -> tuple[str, str] | None:
        """Return (client_id, client_secret) or None if not stored."""
        stored = creds.load_credentials(self.platform)
        if stored is None:
            return None
        cid = stored.get("client_id")
        sec = stored.get("client_secret")
        if not cid or not sec:
            return None
        return cid, sec

    async def _get_app_token(self, client: httpx.AsyncClient) -> str:
        """Fetch (or refresh) the app-level OAuth token.

        Cached per-process for the duration of the token's lifetime minus
        a 60s safety buffer. Raises PostingError if credentials are missing
        or the auth call fails.
        """
        now = time.monotonic()
        cache = EbayConnector._app_token_cache
        if cache.get("token") and cache.get("expires_at", 0) > now + 60:
            return cache["token"]

        app_creds = self._get_app_creds()
        if app_creds is None:
            raise PostingError(
                self.platform,
                "eBay app credentials not set. Add client_id + client_secret in Settings.",
                is_auth_error=True,
            )
        client_id, client_secret = app_creds

        # Basic auth header is base64(client_id:client_secret)
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("ascii")

        response = await client.post(
            f"{self.BASE_URL}/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.USER_AGENT,
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )

        if response.status_code == 401:
            raise PostingError(
                self.platform,
                "eBay rejected the app credentials. Check client_id + client_secret.",
                is_auth_error=True,
            )
        if response.status_code != 200:
            raise PostingError(
                self.platform,
                f"eBay token endpoint error {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise PostingError(self.platform, "eBay returned no access_token")

        # Cache with a 60s safety buffer
        expires_in = int(data.get("expires_in", 7200))
        EbayConnector._app_token_cache = {
            "token": token,
            "expires_at": now + expires_in,
        }
        return token

    def _bearer_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self) -> tuple[bool, str | None]:
        """Try fetching an app token; success means the credentials work.

        Doesn't validate the user OAuth token; that's a separate test once
        the user OAuth flow is implemented.
        """
        if self._get_app_creds() is None:
            return False, "App credentials missing (client_id + client_secret)"

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                await self._get_app_token(client)
        except PostingError as exc:
            return False, str(exc)
        except httpx.RequestError as exc:
            return False, f"Network error: {exc}"

        # Try to enrich with the user's seller display name if a user token
        # is also stored. Optional; failure is fine.
        stored = creds.load_credentials(self.platform)
        label = (stored or {}).get("account_label") or "eBay (app-only)"
        return True, label

    # ------------------------------------------------------------------
    # Taxonomy
    # ------------------------------------------------------------------

    async def _ensure_taxonomy_cache(self, client: httpx.AsyncClient) -> None:
        """Fetch + flatten the full US category tree, caching the result.

        eBay returns the entire tree as a deeply-nested JSON document. We
        recursively walk it once and store a flat list of
        ``{category_id, name, full_name, is_leaf}`` records suitable for
        searching.
        """
        if EbayConnector._taxonomy_cache is not None:
            return

        token = await self._get_app_token(client)
        response = await client.get(
            f"{self.BASE_URL}/commerce/taxonomy/v1/category_tree/{EBAY_US_TREE_ID}",
            headers=self._bearer_headers(token),
        )
        if response.status_code != 200:
            raise PostingError(
                self.platform,
                f"eBay taxonomy fetch failed ({response.status_code}): {response.text[:200]}",
            )

        data = response.json()
        root = data.get("rootCategoryNode")
        if not isinstance(root, dict):
            raise PostingError(self.platform, "eBay taxonomy response missing rootCategoryNode")

        flattened: list[dict[str, Any]] = []
        _flatten_tree(root, breadcrumb=[], out=flattened)

        EbayConnector._taxonomy_cache = flattened
        logger.info("Cached %d eBay taxonomy entries", len(flattened))

    async def search_taxonomy(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        """Search the cached eBay taxonomy by name.

        Mirrors ReverbConnector.search_taxonomy: exact-match first, then
        prefix match on the leaf name, then substring anywhere in the full
        breadcrumb path. Loads the full tree on first call (cached after).

        Returns a list of {category_id, name, full_name, is_leaf} dicts.
        Empty if not connected or if the API returned no usable data.
        """
        if not await self.is_connected():
            return []

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                await self._ensure_taxonomy_cache(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Couldn't load eBay taxonomy: %s", exc)
            return []

        taxonomy = EbayConnector._taxonomy_cache or []
        q = (query or "").lower().strip()

        if not q:
            # No query: return the first `limit` LEAVES (more useful than
            # mid-tree categories for a category picker).
            leaves = [e for e in taxonomy if e["is_leaf"]]
            return leaves[:limit]

        # Score: 100 = exact name match, 50 = name startswith, 25 = name
        # contains, 10 = full_name contains. Leaves outrank non-leaves
        # at the same score level (eBay only lets us list on leaves).
        scored: list[tuple[int, int, int, dict[str, Any]]] = []
        for entry in taxonomy:
            name_l = entry["name"].lower()
            full_l = entry["full_name"].lower()
            score = 0
            if name_l == q:
                score = 100
            elif name_l.startswith(q):
                score = 50
            elif q in name_l:
                score = 25
            elif q in full_l:
                score = 10
            if score == 0:
                continue
            leaf_bonus = 1 if entry["is_leaf"] else 0
            # Tuple keys: descending score, descending leaf-bonus, ascending name length
            scored.append((-score, -leaf_bonus, len(name_l), entry))

        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        return [entry for (_s, _l, _n, entry) in scored[:limit]]

    # ------------------------------------------------------------------
    # Posting (still a stub — needs user OAuth + inventory/offer wiring)
    # ------------------------------------------------------------------

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        raise PostingError(
            self.platform,
            "eBay listing creation not yet implemented (needs Inventory API + user OAuth).",
        )

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        return False

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        return []


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _flatten_tree(node: dict[str, Any], breadcrumb: list[str], out: list[dict[str, Any]]) -> None:
    """Walk one node of eBay's category_tree recursively.

    eBay's response shape per node:
        {
            "category": {"categoryId": "...", "categoryName": "..."},
            "childCategoryTreeNodes": [...],
            "leafCategoryTreeNode": true | false,
            "categoryTreeNodeLevel": N
        }

    The root node has no usable categoryId (it's just "Categories" or
    similar) - we skip recording it but still recurse into its children.
    """
    category = node.get("category") or {}
    cat_id = category.get("categoryId")
    name = category.get("categoryName") or ""
    is_leaf = bool(node.get("leafCategoryTreeNode"))
    level = node.get("categoryTreeNodeLevel", 0)

    if cat_id and level > 0:  # skip the root sentinel
        path = " > ".join(breadcrumb + [name])
        out.append({
            "category_id": int(cat_id),
            "name": name,
            "full_name": path,
            "is_leaf": is_leaf,
        })

    children = node.get("childCategoryTreeNodes") or []
    next_crumbs = breadcrumb + [name] if name and level > 0 else breadcrumb
    for child in children:
        _flatten_tree(child, next_crumbs, out)

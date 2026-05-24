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
import html
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from listing_studio import __version__
from listing_studio.core import credentials as creds
from listing_studio.core.models import Platform, Template
from listing_studio.platforms.base import PlatformConnector, PostingError, PostOutcome

logger = logging.getLogger(__name__)


# US default category tree. eBay maintains separate trees per marketplace
# (US, UK, DE, etc.); for Southwest Acoustics we only care about US.
EBAY_US_TREE_ID = "0"

# OAuth scopes required for the selling flows we plan to support. Reads
# come "free" with the app token; user tokens are needed for inventory,
# offers, and order/fulfillment data.
EBAY_USER_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
]

# Map our internal condition strings to eBay's numeric condition IDs.
# eBay validates these per-category - some categories reject "Used" etc.
# These are our best-fit defaults; if eBay rejects, the user fixes per
# template via platform_overrides later.
EBAY_CONDITION_IDS = {
    "brand_new": 1000,        # New
    "new_old_stock": 1500,    # New Other (closest match for NOS)
    "mint": 1500,
    "excellent": 3000,        # Used (eBay has no "Excellent" - 3000 is best generic)
    "very_good": 3000,
    "good": 3000,
    "fair": 3000,
    "poor": 7000,             # For parts or not working
    "b_stock": 1500,
    "non_functioning": 7000,
}

# US marketplace identifier eBay uses across the sell APIs.
EBAY_MARKETPLACE_ID = "EBAY_US"

# eBay's OAuth endpoints. Auth happens on auth.ebay.com (consent UI);
# token exchange happens on api.ebay.com (REST). Both are production -
# the sandbox equivalents have a `.sandbox.` infix but we're not using
# sandbox per the v0.4.0 decision.
EBAY_OAUTH_AUTHORIZE_URL = "https://auth.ebay.com/oauth2/authorize"
EBAY_OAUTH_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"


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
    # User OAuth (separate from the app token used for taxonomy reads)
    # ------------------------------------------------------------------

    def has_user_token(self) -> bool:
        """True if a user OAuth token has been stored.

        Listing creation (Inventory, Offer, Publish) requires a user token,
        which only arrives after Dad completes the OAuth consent flow in
        his browser. The category picker works without it.
        """
        stored = creds.load_credentials(self.platform)
        if stored is None:
            return False
        return bool(stored.get("user_access_token"))

    def build_authorize_url(self, state: str | None = None) -> str | None:
        """Construct the eBay OAuth authorize URL the user gets sent to.

        eBay uses the **RuName** (registered redirect name) as the
        ``redirect_uri`` parameter - not the actual URL. The mapping from
        RuName to URL lives in the eBay developer dashboard. For Listing
        Studio the RuName resolves to http://localhost:8731/api/ebay/oauth/callback.

        Returns None if app credentials or RuName are missing - the UI
        should disable the "Authorize" button in that state.
        """
        stored = creds.load_credentials(self.platform)
        if not stored:
            return None
        client_id = stored.get("client_id")
        ru_name = stored.get("ru_name")
        if not client_id or not ru_name:
            return None

        # eBay's OAuth only accepts: client_id, response_type, redirect_uri,
        # scope, state. Standard OAuth params like `prompt` cause eBay to
        # return "invalid_request: Input request parameters are invalid."
        params = {
            "client_id": client_id,
            "redirect_uri": ru_name,
            "response_type": "code",
            "scope": " ".join(EBAY_USER_SCOPES),
        }
        if state:
            params["state"] = state
        return f"{EBAY_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Trade an OAuth authorization code for access + refresh tokens.

        Called by the /api/ebay/oauth/callback endpoint right after eBay
        sends Dad's browser back to us with ?code=XXXX. On success, stores
        the tokens in the eBay credentials blob alongside the app creds.

        Returns the new credentials blob (for the caller to log/echo).
        Raises PostingError on failure with a human-readable message.
        """
        app = self._get_app_creds()
        if not app:
            raise PostingError(self.platform, "Missing app credentials", is_auth_error=True)
        client_id, client_secret = app

        stored = creds.load_credentials(self.platform) or {}
        ru_name = stored.get("ru_name")
        if not ru_name:
            raise PostingError(self.platform, "Missing RuName", is_auth_error=True)

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("ascii")

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    EBAY_OAUTH_TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": self.USER_AGENT,
                    },
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": ru_name,
                    },
                )
        except httpx.RequestError as exc:
            raise PostingError(
                self.platform, f"Network error during token exchange: {exc}",
            ) from exc

        if response.status_code != 200:
            raise PostingError(
                self.platform,
                f"eBay rejected the authorization code ({response.status_code}): {response.text[:300]}",
                is_auth_error=True,
            )

        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 7200))

        if not access_token or not refresh_token:
            raise PostingError(self.platform, "eBay token response missing tokens")

        # Compute absolute expiry timestamps for both tokens.
        access_expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        # eBay's refresh tokens are valid 18 months; we don't strictly need
        # to track expiry but it's useful for "you need to re-authorize" UI
        # someday.
        refresh_expires_at = (
            datetime.now() + timedelta(seconds=int(data.get("refresh_token_expires_in", 47304000)))
        ).isoformat()

        # Try to fetch the seller's user ID for a nice account label. Not
        # fatal if it fails - we have the token, that's the important bit.
        account_label = "eBay seller"
        try:
            label = await self._fetch_seller_username(access_token)
            if label:
                account_label = label
        except Exception as exc:  # noqa: BLE001
            logger.warning("Couldn't fetch eBay seller label: %s", exc)

        merged = {
            **stored,
            "user_access_token": access_token,
            "user_refresh_token": refresh_token,
            "user_token_expires_at": access_expires_at,
            "user_refresh_expires_at": refresh_expires_at,
            "account_label": account_label,
        }
        creds.store_credentials(self.platform, merged)
        return merged

    async def _refresh_user_token(self, client: httpx.AsyncClient) -> str:
        """Use the stored refresh token to get a fresh access token.

        Returns the new access token (also persists it in the credentials
        blob). Raises PostingError if no refresh token is stored or the
        refresh request fails.
        """
        stored = creds.load_credentials(self.platform) or {}
        refresh = stored.get("user_refresh_token")
        if not refresh:
            raise PostingError(
                self.platform,
                "No refresh token stored - the seller account needs to re-authorize.",
                is_auth_error=True,
            )

        app = self._get_app_creds()
        if not app:
            raise PostingError(self.platform, "Missing app credentials")
        client_id, client_secret = app
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("ascii")

        response = await client.post(
            EBAY_OAUTH_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.USER_AGENT,
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "scope": " ".join(EBAY_USER_SCOPES),
            },
        )

        if response.status_code != 200:
            raise PostingError(
                self.platform,
                f"eBay refresh failed ({response.status_code}): {response.text[:200]}",
                is_auth_error=True,
            )

        data = response.json()
        new_access = data.get("access_token")
        if not new_access:
            raise PostingError(self.platform, "eBay refresh response missing access_token")

        expires_in = int(data.get("expires_in", 7200))
        new_expiry = (datetime.now() + timedelta(seconds=expires_in)).isoformat()

        merged = {
            **stored,
            "user_access_token": new_access,
            "user_token_expires_at": new_expiry,
        }
        creds.store_credentials(self.platform, merged)
        return new_access

    async def _get_user_token(self, client: httpx.AsyncClient) -> str:
        """Return a usable user access token, refreshing if expired.

        Called by any code path that needs to act on the seller's behalf
        (inventory, offers, order reads).
        """
        stored = creds.load_credentials(self.platform) or {}
        access = stored.get("user_access_token")
        expires_at = stored.get("user_token_expires_at")

        if not access:
            raise PostingError(
                self.platform,
                "Seller account not authorized. Connect via Settings → eBay → Authorize Seller Account.",
                is_auth_error=True,
            )

        # Refresh if within 60s of expiry (safety buffer) or no expiry recorded
        needs_refresh = False
        if not expires_at:
            needs_refresh = True
        else:
            try:
                expiry_dt = datetime.fromisoformat(expires_at)
                if (expiry_dt - datetime.now()).total_seconds() < 60:
                    needs_refresh = True
            except ValueError:
                needs_refresh = True

        if needs_refresh:
            access = await self._refresh_user_token(client)

        return access

    async def _fetch_seller_username(self, access_token: str) -> str | None:
        """Pull the seller's username/ID for use as an account label."""
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self.BASE_URL}/commerce/identity/v1/user/",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "User-Agent": self.USER_AGENT,
                    },
                )
        except httpx.RequestError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        return data.get("username") or data.get("userId")

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
    # Business policies + merchant locations (required for offer creation)
    # ------------------------------------------------------------------

    async def fetch_business_policies(self) -> dict[str, list[dict]]:
        """Return the seller's payment, return, and fulfillment policies.

        Output shape (JSON-friendly for the API layer):
            {
                "fulfillment": [{"id": "...", "name": "..."}],
                "payment":     [{"id": "...", "name": "..."}],
                "return":      [{"id": "...", "name": "..."}],
            }

        Returns empty lists for any kind that's missing or fails to fetch -
        the offer creation step will surface a clear error if a required
        policy isn't set up in eBay Seller Hub.
        """
        if not self.has_user_token():
            return {"fulfillment": [], "payment": [], "return": []}

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            try:
                token = await self._get_user_token(client)
            except PostingError:
                return {"fulfillment": [], "payment": [], "return": []}

            results: dict[str, list[dict]] = {
                "fulfillment": [],
                "payment": [],
                "return": [],
            }

            # Each kind has the same shape: a list under the matching key
            endpoints = {
                "fulfillment": "/sell/account/v1/fulfillment_policy",
                "payment":     "/sell/account/v1/payment_policy",
                "return":      "/sell/account/v1/return_policy",
            }
            response_keys = {
                "fulfillment": "fulfillmentPolicies",
                "payment":     "paymentPolicies",
                "return":      "returnPolicies",
            }
            id_keys = {
                "fulfillment": "fulfillmentPolicyId",
                "payment":     "paymentPolicyId",
                "return":      "returnPolicyId",
            }

            for kind, path in endpoints.items():
                try:
                    response = await client.get(
                        f"{self.BASE_URL}{path}",
                        headers=self._bearer_headers(token),
                        params={"marketplace_id": EBAY_MARKETPLACE_ID},
                    )
                except httpx.RequestError as exc:
                    logger.warning("eBay %s policies fetch failed: %s", kind, exc)
                    continue
                if response.status_code != 200:
                    logger.warning(
                        "eBay %s policies returned %d: %s",
                        kind, response.status_code, response.text[:200],
                    )
                    continue
                data = response.json()
                for policy in data.get(response_keys[kind], []):
                    pid = policy.get(id_keys[kind])
                    name = policy.get("name") or "(unnamed)"
                    if pid:
                        results[kind].append({"id": str(pid), "name": name})

            return results

    async def create_merchant_location(
        self,
        key: str,
        name: str,
        address_line_1: str,
        city: str,
        state_or_province: str,
        postal_code: str,
        country: str = "US",
        address_line_2: str | None = None,
        location_type: str = "WAREHOUSE",
    ) -> None:
        """Create (or upsert) an inventory location on eBay.

        eBay's Inventory API requires every offer to reference a
        ``merchantLocationKey`` that's been registered for the seller.
        Many sellers don't have one because eBay's Seller Hub doesn't
        always expose a UI for this - the construct is API-only. This
        method lets the app create one directly so Dad doesn't have to
        wrestle with eBay's API Explorer.

        Args match eBay's address shape (US-only here; international
        would add region/county). Raises PostingError on failure.
        """
        if not self.has_user_token():
            raise PostingError(
                self.platform,
                "Seller account not authorized.",
                is_auth_error=True,
            )

        address: dict[str, str] = {
            "addressLine1": address_line_1,
            "city": city,
            "stateOrProvince": state_or_province,
            "postalCode": postal_code,
            "country": country,
        }
        if address_line_2:
            address["addressLine2"] = address_line_2

        payload = {
            "location": {"address": address},
            "name": name,
            "merchantLocationStatus": "ENABLED",
            "locationTypes": [location_type],
        }

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            token = await self._get_user_token(client)
            # POST to /location/{key} - eBay treats this as upsert by key.
            response = await client.post(
                f"{self.BASE_URL}/sell/inventory/v1/location/{key}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Content-Language": "en-US",
                    "Accept": "application/json",
                    "User-Agent": self.USER_AGENT,
                },
                json=payload,
            )

        # eBay returns 204 No Content on success
        if response.status_code not in (200, 201, 204):
            _raise_ebay_error(self.platform, "location creation", response)

    async def fetch_required_aspects(self, category_id: str | int) -> list[dict]:
        """Return the item aspect schema eBay defines for ``category_id``.

        Hits ``/commerce/taxonomy/v1/category_tree/{tree}/get_item_aspects_for_category``.
        Each aspect comes back as:

            {
                "name":      "Type",
                "required":  True,
                "values":    ["Bridge Pickup", "Neck Pickup", ...],  # may be empty
                "value_type": "STRING" | "STRING_ARRAY" | "NUMERIC",
                "is_variation": False
            }

        The eBay endpoint accepts the app token (read-only), so works
        without the user OAuth dance. Returns ``[]`` on any failure -
        the UI degrades to "just enter aspects manually" mode.
        """
        category_id = str(category_id)
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            try:
                token = await self._get_app_token(client)
            except PostingError as exc:
                logger.warning("eBay aspects: app token unavailable: %s", exc)
                return []
            url = (
                f"{self.BASE_URL}/commerce/taxonomy/v1/category_tree/"
                f"{EBAY_US_TREE_ID}/get_item_aspects_for_category"
            )
            try:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "User-Agent": self.USER_AGENT,
                    },
                    params={"category_id": category_id},
                )
            except httpx.RequestError as exc:
                logger.warning("eBay aspects request failed: %s", exc)
                return []
            if response.status_code != 200:
                logger.warning(
                    "eBay aspects for %s returned HTTP %d: %s",
                    category_id, response.status_code, response.text[:300],
                )
                return []

            data = response.json()
            out: list[dict] = []
            for asp in data.get("aspects") or []:
                name = asp.get("localizedAspectName") or asp.get("aspectName")
                if not name:
                    continue
                constraint = asp.get("aspectConstraint") or {}
                # Values list, if eBay constrains them.
                vals = []
                for vobj in asp.get("aspectValues") or []:
                    label = vobj.get("localizedValue") or vobj.get("value")
                    if label:
                        vals.append(label)
                out.append({
                    "name": name,
                    "required": bool(constraint.get("aspectRequired")),
                    "values": vals,
                    "value_type": constraint.get("aspectDataType") or "STRING",
                    "is_variation": bool(constraint.get("itemToAspectCardinality") == "MULTI"),
                    "max_length": constraint.get("aspectMaxLength"),
                })
            # Sort: required first, then alphabetical.
            out.sort(key=lambda a: (0 if a["required"] else 1, a["name"].lower()))
            return out

    async def fetch_merchant_locations(self) -> list[dict]:
        """Return the seller's inventory locations.

        Offers require a merchantLocationKey. Most sellers have exactly one
        (their warehouse / home). Returns ``[{key, name}]``; empty if none
        exist or the call fails.
        """
        if not self.has_user_token():
            return []
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            try:
                token = await self._get_user_token(client)
                response = await client.get(
                    f"{self.BASE_URL}/sell/inventory/v1/location",
                    headers=self._bearer_headers(token),
                )
            except (PostingError, httpx.RequestError) as exc:
                logger.warning("eBay locations fetch failed: %s", exc)
                return []
            if response.status_code != 200:
                logger.warning("eBay locations returned %d", response.status_code)
                return []
            data = response.json()
            out = []
            for loc in data.get("locations", []):
                key = loc.get("merchantLocationKey")
                name = loc.get("name") or loc.get("location", {}).get("address", {}).get("city") or "(location)"
                if key:
                    out.append({"key": key, "name": name})
            return out

    # ------------------------------------------------------------------
    # Preview helpers (inventory_item + offer fetch by SKU/offerId)
    # ------------------------------------------------------------------

    async def fetch_inventory_and_offer(self, sku: str) -> dict[str, Any]:
        """Pull the current inventory_item and matching offer for a SKU.

        Returns a dict like::

            {
                "inventory": {...} | None,   # eBay inventory_item JSON, if found
                "offer":     {...} | None,   # most recent offer for the SKU, if any
                "errors":    ["..."]         # human-readable fetch warnings
            }

        Used by the in-app preview view: Seller Hub doesn't render
        unpublished Inventory API offers, so we render our own preview
        from this data.
        """
        result: dict[str, Any] = {"inventory": None, "offer": None, "errors": []}
        if not self.has_user_token():
            result["errors"].append("eBay seller account not authorized.")
            return result

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            try:
                token = await self._get_user_token(client)
            except PostingError as exc:
                result["errors"].append(f"token refresh failed: {exc}")
                return result
            headers = self._bearer_headers(token)

            # ---- inventory_item GET (eBay's read endpoint is flaky; retry once) ----
            import asyncio as _asyncio
            for attempt in (1, 2):
                try:
                    rb_inv = await client.get(
                        f"{self.BASE_URL}/sell/inventory/v1/inventory_item/{sku}",
                        headers=headers,
                    )
                    if rb_inv.status_code == 200:
                        result["inventory"] = rb_inv.json()
                        break
                    elif rb_inv.status_code == 404:
                        result["errors"].append(f"No inventory_item for SKU {sku} on eBay.")
                        break
                    else:
                        result["errors"].append(
                            f"inventory_item GET attempt {attempt} returned {rb_inv.status_code}"
                        )
                except Exception as exc:  # noqa: BLE001
                    result["errors"].append(f"inventory_item GET attempt {attempt} failed: {exc}")
                if attempt == 1:
                    await _asyncio.sleep(1.5)

            # ---- offer lookup by SKU ----
            try:
                lookup = await client.get(
                    f"{self.BASE_URL}/sell/inventory/v1/offer",
                    headers=headers,
                    params={"sku": sku, "marketplace_id": EBAY_MARKETPLACE_ID, "limit": "5"},
                )
                if lookup.status_code == 200:
                    offers = lookup.json().get("offers") or []
                    # Prefer UNPUBLISHED; fall back to whatever's there.
                    preferred = next(
                        (o for o in offers if o.get("status") == "UNPUBLISHED"),
                        offers[0] if offers else None,
                    )
                    result["offer"] = preferred
                elif lookup.status_code == 404:
                    result["errors"].append(f"No offer for SKU {sku} on eBay.")
                else:
                    result["errors"].append(f"offer lookup returned {lookup.status_code}")
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"offer lookup failed: {exc}")

        return result

    # ------------------------------------------------------------------
    # Publish an unpublished offer
    # ------------------------------------------------------------------

    async def publish_offer(self, offer_id: str) -> dict[str, Any]:
        """Publish an unpublished offer, converting it to a live listing.

        Returns::

            {"listing_id": "...", "url": "https://www.ebay.com/itm/<id>"}

        Raises PostingError on failure. Note: publishing a listing is
        irreversible in the sense that the listing becomes immediately
        visible on eBay (you can withdraw it via DELETE on the listing,
        but it counts toward your insertion fee allowance).
        """
        if not self.has_user_token():
            raise PostingError(
                self.platform,
                "Seller account not authorized.",
                is_auth_error=True,
            )

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            token = await self._get_user_token(client)
            headers = self._bearer_headers(token)
            headers["Content-Type"] = "application/json"
            headers["Content-Language"] = "en-US"

            response = await client.post(
                f"{self.BASE_URL}/sell/inventory/v1/offer/{offer_id}/publish",
                headers=headers,
            )

        if response.status_code not in (200, 201):
            _raise_ebay_error(self.platform, "offer publish", response)

        data = response.json()
        listing_id = data.get("listingId")
        url = f"https://www.ebay.com/itm/{listing_id}" if listing_id else "https://www.ebay.com/sh/lst/active"
        return {"listing_id": listing_id, "url": url, "raw": data}

    # ------------------------------------------------------------------
    # Draft listing creation (inventory_item + offer, unpublished)
    # ------------------------------------------------------------------

    async def create_draft(
        self,
        template,
        photo_urls: list[str] | None = None,
        fulfillment_policy_id: str | None = None,
        payment_policy_id: str | None = None,
        return_policy_id: str | None = None,
        merchant_location_key: str | None = None,
    ) -> dict[str, Any]:
        """Create an unpublished eBay offer (draft) from a template.

        Two API calls:
          1. PUT /sell/inventory/v1/inventory_item/{sku} - upserts the product
          2. POST /sell/inventory/v1/offer - creates the unpublished offer

        We deliberately skip the publish step so the seller can review in
        Seller Hub before going live - same pattern as Reverb's drafts.

        Returns:
            {
                "sku": "ls-NNN",
                "offer_id": "...",
                "url": "https://www.ebay.com/sh/lst/drafts",
                "raw_inventory": {...},
                "raw_offer": {...}
            }

        Raises PostingError with a human-readable detail on any failure.
        eBay's validation messages are verbose; we surface the first one
        in the message and stash the rest in the raised exception.
        """
        if not self.has_user_token():
            raise PostingError(
                self.platform,
                "Seller account not authorized. Connect via Settings → eBay → Authorize Seller Account.",
                is_auth_error=True,
            )

        category_id = getattr(template, "ebay_category_id", None)
        if not category_id:
            raise PostingError(
                self.platform,
                "No eBay category set on this template's Category. Open Categories and pick an eBay leaf.",
            )

        # SKU: stable per-template ID so PUT inventory_item upserts cleanly.
        sku = f"ls-{template.id}"
        price_value = f"{template.base_price_cents / 100:.2f}"
        condition_id = EBAY_CONDITION_IDS.get(template.condition, 1500)

        # eBay wants HTML in listingDescription. The template's description
        # is plaintext-ish; wrap newlines and double-newlines in <br>/<p>
        # so it renders cleanly in eBay's preview.
        #
        # IMPORTANT: escape user-supplied text before wrapping in tags. An
        # unescaped `<`, `&`, or stray angle bracket in Dad's description
        # surfaces as a confusing "Core Inventory Service internal error"
        # from eBay's HTML parser rather than a useful validation message.
        raw_desc = (template.description or "").strip()
        if raw_desc:
            paragraphs = [p.strip() for p in raw_desc.split("\n\n") if p.strip()]
            description_html = "".join(
                f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>"
                for p in paragraphs
            )
        else:
            description_html = f"<p>{html.escape(template.title or '')}</p>"

        # Item specifics ("aspects" in eBay's vocabulary). Start with our
        # auto-derived Brand/MPN/Model from the template's basic fields,
        # then layer the user-edited template.item_specifics on top (user
        # value wins). eBay's required aspects vary per category - the UI
        # lets the user fetch the schema and fill the required ones.
        aspects: dict[str, list[str]] = {}
        if template.brand:
            aspects["Brand"] = [template.brand]
        if getattr(template, "model", None):
            aspects["MPN"] = [str(template.model)]
            aspects["Model"] = [str(template.model)]

        user_aspects = getattr(template, "item_specifics", None) or {}
        if isinstance(user_aspects, dict):
            for key, value in user_aspects.items():
                if value in (None, "", []):
                    continue
                if isinstance(value, list):
                    cleaned = [str(v).strip() for v in value if str(v).strip()]
                else:
                    cleaned = [str(value).strip()] if str(value).strip() else []
                if cleaned:
                    aspects[str(key).strip()] = cleaned

        # ---- Step 1: PUT inventory item (upsert by SKU) ----
        inventory_payload = {
            "availability": {
                "shipToLocationAvailability": {"quantity": int(template.quantity or 1)},
            },
            "condition": _condition_enum_for_id(condition_id),
            "product": {
                "title": (template.title or template.name)[:80],  # eBay caps at 80
                "description": description_html,
                "aspects": aspects,
                "imageUrls": list(photo_urls or []),
            },
        }
        # MPN is also a product-level field, not just an aspect
        if getattr(template, "model", None):
            inventory_payload["product"]["mpn"] = str(template.model)
        if template.brand:
            inventory_payload["product"]["brand"] = template.brand

        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            token = await self._get_user_token(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Language": "en-US",  # required for inventory_item endpoint
                "Accept": "application/json",
                "User-Agent": self.USER_AGENT,
            }

            # Log the exact inventory_item payload going out. We had a case
            # where the API call succeeded but the resulting Seller Hub
            # draft was missing description/photos/aspects - this log lets
            # us confirm what we sent vs. what eBay stored.
            try:
                logger.info(
                    "eBay inventory_item PUT %s payload:\n%s",
                    sku,
                    json.dumps(inventory_payload, indent=2)[:4000],
                )
            except Exception:
                pass

            inv_response = await client.put(
                f"{self.BASE_URL}/sell/inventory/v1/inventory_item/{sku}",
                headers=headers,
                json=inventory_payload,
            )
            if inv_response.status_code not in (200, 201, 204):
                _raise_ebay_error(self.platform, "inventory item upsert", inv_response)

            # Read back the inventory_item to confirm eBay stored what we
            # sent. 204 means "accepted, no body returned" - the only way
            # to verify the data is to GET it. eBay's GET endpoint is
            # known to throw 500 right after a PUT (eventual consistency);
            # retry once after a short delay before giving up.
            readback_inventory: dict[str, Any] = {}
            inv_readback_status: int | None = None
            import asyncio as _asyncio
            for attempt in (1, 2):
                try:
                    rb_inv = await client.get(
                        f"{self.BASE_URL}/sell/inventory/v1/inventory_item/{sku}",
                        headers=headers,
                    )
                    inv_readback_status = rb_inv.status_code
                    if rb_inv.status_code == 200:
                        readback_inventory = rb_inv.json()
                        logger.info(
                            "eBay inventory_item GET %s readback (attempt %d):\n%s",
                            sku,
                            attempt,
                            json.dumps(readback_inventory, indent=2)[:4000],
                        )
                        break
                    logger.warning(
                        "eBay inventory_item readback attempt %d returned HTTP %d: %s",
                        attempt,
                        rb_inv.status_code,
                        rb_inv.text[:500],
                    )
                except Exception as exc:  # noqa: BLE001 - diagnostic only
                    logger.warning(
                        "eBay inventory_item readback attempt %d failed: %s",
                        attempt,
                        exc,
                    )
                if attempt == 1:
                    await _asyncio.sleep(1.5)

            # ---- Step 2: POST offer (unpublished) ----
            offer_payload: dict[str, Any] = {
                "sku": sku,
                "marketplaceId": EBAY_MARKETPLACE_ID,
                "format": "FIXED_PRICE",
                "availableQuantity": int(template.quantity or 1),
                "categoryId": str(category_id),
                "listingDescription": description_html,
                "pricingSummary": {
                    "price": {"currency": "USD", "value": price_value},
                },
                # CRITICAL: when true (eBay's default), if our brand+MPN
                # match anything in eBay's catalog, eBay overlays the
                # catalog product's data (including title, photos, aspects)
                # on top of ours - which can silently zero out our content.
                # Setting false keeps our submitted data authoritative.
                "includeCatalogProductDetails": False,
            }

            # Business policies + location. eBay rejects the offer if any
            # of these are missing.
            policies: dict[str, str] = {}
            if fulfillment_policy_id:
                policies["fulfillmentPolicyId"] = fulfillment_policy_id
            if payment_policy_id:
                policies["paymentPolicyId"] = payment_policy_id
            if return_policy_id:
                policies["returnPolicyId"] = return_policy_id
            if policies:
                offer_payload["listingPolicies"] = policies
            if merchant_location_key:
                offer_payload["merchantLocationKey"] = merchant_location_key

            # Per-template shipping override. The fulfillment policy sets the
            # default; this lets a single listing override the domestic
            # shipping cost (e.g. "free shipping on this item" or "flat $X
            # because this one's heavier"). The override is scoped to the
            # FIRST shipping service in the policy (priority=1).
            ebay_ship_type = getattr(template, "ebay_shipping_type", None)
            ebay_ship_cents = getattr(template, "ebay_shipping_override_cents", 0) or 0
            override_value: str | None = None
            if ebay_ship_type == "free":
                override_value = "0.00"
            elif ebay_ship_type == "flat" and ebay_ship_cents >= 0:
                override_value = f"{ebay_ship_cents / 100:.2f}"
            if override_value is not None:
                offer_payload["shippingCostOverrides"] = [{
                    "priority": 1,
                    "shippingCost": {"currency": "USD", "value": override_value},
                    "shippingServiceType": "DOMESTIC",
                }]

            try:
                logger.info(
                    "eBay offer payload (will upsert by SKU):\n%s",
                    json.dumps(offer_payload, indent=2)[:4000],
                )
            except Exception:
                pass

            # ---- Offer upsert: check for existing offer for this SKU ----
            # eBay's offer endpoint is NOT an upsert via POST - it returns
            # 25002 "Offer entity already exists" if you POST when one is
            # already there. Inventory_item PUT is a true upsert; offer is
            # GET-then-(PUT-or-POST).
            existing_offer_id: str | None = None
            try:
                lookup_response = await client.get(
                    f"{self.BASE_URL}/sell/inventory/v1/offer",
                    headers=headers,
                    params={"sku": sku, "marketplace_id": EBAY_MARKETPLACE_ID, "limit": "5"},
                )
                if lookup_response.status_code == 200:
                    offers = lookup_response.json().get("offers") or []
                    for off in offers:
                        # Match on SKU + marketplace, prefer UNPUBLISHED so
                        # we don't accidentally PUT over a live listing.
                        if off.get("sku") == sku:
                            existing_offer_id = off.get("offerId")
                            if off.get("status") == "UNPUBLISHED":
                                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("eBay offer lookup failed (will fall back to POST): %s", exc)

            if existing_offer_id:
                logger.info("eBay offer exists for SKU %s (offerId=%s); PUT to update.",
                            sku, existing_offer_id)
                offer_response = await client.put(
                    f"{self.BASE_URL}/sell/inventory/v1/offer/{existing_offer_id}",
                    headers=headers,
                    json=offer_payload,
                )
                if offer_response.status_code not in (200, 204):
                    _raise_ebay_error(self.platform, "offer update", offer_response)
                # PUT returns 204 with no body; we already have the ID.
                if offer_response.status_code == 204 or not offer_response.text.strip():
                    offer_data = {"offerId": existing_offer_id}
                else:
                    offer_data = offer_response.json()
            else:
                offer_response = await client.post(
                    f"{self.BASE_URL}/sell/inventory/v1/offer",
                    headers=headers,
                    json=offer_payload,
                )
                if offer_response.status_code not in (200, 201):
                    # Special-case 25002: an offer for this SKU now exists
                    # but we missed it in the lookup (race or filter issue).
                    # Parse offerId out of the error parameters and PUT.
                    retry_id = _extract_existing_offer_id(offer_response)
                    if retry_id:
                        logger.info(
                            "eBay POST /offer hit 25002; retrying as PUT /offer/%s",
                            retry_id,
                        )
                        offer_response = await client.put(
                            f"{self.BASE_URL}/sell/inventory/v1/offer/{retry_id}",
                            headers=headers,
                            json=offer_payload,
                        )
                        if offer_response.status_code not in (200, 204):
                            _raise_ebay_error(self.platform, "offer update (retry)", offer_response)
                        offer_data = (
                            {"offerId": retry_id}
                            if offer_response.status_code == 204 or not offer_response.text.strip()
                            else offer_response.json()
                        )
                    else:
                        _raise_ebay_error(self.platform, "offer creation", offer_response)
                else:
                    offer_data = offer_response.json()

            offer_id = offer_data.get("offerId")

            # Read back the offer to confirm eBay stored what we sent.
            readback_offer: dict[str, Any] = {}
            if offer_id:
                try:
                    rb_off = await client.get(
                        f"{self.BASE_URL}/sell/inventory/v1/offer/{offer_id}",
                        headers=headers,
                    )
                    if rb_off.status_code == 200:
                        readback_offer = rb_off.json()
                        logger.info(
                            "eBay offer GET %s readback:\n%s",
                            offer_id,
                            json.dumps(readback_offer, indent=2)[:4000],
                        )
                    else:
                        logger.warning(
                            "eBay offer readback returned HTTP %d: %s",
                            rb_off.status_code,
                            rb_off.text[:500],
                        )
                except Exception as exc:  # noqa: BLE001 - diagnostic only
                    logger.warning("eBay offer readback failed: %s", exc)

        # Build a concise "stored summary" for the UI so the user can see
        # at a glance whether eBay actually has the rich fields. If these
        # are populated but Seller Hub's drafts page shows them blank,
        # it's a Seller Hub UI issue, not our problem.
        stored_inv_product = readback_inventory.get("product", {}) if readback_inventory else {}
        stored_summary = {
            "inventory_title": stored_inv_product.get("title"),
            "inventory_description_len": len(stored_inv_product.get("description") or ""),
            "inventory_image_count": len(stored_inv_product.get("imageUrls") or []),
            "inventory_aspect_count": len(stored_inv_product.get("aspects") or {}),
            "inventory_condition": readback_inventory.get("condition") if readback_inventory else None,
            # When eBay's inventory_item GET returns 500 (their known flaky
            # endpoint), the inventory_* fields above will look empty even
            # though the data IS stored. The UI uses this to tell the user
            # "eBay's GET hiccupped" instead of "your data is missing".
            "inventory_readback_status": inv_readback_status,
            "offer_category_id": (readback_offer.get("categoryId") if readback_offer else None),
            "offer_description_len": len(readback_offer.get("listingDescription") or "") if readback_offer else 0,
            "offer_price": (readback_offer.get("pricingSummary") or {}).get("price") if readback_offer else None,
            "offer_status": readback_offer.get("status") if readback_offer else None,
        }
        logger.info("eBay create_draft stored summary: %s", stored_summary)

        return {
            "sku": sku,
            "offer_id": offer_id,
            # Inventory API offers don't appear in the legacy Seller Hub
            # "Drafts" view in full detail. The Inventory/Listings page
            # is the right place to find them - linking there now.
            "url": f"https://www.ebay.com/sh/lst/active?action=edit_offer&offerId={offer_id}" if offer_id else "https://www.ebay.com/sh/lst/active",
            "raw_inventory": {"status": inv_response.status_code},
            "raw_offer": offer_data,
            "stored_summary": stored_summary,
        }

    # ------------------------------------------------------------------
    # PlatformConnector abstract methods (for the cross-post pipeline)
    # ------------------------------------------------------------------

    async def post(self, template: Template, price_cents: int, quantity: int) -> PostOutcome:
        # Cross-post pipeline override: mutate locally, call create_draft.
        # Photos and policies must be wired by the API layer (mirror of the
        # Reverb pattern in post_template_to_reverb).
        raise PostingError(
            self.platform,
            "eBay direct cross-post not implemented yet - use the per-template Post eBay Draft button.",
        )

    async def update_inventory(self, external_listing_id: str, new_quantity: int) -> bool:
        return False

    async def fetch_recent_orders(self, since: datetime) -> list[dict]:
        return []


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _condition_enum_for_id(condition_id: int) -> str:
    """Translate the numeric condition ID to eBay's inventory_item enum.

    The Inventory API's inventory_item endpoint wants the string form
    (NEW, NEW_OTHER, USED, FOR_PARTS_OR_NOT_WORKING, etc.). Other
    sell endpoints use the numeric ID. We pass both - this maps the
    common ones; less common conditions fall back to USED.
    """
    return {
        1000: "NEW",
        1500: "NEW_OTHER",
        1750: "NEW_WITH_DEFECTS",
        2000: "MANUFACTURER_REFURBISHED",
        2500: "SELLER_REFURBISHED",
        3000: "USED_EXCELLENT",
        4000: "USED_VERY_GOOD",
        5000: "USED_GOOD",
        6000: "USED_ACCEPTABLE",
        7000: "FOR_PARTS_OR_NOT_WORKING",
    }.get(condition_id, "USED_EXCELLENT")


def _extract_existing_offer_id(response: httpx.Response) -> str | None:
    """If response is eBay's 25002 'Offer entity already exists' error, return
    the offerId from its `parameters` array. Otherwise return None.
    """
    try:
        data = response.json()
    except Exception:
        return None
    for err in data.get("errors") or []:
        if err.get("errorId") == 25002:
            for p in err.get("parameters") or []:
                if p.get("name") == "offerId" and p.get("value"):
                    return p["value"]
    return None


def _raise_ebay_error(platform, step: str, response: httpx.Response) -> None:
    """Translate an eBay error response into a PostingError with a useful message.

    eBay's error JSON shape:
        {"errors": [{"errorId": N, "message": "...", "longMessage": "...", "parameters": [...]}]}

    We pull the first error's message into the exception text. Additional
    errors get appended in parentheses so the user sees a complete picture
    without us needing a structured renderer.

    We ALSO dump the full error JSON to the log so that when eBay's primary
    message is unhelpful (e.g. "Core Inventory Service internal error"),
    we can still see the underlying `parameters` array — that's where eBay
    actually tells us which field/aspect/value it choked on.
    """
    try:
        data = response.json()
    except Exception:
        logger.error(
            "eBay %s: non-JSON error response HTTP %d: %s",
            step,
            response.status_code,
            response.text[:1000],
        )
        raise PostingError(
            Platform.EBAY,
            f"eBay {step} returned HTTP {response.status_code}: {response.text[:300]}",
        )

    # Always log the full response so we never lose error context to the
    # short user-visible message. Truncated at 4KB just in case eBay returns
    # something gigantic.
    try:
        full_dump = json.dumps(data, indent=2)[:4000]
    except Exception:
        full_dump = str(data)[:4000]
    logger.error("eBay %s failed (HTTP %d). Full response:\n%s",
                 step, response.status_code, full_dump)

    errors = data.get("errors") or []
    if not errors:
        raise PostingError(
            Platform.EBAY,
            f"eBay {step} returned HTTP {response.status_code} with no error detail",
        )

    primary = errors[0]
    msg = primary.get("longMessage") or primary.get("message") or "unknown"

    # eBay puts the actual problem field in `parameters`. For an "internal
    # error" that's the only useful breadcrumb. Append the first 2 params
    # to the user-visible message so Dad doesn't have to crack open the log
    # to know which field is unhappy.
    params = primary.get("parameters") or []
    if params:
        param_bits = []
        for p in params[:3]:
            name = p.get("name") or "?"
            value = (p.get("value") or "")[:60]
            param_bits.append(f"{name}={value}" if value else name)
        msg = f"{msg} [eBay params: {'; '.join(param_bits)}]"

    if len(errors) > 1:
        extras = ", ".join(
            (e.get("message") or "?")[:80] for e in errors[1:4]
        )
        msg = f"{msg} (additional: {extras})"

    raise PostingError(
        Platform.EBAY,
        f"eBay {step} failed: {msg}",
        is_auth_error=(primary.get("errorId") in (1001, 1002, 1003, 1100)),
    )


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

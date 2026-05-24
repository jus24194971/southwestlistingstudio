"""FastAPI application: API the UI calls from JavaScript.

Routes:
  GET    /api/health                       - simple ping
  GET    /api/templates                    - all templates (grouped by folder)
  GET    /api/templates/{id}               - one template, with photos
  POST   /api/templates                    - create template
  PATCH  /api/templates/{id}               - update template
  DELETE /api/templates/{id}               - delete template
  POST   /api/post                         - the 'Post Listing' button
  GET    /api/settings/platforms           - platform connection statuses

Static files (HTML/CSS/JS) are mounted at /.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from listing_studio import __app_name__, __brand_name__, __version__
from listing_studio.core import templates as templates_repo
from listing_studio.core.credentials import account_label, expires_in, is_connected
from listing_studio.core.db import session_scope
from listing_studio.core.models import Platform
from listing_studio.core.posting import post_to_platforms
from listing_studio.core.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    PlatformConnectionStatus,
    PostRequest,
    PostResponse,
    TemplateCreate,
    TemplateOut,
    TemplateSummary,
    TemplateUpdate,
)

# Paths to the static UI files relative to this package
_UI_DIR = Path(__file__).parent
_STATIC_DIR = _UI_DIR / "static"
_TEMPLATES_DIR = _UI_DIR / "templates"

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description=f"{__app_name__} backend API. Used by the in-window UI; not intended for external clients.",
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": __app_name__,
        "brand": __brand_name__,
        "version": __version__,
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@app.get("/api/templates", response_model=dict[str, list[TemplateSummary]])
async def list_templates_grouped() -> dict[str, list[TemplateSummary]]:
    """Return all templates grouped by folder, lightweight."""
    with session_scope() as session:
        grouped = templates_repo.list_templates_by_folder(session)
        return {
            folder: [TemplateSummary.model_validate(t) for t in tmpls]
            for folder, tmpls in grouped.items()
        }


@app.get("/api/templates/{template_id}", response_model=TemplateOut)
async def get_template(template_id: int) -> TemplateOut:
    """Return one template with photos."""
    with session_scope() as session:
        tmpl = templates_repo.get_template(session, template_id)
        if tmpl is None:
            raise HTTPException(404, f"Template {template_id} not found")
        # Eagerly materialize before session close
        return TemplateOut.model_validate(tmpl)


@app.post("/api/templates", response_model=TemplateOut, status_code=201)
async def create_template(payload: TemplateCreate) -> TemplateOut:
    with session_scope() as session:
        tmpl = templates_repo.create_template(session, payload)
        session.flush()
        return TemplateOut.model_validate(tmpl)


@app.patch("/api/templates/{template_id}", response_model=TemplateOut)
async def update_template(template_id: int, payload: TemplateUpdate) -> TemplateOut:
    with session_scope() as session:
        tmpl = templates_repo.update_template(session, template_id, payload)
        if tmpl is None:
            raise HTTPException(404, f"Template {template_id} not found")
        return TemplateOut.model_validate(tmpl)


@app.delete("/api/templates/{template_id}", status_code=204)
async def delete_template(template_id: int) -> None:
    with session_scope() as session:
        deleted = templates_repo.delete_template(session, template_id)
        if not deleted:
            raise HTTPException(404, f"Template {template_id} not found")


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


@app.post("/api/post", response_model=PostResponse)
async def post_listing(request: PostRequest) -> PostResponse:
    """Post a template to one or more platforms.

    Returns per-platform results (success/failure URLs, errors) plus the
    Facebook copy-paste package if Facebook was one of the targets.
    """
    try:
        return await post_to_platforms(request)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.get("/api/settings/platforms", response_model=list[PlatformConnectionStatus])
async def list_platform_connections() -> list[PlatformConnectionStatus]:
    """Status of each platform's connection - feeds the settings screen."""
    statuses: list[PlatformConnectionStatus] = []
    for platform in Platform:
        connected = is_connected(platform)
        td = expires_in(platform)
        statuses.append(
            PlatformConnectionStatus(
                platform=platform,
                is_connected=connected,
                account_label=account_label(platform),
                token_expires_at=None,  # TODO: convert td to absolute time
                last_used_at=None,  # TODO: pull from posts table
                error=None,
            )
        )
    return statuses


@app.post("/api/settings/platforms/{platform_value}/disconnect", status_code=204)
async def disconnect_platform(platform_value: str) -> None:
    """Remove stored credentials for a platform (settings 'Disconnect' button)."""
    from listing_studio.core.credentials import clear_credentials

    try:
        platform = Platform(platform_value)
    except ValueError as exc:
        raise HTTPException(404, f"Unknown platform: {platform_value}") from exc

    clear_credentials(platform)


@app.get("/api/settings/preferences")
async def get_preferences() -> dict:
    """Return all user preferences (defaults from config, overrides from DB)."""
    from listing_studio.core.preferences import get_all_preferences

    with session_scope() as session:
        return get_all_preferences(session)


@app.patch("/api/settings/preferences")
async def update_preferences(values: dict) -> dict:
    """Update one or more preferences. Body is a dict of key->value.

    Unknown keys are ignored. Returns the full updated preferences dict.
    """
    from listing_studio.core.preferences import get_all_preferences, set_preferences

    with session_scope() as session:
        set_preferences(session, values)
        session.flush()
        return get_all_preferences(session)


# ---------------------------------------------------------------------------
# Fee estimates (for the form panel's per-platform price rows)
# ---------------------------------------------------------------------------


@app.get("/api/posts/history")
async def get_post_history(limit: int = 100) -> list[dict]:
    """Return recent post attempts grouped by batch.

    A "batch" here is one Post Listing click - it produces multiple Post rows
    (one per platform). We collapse them back into a single history item with
    a list of per-platform results.

    Returns newest first. The frontend re-groups them by date for display.
    """
    from listing_studio.core.models import Post, Template

    with session_scope() as session:
        # Pull recent posts. We group by (template_id, started_at rounded to minute)
        # as a proxy for "same batch" - all rows from one POST /api/post share a
        # template and were created within milliseconds of each other.
        stmt = (
            select(Post, Template.name)
            .join(Template, Template.id == Post.template_id)
            .order_by(Post.started_at.desc())
            .limit(limit * 5)  # over-fetch since we'll group
        )
        rows = session.execute(stmt).all()

        # Bucket by (template_id, minute timestamp)
        batches: dict[tuple, dict] = {}
        for post, template_name in rows:
            # Round to nearest minute for batch grouping
            minute_key = post.started_at.replace(second=0, microsecond=0)
            key = (post.template_id, minute_key)

            if key not in batches:
                batches[key] = {
                    "template_id": post.template_id,
                    "template_name": template_name,
                    "started_at": post.started_at.isoformat(),
                    "results": [],
                }

            elapsed_ms = None
            if post.completed_at is not None:
                delta = post.completed_at - post.started_at
                elapsed_ms = int(delta.total_seconds() * 1000)

            batches[key]["results"].append({
                "platform": post.platform.value,
                "status": post.status.value,
                "price_cents": post.price_cents,
                "external_listing_url": post.external_listing_url,
                "external_listing_id": post.external_listing_id,
                "error_message": post.error_message,
                "elapsed_ms": elapsed_ms,
            })

        # Sort by started_at desc, return at most `limit` batches
        items = sorted(batches.values(), key=lambda b: b["started_at"], reverse=True)
        return items[:limit]


@app.get("/api/fees")
async def get_fee_structures() -> dict[str, dict]:
    """Return fee descriptions for all platforms.

    The frontend uses this to render the "fee ~$X.XX · net $Y.YY" hints.
    Static data so we serve it as a single call rather than per-platform.
    """
    from listing_studio.core.fees import get_fee_structure

    out: dict[str, dict] = {}
    for platform in Platform:
        fee = get_fee_structure(platform)
        out[platform.value] = {
            "percentage_bps": fee.percentage_bps,
            "flat_cents": fee.flat_cents,
            "listing_cents": fee.listing_cents,
            "description": fee.description,
        }
    return out


@app.post("/api/settings/platforms/squarespace/connect")
async def connect_squarespace(payload: dict) -> dict:
    """Validate a Squarespace API key and save it on success.

    Body: ``{"api_key": "<the key>"}``

    Tests the key, stores it in the OS keyring on success along with the
    detected account label for display.
    """
    return await _connect_with_api_key(Platform.SQUARESPACE, payload)


@app.post("/api/settings/platforms/reverb/connect")
async def connect_reverb(payload: dict) -> dict:
    """Validate a Reverb personal access token and save it on success.

    Body: ``{"api_key": "<the token>"}``
    """
    return await _connect_with_api_key(Platform.REVERB, payload)


@app.post("/api/settings/platforms/ebay/connect")
async def connect_ebay(payload: dict) -> dict:
    """Save eBay app credentials and verify them.

    Body shape (all three required):
        {
            "client_id":     "...",  // App ID from the eBay dev dashboard
            "client_secret": "...",  // Cert ID
            "ru_name":       "..."   // Redirect User Name (associated with our
                                      // localhost callback URL in eBay's dashboard)
        }

    Verifies the client_id/secret by fetching an app-only OAuth token.
    The user OAuth dance (which authorizes Dad's actual seller account) is
    a separate step: GET /api/ebay/oauth/start, callback at
    /api/ebay/oauth/callback. Until that runs, the eBay connection is
    "app-only" and lets us read the taxonomy but not post listings.
    """
    from listing_studio.core.credentials import (
        clear_credentials,
        store_credentials,
    )
    from listing_studio.platforms.ebay import EbayConnector

    client_id = (payload.get("client_id") or "").strip()
    client_secret = (payload.get("client_secret") or "").strip()
    ru_name = (payload.get("ru_name") or "").strip()

    if not client_id or not client_secret or not ru_name:
        raise HTTPException(400, "All three fields (client_id, client_secret, ru_name) are required")

    # Save first so the connector can read them during the test
    try:
        store_credentials(Platform.EBAY, {
            "client_id": client_id,
            "client_secret": client_secret,
            "ru_name": ru_name,
        })
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    connector = EbayConnector()
    ok, label_or_error = await connector.test_connection()

    if not ok:
        clear_credentials(Platform.EBAY)
        raise HTTPException(400, f"eBay rejected the credentials: {label_or_error}")

    # Save with the label that the test produced; keep the three input fields.
    store_credentials(Platform.EBAY, {
        "client_id": client_id,
        "client_secret": client_secret,
        "ru_name": ru_name,
        "account_label": label_or_error,
    })
    return {
        "is_connected": True,
        "account_label": label_or_error,
        "has_user_token": False,
        "next_step": "Authorize Dad's seller account via /api/ebay/oauth/start",
    }


@app.get("/api/settings/platforms/ebay/oauth-status")
async def ebay_oauth_status() -> dict:
    """Quick poll endpoint for the UI's "Waiting for callback..." spinner.

    Returns whether a user token is currently stored (the OAuth callback
    completed) and the account label so the UI can update without
    reloading the whole platforms list.
    """
    from listing_studio.core.credentials import load_credentials
    from listing_studio.platforms.ebay import EbayConnector

    connector = EbayConnector()
    stored = load_credentials(Platform.EBAY) or {}
    return {
        "app_connected": await connector.is_connected(),
        "has_user_token": connector.has_user_token(),
        "account_label": stored.get("account_label"),
    }


@app.get("/api/ebay/oauth/start")
async def ebay_oauth_start() -> dict:
    """Open the eBay consent screen in the user's default browser.

    Constructs the authorize URL from the stored client_id + ru_name and
    opens it via the OS browser handler. Returns immediately - the actual
    redirect comes back to /api/ebay/oauth/callback later (potentially
    minutes later if Dad takes his time on the consent screen).

    Response shape:
        {"opened": true, "url": "https://auth.ebay.com/oauth2/authorize?..."}
    """
    import webbrowser

    from listing_studio.platforms.ebay import EbayConnector

    connector = EbayConnector()
    auth_url = connector.build_authorize_url()
    if not auth_url:
        raise HTTPException(400, "eBay app credentials not configured. Connect first.")

    try:
        opened = webbrowser.open(auth_url, new=2)  # new=2 means new tab if possible
    except Exception as exc:  # noqa: BLE001 - webbrowser is platform-dependent
        import logging
        logging.getLogger(__name__).warning("Couldn't open browser for eBay OAuth: %s", exc)
        opened = False

    return {"opened": bool(opened), "url": auth_url}


@app.get("/api/ebay/oauth/callback")
async def ebay_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
):
    """Handle eBay's redirect after Dad approves (or denies) the consent.

    eBay redirects here with ``?code=XXXX`` (success) or ``?error=...``
    (failure). On success we exchange the code for user tokens and store
    them. Returns an HTML page that tells Dad to close the tab and switch
    back to Listing Studio - the running app will see the stored tokens
    on its next poll of /api/settings/platforms.

    This endpoint exists because eBay's RuName-to-URL mapping is configured
    in the dev dashboard to point at http://localhost:8731/api/ebay/oauth/callback.

    Defensive code recovery: in the wild we saw cases where the URL the
    browser navigated to ended up as ``?=value&expires_in=...`` (no
    ``code=`` prefix) - either due to manual URL editing during
    troubleshooting or an edge case in browser handling of the worker's
    bounce HTML. eBay OAuth codes always start with ``v^1.1`` (or
    ``v%5E1.1`` URL-encoded), so if the normal ``code`` param is missing
    we scan the rest of the query string for a value with that signature.
    """
    from fastapi.responses import HTMLResponse

    if error:
        body = f"<h1>eBay authorization failed</h1><p>{error}</p>"
        return HTMLResponse(_oauth_result_page(False, body), status_code=400)

    # Fallback: if code is missing, look through all query params for an
    # eBay-shaped code value. FastAPI auto-URL-decodes values so we look
    # for the decoded prefix "v^1.1".
    if not code:
        for key, value in request.query_params.items():
            if value and value.startswith("v^1.1"):
                code = value
                break

    if not code:
        # Show the raw query string in the error page so the user can see
        # what we actually received - helps diagnose URL-edit mishaps.
        raw_qs = str(request.url.query) or "(none)"
        body = (
            f"<h1>Missing code parameter</h1>"
            f"<p>We didn't see a <code>code=</code> parameter in the callback URL, "
            f"and no other param value matched eBay's OAuth code format.</p>"
            f"<p>Raw query string received:</p>"
            f"<pre style='word-break: break-all; white-space: pre-wrap; background: #1B1813; padding: 8px; border-radius: 4px;'>"
            f"{raw_qs[:500]}</pre>"
            f"<p>Re-run the OAuth flow from Settings &rarr; eBay; the code expires after 5 minutes "
            f"so a stale one is the usual cause.</p>"
        )
        return HTMLResponse(_oauth_result_page(False, body), status_code=400)

    import logging
    import traceback
    from listing_studio.platforms.base import PostingError
    from listing_studio.platforms.ebay import EbayConnector

    log = logging.getLogger(__name__)

    connector = EbayConnector()
    try:
        merged = await connector.exchange_code_for_tokens(code)
    except PostingError as exc:
        # eBay rejected the code, or our app credentials are misconfigured
        return HTMLResponse(
            _oauth_result_page(False, f"<h1>Couldn't exchange code</h1><p>{exc}</p>"),
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001 - we want to catch literally everything here
        # Anything else: log full traceback AND show it on the page so the
        # user doesn't see a bare "Internal Server Error" with no clue.
        # OAuth callbacks are one-shot - if we don't surface the error now,
        # the user has to re-run the whole flow to retry.
        tb = traceback.format_exc()
        log.exception("eBay OAuth callback: unhandled exception during token exchange")
        body = (
            f"<h1>Unexpected error during token exchange</h1>"
            f"<p>{type(exc).__name__}: {exc}</p>"
            f"<p style='color: #8A7B5E; font-size: 12px;'>Full traceback (also in the log file):</p>"
            f"<pre style='background: #1B1813; padding: 8px; border-radius: 4px; "
            f"white-space: pre-wrap; word-break: break-all; font-size: 11px; "
            f"max-height: 320px; overflow: auto;'>{tb[:3000]}</pre>"
        )
        return HTMLResponse(_oauth_result_page(False, body), status_code=500)

    label = merged.get("account_label") or "eBay seller"
    body = f"""
        <h1>✓ Connected to eBay</h1>
        <p>Authorized as <strong>{label}</strong>.</p>
        <p>You can close this tab and return to Listing Studio - the app will pick up the new tokens automatically.</p>
    """
    return HTMLResponse(_oauth_result_page(True, body))


def _oauth_result_page(ok: bool, body: str) -> str:
    """Wrap the OAuth callback result in a styled HTML shell.

    Kept self-contained (no external CSS) so the page works even if the
    user's browser has lost connection to the embedded server.
    """
    accent = "#7a9d4f" if ok else "#c85a3c"
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Listing Studio - eBay OAuth</title>
    <style>
        body {{
            background: #1B1813;
            color: #d4cfc4;
            font-family: -apple-system, system-ui, sans-serif;
            margin: 0;
            display: grid;
            place-items: center;
            min-height: 100vh;
        }}
        .card {{
            background: #2a2520;
            padding: 32px 40px;
            border-radius: 6px;
            border: 1px solid {accent};
            max-width: 480px;
        }}
        h1 {{ color: {accent}; font-weight: 500; margin-top: 0; }}
        p {{ line-height: 1.6; }}
        code {{ background: #1B1813; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body><div class="card">{body}</div></body>
</html>"""


async def _connect_with_api_key(platform: Platform, payload: dict) -> dict:
    """Shared logic for platforms that use bearer-token auth.

    Store the key, ask the connector to test it, save with the account label
    on success or clear on failure.
    """
    from listing_studio.core.credentials import (
        clear_credentials,
        store_credentials,
    )

    api_key = payload.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "Missing api_key")

    try:
        store_credentials(platform, {"api_key": api_key})
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    connector = _get_connector(platform)
    if connector is None:
        clear_credentials(platform)
        raise HTTPException(501, f"Connector not yet implemented for {platform.value}")

    ok, label_or_error = await connector.test_connection()

    if not ok:
        clear_credentials(platform)
        raise HTTPException(
            400, f"{platform.value.capitalize()} rejected the key: {label_or_error}",
        )

    store_credentials(platform, {
        "api_key": api_key,
        "account_label": label_or_error,
    })
    return {"is_connected": True, "account_label": label_or_error}


def _get_connector(platform: Platform):
    """Instantiate the right connector class for a platform.

    Returns None for platforms whose connectors aren't built yet (eBay, Etsy).
    Caller should treat None as 'not implemented'.
    """
    if platform == Platform.SQUARESPACE:
        from listing_studio.platforms.squarespace import SquarespaceConnector
        return SquarespaceConnector()
    if platform == Platform.REVERB:
        from listing_studio.platforms.reverb import ReverbConnector
        return ReverbConnector()
    # Etsy, eBay - not implemented yet
    return None


@app.post("/api/settings/platforms/{platform_value}/test")
async def test_platform_connection(platform_value: str) -> dict:
    """Verify a platform's stored credentials still work.

    Returns:
        {"ok": true, "account_label": "..."} on success
        {"ok": false, "error": "..."} on failure
    """
    try:
        platform = Platform(platform_value)
    except ValueError:
        raise HTTPException(404, f"Unknown platform: {platform_value}")

    connector = _get_connector(platform)
    if connector is None:
        return {"ok": False, "error": "Test not implemented for this platform yet"}

    ok, message = await connector.test_connection()
    if ok:
        return {"ok": True, "account_label": message}
    return {"ok": False, "error": message}


# ---------------------------------------------------------------------------
# Photo host (image hosting for Reverb)
# ---------------------------------------------------------------------------
#
# Reverb's API doesn't accept binary photo uploads, so we host them on an
# external service (currently ImgBB) and pass URLs to Reverb. These endpoints
# manage the host's stored API key, mirroring the platform-connection pattern
# above but using the "service" namespace in the keyring rather than the
# Platform enum.


@app.get("/api/settings/photo-host")
async def get_photo_host_status() -> dict:
    """Return whether a photo host is configured and which one.

    Response shape: {"connected": bool, "service_name": str | null,
                     "display_name": str | null}
    """
    from listing_studio.core.photo_host import get_status
    return get_status()


@app.post("/api/settings/photo-host/imgbb/connect")
async def connect_imgbb(payload: dict) -> dict:
    """Validate an ImgBB API key and save it on success.

    Body: ``{"api_key": "<the key>"}``

    Tests the key by performing a tiny upload; saves it in the OS keyring
    only if the test succeeds. Pattern matches the platform connect flow.
    """
    from listing_studio.core.credentials import (
        clear_service_credentials,
        store_service_credentials,
    )
    from listing_studio.core.photo_host import IMGBB_SERVICE_NAME, ImgBBHost

    api_key = payload.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "Missing api_key")

    # Save first so the ImgBBHost factory can find it during the test.
    # Cleared if the test fails so we never leave a bad key sitting around.
    try:
        store_service_credentials(IMGBB_SERVICE_NAME, {"api_key": api_key})
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    host = ImgBBHost(api_key=api_key)
    ok, label_or_error = await host.test_connection()

    if not ok:
        clear_service_credentials(IMGBB_SERVICE_NAME)
        raise HTTPException(400, f"ImgBB rejected the key: {label_or_error}")

    store_service_credentials(IMGBB_SERVICE_NAME, {
        "api_key": api_key,
        "account_label": label_or_error,
    })
    return {"is_connected": True, "account_label": label_or_error}


@app.post("/api/settings/photo-host/disconnect", status_code=204)
async def disconnect_photo_host() -> None:
    """Remove the configured photo host's credentials."""
    from listing_studio.core.credentials import clear_service_credentials
    from listing_studio.core.photo_host import IMGBB_SERVICE_NAME
    # Only one host today, so we always clear ImgBB. When we add Cloudinary
    # etc, this becomes "clear whichever is configured".
    clear_service_credentials(IMGBB_SERVICE_NAME)


@app.post("/api/settings/photo-host/test")
async def test_photo_host() -> dict:
    """Verify the stored photo-host credentials still work.

    Returns {"ok": bool, "account_label" | "error": str}, matching the
    platform test endpoint's shape so the UI can use the same handler.
    """
    from listing_studio.core.photo_host import get_configured_host

    host = get_configured_host()
    if host is None:
        return {"ok": False, "error": "No photo host configured"}

    ok, message = await host.test_connection()
    if ok:
        return {"ok": True, "account_label": message}
    return {"ok": False, "error": message}


# ---------------------------------------------------------------------------
# Backup / Restore (.sals file format)
# ---------------------------------------------------------------------------
#
# Export bundles templates, categories, mappings, tags, preferences, and
# optionally API credentials into a single .sals (Southwest Acoustics
# Listing Studio) ZIP file. Import restores from one. Both endpoints take
# care to surface clear warnings; the destructive nature of import is
# acknowledged in the UI before the call lands here.


@app.get("/api/backup/export")
async def backup_export(include_credentials: bool = False):
    """Return a .sals backup of the user's data as a file download.

    Query params:
      include_credentials (default false): if true, embed stored API tokens
        in the archive. The UI must show a warning before passing true.
    """
    from fastapi.responses import Response
    from listing_studio.core import backup

    with session_scope() as session:
        data = backup.export_backup(session, include_credentials=include_credentials)

    # Filename with version + date for easy identification on disk
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y%m%d-%H%M%S")
    filename = f"listing-studio-backup-v{__version__}-{stamp}.sals"

    return Response(
        content=data,
        media_type="application/x-sals",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/backup/import")
async def backup_import(request: Request) -> dict:
    """Restore a .sals backup. DESTRUCTIVE - replaces current data.

    Body: raw .sals file bytes (POSTed as application/octet-stream or
    multipart/form-data; we read whatever the request body contains).

    Returns: ``{"manifest": {...}, "counts": {...}, "warnings": [...]}``
    """
    from listing_studio.core import backup

    data = await request.body()
    if not data:
        raise HTTPException(400, "Empty request body - upload a .sals file")

    with session_scope() as session:
        try:
            result = backup.import_backup(session, data, restore_credentials=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return result


# ---------------------------------------------------------------------------
# Auto-update endpoints
# ---------------------------------------------------------------------------


@app.get("/api/updates/check")
async def check_for_updates(force: bool = False) -> dict:
    """Check GitHub for a newer release.

    Returns:
        {
            "current_version": "0.2.0",
            "is_packaged": true,
            "update_available": true,
            "release": {
                "tag_name": "v0.2.1",
                "version": "0.2.1",
                "name": "v0.2.1",
                "body": "Release notes...",
                "published_at": "2026-05-22T...",
                "download_size": 67108864
            }
        }

    If no update is available, "update_available" is false and "release" is null.
    Never raises - any network or parsing error becomes "no update available".
    """
    from listing_studio.core.updater import (
        check_for_update,
        is_packaged_build,
    )

    release = check_for_update(force=force)
    result = {
        "current_version": __version__,
        "is_packaged": is_packaged_build(),
        "update_available": release is not None,
        "release": None,
    }
    if release is not None:
        result["release"] = {
            "tag_name": release.tag_name,
            "version": release.version,
            "name": release.name,
            "body": release.body,
            "published_at": release.published_at,
            "download_size": release.download_size,
        }
    return result


# Tracks an in-progress install. We allow only one at a time.
_install_state: dict = {
    "in_progress": False,
    "bytes_done": 0,
    "bytes_total": 0,
    "error": None,
    "completed_install_root": None,
}


@app.post("/api/updates/install")
async def install_update_endpoint() -> dict:
    """Kick off an update install. Returns immediately; check progress separately.

    The install runs on a background thread so this endpoint stays responsive.
    Use GET /api/updates/progress to poll progress. When `completed_install_root`
    is non-null, call POST /api/updates/restart to switch to the new version.

    Only one install can be in progress at a time. Returns 409 if one's already running.
    """
    from listing_studio.core.updater import (
        check_for_update,
        install_update,
    )

    if _install_state["in_progress"]:
        raise HTTPException(409, "An update is already in progress.")

    release = check_for_update(force=True)
    if release is None:
        raise HTTPException(404, "No update available.")

    # Reset state
    _install_state.update({
        "in_progress": True,
        "bytes_done": 0,
        "bytes_total": release.download_size,
        "error": None,
        "completed_install_root": None,
    })

    def progress_callback(done: int, total: int) -> None:
        _install_state["bytes_done"] = done
        _install_state["bytes_total"] = total

    def _do_install():

        try:
            install_root = install_update(release, progress_callback=progress_callback)
            _install_state["completed_install_root"] = str(install_root)
        except Exception as exc:
            _install_state["error"] = str(exc)
        finally:
            _install_state["in_progress"] = False

    import threading as _t
    _t.Thread(target=_do_install, daemon=True, name="updater-install").start()

    return {"started": True, "version": release.version}


@app.get("/api/updates/progress")
async def get_install_progress() -> dict:
    """Return the current install progress."""
    return dict(_install_state)  # Copy so caller can't mutate


@app.post("/api/updates/restart")
async def restart_into_update() -> dict:
    """Restart the app into the newly-installed version.

    Must be called after install completes (completed_install_root is set).
    Returns immediately; the actual restart happens ~500ms later so this
    response reaches the UI before we exit.
    """
    from listing_studio.core.updater import restart_into

    install_root_str = _install_state.get("completed_install_root")
    if not install_root_str:
        raise HTTPException(400, "No installed update is ready. Run install first.")

    from pathlib import Path as _Path

    install_root = _Path(install_root_str)

    # Schedule the restart shortly after this response goes out
    def _do_restart():
        import time as _time
        _time.sleep(0.8)  # Let the HTTP response reach the UI
        try:
            restart_into(install_root)
        except Exception as exc:
            # If restart fails, log and give up - we can't really recover here
            import logging
            logging.getLogger(__name__).exception("Restart failed: %s", exc)

    import threading as _t
    _t.Thread(target=_do_restart, daemon=True, name="updater-restart").start()

    return {"restarting": True, "install_root": install_root_str}


# ---------------------------------------------------------------------------
# Template photos (attach NAS photos to a listing)
# ---------------------------------------------------------------------------


@app.post("/api/templates/{template_id}/photos")
async def add_photos_to_template(template_id: int, payload: dict) -> dict:
    """Attach one or more NAS photos to a template.

    Body shape:
        {
            "paths": ["Z:\\...\\photo1.jpg", "Z:\\...\\photo2.jpg"],
            "tags": ["kluson", "tuners", "vintage"]
        }

    Paths are added in array order. If the template has no photos yet, the
    first one becomes primary (sort_order 0). If it already has photos, new
    ones are appended after the existing ones.

    Tags are added to the template's tag list (deduplicating against existing tags).

    All paths must pass NAS security validation. Any path that's not under
    a configured NAS root will cause the entire request to fail (400).
    """
    from datetime import datetime as _datetime

    from listing_studio.core.models import Tag, Template, TemplatePhoto, TemplateTag
    from listing_studio.core.nas import PathOutsideRoots, validate_path

    paths = payload.get("paths", [])
    tags = payload.get("tags", [])

    if not isinstance(paths, list) or not paths:
        raise HTTPException(400, "Provide a non-empty list of paths")

    # Validate all paths up front - we'd rather fail before any DB writes
    # than leave the template in a partial state.
    validated_paths: list[str] = []
    for path in paths:
        try:
            resolved = validate_path(path)
        except PathOutsideRoots as exc:
            raise HTTPException(
                400, f"Path outside configured NAS roots: {path}",
            ) from exc
        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(404, f"File not found: {path}")
        validated_paths.append(str(resolved))

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")

        # Find the current highest sort_order so we append after it
        existing_count = (
            session.execute(
                select(TemplatePhoto)
                .where(TemplatePhoto.template_id == template_id)
            )
            .scalars()
            .all()
        )
        next_sort_order = (
            max((p.sort_order for p in existing_count), default=-1) + 1
        )

        added = []
        now = _datetime.now()
        for path in validated_paths:
            # Skip if this exact path is already attached
            already_attached = any(p.source_path == path for p in existing_count)
            if already_attached:
                continue

            photo = TemplatePhoto(
                template_id=template_id,
                source_path=path,
                sort_order=next_sort_order,
                last_seen_at=now,
            )
            session.add(photo)
            added.append(path)
            next_sort_order += 1

        # Tags: ensure each exists in tags table, then attach to template
        if tags:
            for tag_name in tags:
                tag_name = tag_name.strip().lower()
                if not tag_name:
                    continue
                # find-or-create the Tag
                existing_tag = session.execute(
                    select(Tag).where(Tag.name == tag_name)
                ).scalar_one_or_none()
                if existing_tag is None:
                    existing_tag = Tag(name=tag_name)
                    session.add(existing_tag)
                    session.flush()  # so we get an ID

                # link to template if not already linked
                already_linked = session.execute(
                    select(TemplateTag).where(
                        (TemplateTag.template_id == template_id) &
                        (TemplateTag.tag_id == existing_tag.id)
                    )
                ).first()
                if not already_linked:
                    session.add(TemplateTag(
                        template_id=template_id, tag_id=existing_tag.id,
                    ))

        # bump the template's updated_at
        template.updated_at = now

        session.commit()

        return {
            "added_count": len(added),
            "skipped_count": len(validated_paths) - len(added),
            "total_photos": len(existing_count) + len(added),
        }


@app.delete("/api/templates/{template_id}/photos/{photo_id}", status_code=204)
async def remove_photo_from_template(template_id: int, photo_id: int) -> None:
    """Detach a single photo from a template.

    Doesn't touch the file on the NAS - we only delete the DB row that
    associated it with this template. After deletion, remaining photos are
    re-numbered so sort_order has no gaps.
    """
    from listing_studio.core.models import TemplatePhoto

    with session_scope() as session:
        photo = session.get(TemplatePhoto, photo_id)
        if photo is None or photo.template_id != template_id:
            raise HTTPException(404, "Photo not found on this template")

        session.delete(photo)
        session.flush()

        # Re-number remaining photos to close the gap
        remaining = session.execute(
            select(TemplatePhoto)
            .where(TemplatePhoto.template_id == template_id)
            .order_by(TemplatePhoto.sort_order)
        ).scalars().all()

        for idx, p in enumerate(remaining):
            p.sort_order = idx


# ---------------------------------------------------------------------------
# Categories - Dad's organizational groups with marketplace taxonomy mappings
# ---------------------------------------------------------------------------


@app.get("/api/categories")
async def list_categories() -> list[CategoryOut]:
    """Return all categories with template counts.

    Sorted alphabetically by name. Each category includes ``template_count``
    so the library sidebar can show "Tuners (12)" style labels.
    """
    from sqlalchemy import func as sqlfunc

    from listing_studio.core.models import Category, Template

    out: list[CategoryOut] = []
    with session_scope() as session:
        # Get template counts grouped by category
        counts_query = session.execute(
            select(Template.category_id, sqlfunc.count(Template.id))
            .where(Template.category_id.isnot(None))
            .group_by(Template.category_id)
        ).all()
        counts_by_id = {row[0]: row[1] for row in counts_query}

        categories = session.execute(
            select(Category).order_by(Category.name)
        ).scalars().all()

        for cat in categories:
            data = CategoryOut.model_validate(cat)
            data.template_count = counts_by_id.get(cat.id, 0)
            out.append(data)

    return out


@app.post("/api/categories", status_code=201)
async def create_category(payload: CategoryCreate) -> CategoryOut:
    """Create a new category."""
    from listing_studio.core.models import Category

    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Category name is required")

    with session_scope() as session:
        # Check for name collision
        existing = session.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(400, f"Category '{name}' already exists")

        cat = Category(
            name=name,
            reverb_category_uuid=payload.reverb_category_uuid,
            reverb_category_full_name=payload.reverb_category_full_name,
            reverb_subcategory_uuids=payload.reverb_subcategory_uuids,
            reverb_subcategory_names=payload.reverb_subcategory_names,
            ebay_category_id=payload.ebay_category_id,
            ebay_category_name=payload.ebay_category_name,
            ebay_category_path=payload.ebay_category_path,
            ebay_leaf=payload.ebay_leaf,
            squarespace_store_page_id=payload.squarespace_store_page_id,
            squarespace_store_page_name=payload.squarespace_store_page_name,
            platform_config={},
            default_condition=payload.default_condition,
            default_weight_oz=payload.default_weight_oz,
            default_shipping_method=payload.default_shipping_method,
        )
        session.add(cat)
        session.flush()

        # Learn cross-platform mappings + bump recent-used for any platforms
        # this category was created against. Safe to call regardless of which
        # platforms have data populated.
        from listing_studio.core import category_suggest
        category_suggest.record_category_save(session, cat)

        result = CategoryOut.model_validate(cat)
        result.template_count = 0
        return result


@app.patch("/api/categories/{category_id}")
async def update_category(category_id: int, payload: CategoryUpdate) -> CategoryOut:
    """Update an existing category."""
    from sqlalchemy import func as sqlfunc

    from listing_studio.core.models import Category, Template

    with session_scope() as session:
        cat = session.get(Category, category_id)
        if cat is None:
            raise HTTPException(404, f"Category {category_id} not found")

        update_data = payload.model_dump(exclude_unset=True)

        # Name collision check
        if "name" in update_data and update_data["name"] != cat.name:
            new_name = update_data["name"].strip()
            if not new_name:
                raise HTTPException(400, "Category name cannot be empty")
            other = session.execute(
                select(Category).where(Category.name == new_name)
            ).scalar_one_or_none()
            if other is not None and other.id != cat.id:
                raise HTTPException(400, f"Category '{new_name}' already exists")
            update_data["name"] = new_name

        for key, value in update_data.items():
            setattr(cat, key, value)

        session.flush()

        # Learn cross-platform mappings + bump recent-used after any update
        # that may have changed the platform fields. record_category_save
        # is idempotent on existing rows, so no harm calling it every time.
        from listing_studio.core import category_suggest
        category_suggest.record_category_save(session, cat)

        # Count templates
        count = session.execute(
            select(sqlfunc.count(Template.id))
            .where(Template.category_id == cat.id)
        ).scalar() or 0

        result = CategoryOut.model_validate(cat)
        result.template_count = count
        return result


@app.delete("/api/categories/{category_id}", status_code=204)
async def delete_category(category_id: int) -> None:
    """Delete a category. Fails if any templates still reference it."""
    from sqlalchemy import func as sqlfunc

    from listing_studio.core.models import Category, Template

    with session_scope() as session:
        cat = session.get(Category, category_id)
        if cat is None:
            raise HTTPException(404, f"Category {category_id} not found")

        # Refuse delete if templates use it
        count = session.execute(
            select(sqlfunc.count(Template.id))
            .where(Template.category_id == category_id)
        ).scalar() or 0
        if count > 0:
            raise HTTPException(
                400,
                f"Can't delete '{cat.name}' - {count} template(s) still reference it. "
                "Move them to another category or delete them first.",
            )

        session.delete(cat)


# ---------------------------------------------------------------------------
# Reverb taxonomy search (for the category picker UI)
# ---------------------------------------------------------------------------


@app.get("/api/platforms/reverb/taxonomy/search")
async def search_reverb_taxonomy(q: str = "", limit: int = 30) -> list[dict]:
    """Search Reverb's category taxonomy.

    Returns matches with uuid, name, and full_name (the breadcrumb path).
    Used by the category creation modal to find the right Reverb category.

    Empty query returns the first ``limit`` categories alphabetically.
    """
    from listing_studio.platforms.reverb import ReverbConnector

    connector = ReverbConnector()
    if not await connector.is_connected():
        raise HTTPException(
            400,
            "Reverb not connected. Connect it in Settings before searching the taxonomy.",
        )

    matches = await connector.search_taxonomy(q, limit=limit)
    return matches


@app.get("/api/platforms/ebay/taxonomy/search")
async def search_ebay_taxonomy(q: str = "", limit: int = 30) -> list[dict]:
    """Search eBay's category taxonomy.

    Returns matches with category_id (int), name, full_name, is_leaf (bool).
    eBay only allows listings on LEAF categories - the UI should warn the
    user when picking a non-leaf result.

    Empty query returns the first ``limit`` leaves (more useful than mid-tree
    nodes when populating a category picker).
    """
    from listing_studio.platforms.ebay import EbayConnector

    connector = EbayConnector()
    if not await connector.is_connected():
        raise HTTPException(
            400,
            "eBay not connected. Connect it in Settings before searching the taxonomy.",
        )

    matches = await connector.search_taxonomy(q, limit=limit)
    return matches


@app.post("/api/platforms/ebay/locations")
async def create_ebay_location(payload: dict) -> dict:
    """Create an eBay inventory (merchant) location.

    Required fields in payload:
        key                  - merchantLocationKey (URL-safe identifier, e.g. "main")
        name                 - human-readable name
        address_line_1       - street address
        city                 - city
        state_or_province    - 2-letter state for US (e.g. "AZ")
        postal_code          - ZIP / postal code

    Optional:
        country              - 2-letter code, defaults to "US"
        address_line_2       - apt/suite
        location_type        - "WAREHOUSE" (default) or "STORE"

    Returns {"ok": true, "key": "..."} on success. Lets the user set up
    the location eBay requires for offers without needing to use eBay's
    API Explorer or hunt through Seller Hub.
    """
    from listing_studio.platforms.base import PostingError
    from listing_studio.platforms.ebay import EbayConnector

    required = ("key", "name", "address_line_1", "city",
                "state_or_province", "postal_code")
    missing = [f for f in required if not payload.get(f)]
    if missing:
        raise HTTPException(400, f"Missing required field(s): {', '.join(missing)}")

    connector = EbayConnector()
    if not connector.has_user_token():
        raise HTTPException(400, "eBay seller account not authorized. Connect via Settings → eBay first.")

    try:
        await connector.create_merchant_location(
            key=payload["key"],
            name=payload["name"],
            address_line_1=payload["address_line_1"],
            city=payload["city"],
            state_or_province=payload["state_or_province"],
            postal_code=payload["postal_code"],
            country=payload.get("country", "US"),
            address_line_2=payload.get("address_line_2"),
            location_type=payload.get("location_type", "WAREHOUSE"),
        )
    except PostingError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {"ok": True, "key": payload["key"]}


@app.get("/api/platforms/ebay/policies")
async def get_ebay_policies() -> dict:
    """Return Dad's eBay business policies + merchant locations.

    Offers (drafts and live alike) require references to fulfillment/
    payment/return policy IDs and a merchantLocationKey. Most sellers have
    exactly one of each; the post endpoint auto-picks the first by default.

    Response shape::

        {
            "fulfillment": [{"id": "...", "name": "..."}],
            "payment":     [{"id": "...", "name": "..."}],
            "return":      [{"id": "...", "name": "..."}],
            "locations":   [{"key": "...", "name": "..."}]
        }
    """
    from listing_studio.platforms.ebay import EbayConnector

    connector = EbayConnector()
    if not connector.has_user_token():
        return {"fulfillment": [], "payment": [], "return": [], "locations": []}

    policies = await connector.fetch_business_policies()
    locations = await connector.fetch_merchant_locations()
    return {**policies, "locations": locations}


@app.get("/api/platforms/ebay/aspects")
async def get_ebay_aspects(category_id: str) -> dict:
    """Return the item-aspect schema eBay defines for ``category_id``.

    Used by the form's Item Specifics editor to prefill required aspects
    when Dad picks an eBay category. Read-only; uses the app token so it
    works even without the user OAuth dance.

    Response::

        {
            "aspects": [
                {"name": "Type", "required": true, "values": ["Bridge Pickup", ...],
                 "value_type": "STRING", "is_variation": false, "max_length": 65},
                ...
            ]
        }
    """
    from listing_studio.platforms.ebay import EbayConnector

    if not category_id or not str(category_id).strip():
        raise HTTPException(400, "category_id is required")

    connector = EbayConnector()
    aspects = await connector.fetch_required_aspects(category_id)
    return {"aspects": aspects}


@app.post("/api/templates/{template_id}/post-to-ebay")
async def post_template_to_ebay(template_id: int, payload: dict | None = None) -> dict:
    """Create an unpublished eBay offer (draft) from a template.

    Mirrors post_template_to_reverb's flow:
        1. Snapshot template + photo paths from the session
        2. Normalize + upload each photo to the configured image host
        3. Auto-pick first of each eBay business policy + first location
           (overridable via payload), then create_draft on the connector

    Body (all optional):
        {
            "fulfillment_policy_id": "...",
            "payment_policy_id":     "...",
            "return_policy_id":      "...",
            "merchant_location_key": "...",
            "skip_photos":           false
        }
    """
    from listing_studio.core.models import Template
    from listing_studio.core.photo_host import get_configured_host
    from listing_studio.core.photo_processor import (
        NormalizeError,
        normalize_for_upload,
    )
    from listing_studio.platforms.base import PostingError
    from listing_studio.platforms.ebay import EbayConnector

    payload = payload or {}
    skip_photos = bool(payload.get("skip_photos", False))

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")

        photo_paths = sorted(
            [(p.sort_order, p.source_path) for p in template.photos],
            key=lambda x: x[0],
        )
        photo_paths = [path for (_o, path) in photo_paths]

        # Pull the category's eBay mapping so we can fail fast if missing.
        ebay_category_id = None
        if template.category_id and template.category:
            ebay_category_id = template.category.ebay_category_id

        # Snapshot all the template fields we need for the async call
        template_copy = _SimpleNamespace(
            id=template.id,
            name=template.name,
            title=template.title,
            description=template.description,
            brand=template.brand,
            model=template.model,
            condition=template.condition,
            base_price_cents=template.base_price_cents,
            quantity=template.quantity,
            ebay_category_id=ebay_category_id,
            ebay_shipping_type=template.ebay_shipping_type,
            ebay_shipping_override_cents=template.ebay_shipping_override_cents,
            # Pass the user-edited item specifics through so they end up
            # in inventory_item.product.aspects on the eBay payload.
            item_specifics=dict(template.item_specifics or {}),
            category_id=template.category_id,
            category=type("C", (), {"ebay_category_id": ebay_category_id}),
        )

    connector = EbayConnector()
    if not await connector.is_connected():
        raise HTTPException(400, "eBay app credentials not configured. Connect in Settings.")
    if not connector.has_user_token():
        raise HTTPException(400, "eBay seller account not authorized. Connect via Settings → eBay → Authorize Seller Account.")

    # ---- Resolve business policies (auto-pick first if not specified) ----
    fulfillment_id = payload.get("fulfillment_policy_id")
    payment_id = payload.get("payment_policy_id")
    return_id = payload.get("return_policy_id")
    location_key = payload.get("merchant_location_key")

    if not (fulfillment_id and payment_id and return_id and location_key):
        policies = await connector.fetch_business_policies()
        locations = await connector.fetch_merchant_locations()

        if not fulfillment_id:
            if not policies["fulfillment"]:
                raise HTTPException(400, "No fulfillment policy found on eBay account. Create one in Seller Hub → Account → Business Policies.")
            fulfillment_id = policies["fulfillment"][0]["id"]
        if not payment_id:
            if not policies["payment"]:
                raise HTTPException(400, "No payment policy found on eBay account. Create one in Seller Hub.")
            payment_id = policies["payment"][0]["id"]
        if not return_id:
            if not policies["return"]:
                raise HTTPException(400, "No return policy found on eBay account. Create one in Seller Hub.")
            return_id = policies["return"][0]["id"]
        if not location_key:
            if not locations:
                raise HTTPException(400, "No merchant location found on eBay account. Add one in Seller Hub → Account → Locations.")
            location_key = locations[0]["key"]

    # ---- Photo pre-upload (same pipeline as Reverb) ----
    photo_results: dict = {
        "uploaded": 0, "failed": 0, "errors": [],
        "host_configured": False, "host_display_name": None,
    }
    photo_urls: list[str] = []

    host = None if skip_photos else get_configured_host()
    if host is not None:
        photo_results["host_configured"] = True
        photo_results["host_display_name"] = host.display_name

    if host is not None and photo_paths:
        from pathlib import Path as PathLib
        from listing_studio.core.photo_host import PhotoHostError

        for idx, photo_path_str in enumerate(photo_paths):
            photo_path = PathLib(photo_path_str)
            try:
                normalized = normalize_for_upload(photo_path)
                upload_filename = f"{idx + 1:02d}_{normalized.filename}"
                url = await host.upload(normalized.data, upload_filename)
                photo_urls.append(url)
                photo_results["uploaded"] += 1
            except (NormalizeError, PhotoHostError) as exc:
                photo_results["failed"] += 1
                photo_results["errors"].append(f"{photo_path.name}: {exc}")
            except Exception as exc:  # noqa: BLE001 - photo failure shouldn't block listing
                photo_results["failed"] += 1
                photo_results["errors"].append(f"{photo_path.name}: {type(exc).__name__}: {exc}")

    # ---- Create the draft ----
    try:
        result = await connector.create_draft(
            template_copy,
            photo_urls=photo_urls,
            fulfillment_policy_id=fulfillment_id,
            payment_policy_id=payment_id,
            return_policy_id=return_id,
            merchant_location_key=location_key,
        )
    except PostingError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "sku": result["sku"],
        "offer_id": result.get("offer_id"),
        "url": result.get("url"),
        "photo_results": photo_results,
        # stored_summary tells us what eBay echoed back from the readback
        # GETs - useful when the API call "succeeds" but Seller Hub shows
        # an empty draft. If stored_summary has populated fields, the
        # data is in eBay's system and the issue is just Seller Hub UI.
        "stored_summary": result.get("stored_summary", {}),
        "policies_used": {
            "fulfillment_policy_id": fulfillment_id,
            "payment_policy_id": payment_id,
            "return_policy_id": return_id,
            "merchant_location_key": location_key,
        },
    }


class _SimpleNamespace:
    """Minimal stand-in for a Template across session boundaries.

    Used by post_template_to_ebay (and elsewhere) so we can call connector
    methods after the SQLAlchemy session has closed without copying a
    detached ORM instance.
    """
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@app.get("/api/templates/{template_id}/ebay-preview")
async def get_template_ebay_preview(template_id: int) -> dict:
    """Fetch the inventory_item + offer eBay has stored for this template.

    Seller Hub doesn't render unpublished Inventory API offers as drafts,
    so we render our own preview from this data. Always pulls fresh from
    eBay so the preview reflects whatever the last post-to-ebay call
    actually stored (or the result of any in-app edit).
    """
    from listing_studio.core.models import Template
    from listing_studio.platforms.ebay import EbayConnector

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")
        sku = f"ls-{template.id}"
        # Snapshot the local-side fields used by the preview, so the UI
        # can render even if eBay's GET is down.
        local = {
            "name": template.name,
            "title": template.title,
            "description": template.description,
            "brand": template.brand,
            "model": template.model,
            "condition": template.condition,
            "base_price_cents": template.base_price_cents,
            "quantity": template.quantity,
            "ebay_category_id": (
                template.category.ebay_category_id if template.category else None
            ),
            "ebay_shipping_type": template.ebay_shipping_type,
            "ebay_shipping_override_cents": template.ebay_shipping_override_cents,
            "photo_count": len(template.photos or []),
        }

    connector = EbayConnector()
    if not connector.has_user_token():
        return {
            "sku": sku,
            "local": local,
            "ebay": {"inventory": None, "offer": None,
                     "errors": ["eBay seller account not authorized."]},
        }
    ebay_data = await connector.fetch_inventory_and_offer(sku)
    return {"sku": sku, "local": local, "ebay": ebay_data}


@app.post("/api/templates/{template_id}/publish-to-ebay")
async def publish_template_to_ebay(template_id: int) -> dict:
    """Publish the unpublished eBay offer for this template, going live.

    Looks up the most recent UNPUBLISHED offer for the template's SKU,
    then calls publish. Returns the live listingId + URL. Raises 400 if
    no unpublished offer exists (caller should Post Draft first).
    """
    from listing_studio.core.models import Template
    from listing_studio.platforms.base import PostingError
    from listing_studio.platforms.ebay import EbayConnector

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")
        sku = f"ls-{template.id}"

    connector = EbayConnector()
    if not connector.has_user_token():
        raise HTTPException(400, "eBay seller account not authorized.")

    ebay_data = await connector.fetch_inventory_and_offer(sku)
    offer = ebay_data.get("offer")
    if not offer or not offer.get("offerId"):
        raise HTTPException(
            400,
            "No eBay offer found for this template. Click Post eBay Draft first.",
        )
    if offer.get("status") == "PUBLISHED":
        # Already live - return the listing info instead of re-publishing.
        listing_id = offer.get("listing", {}).get("listingId") if isinstance(offer.get("listing"), dict) else None
        return {
            "already_published": True,
            "listing_id": listing_id,
            "url": f"https://www.ebay.com/itm/{listing_id}" if listing_id else "https://www.ebay.com/sh/lst/active",
        }

    try:
        result = await connector.publish_offer(offer["offerId"])
    except PostingError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "already_published": False,
        "listing_id": result.get("listing_id"),
        "url": result.get("url"),
    }


@app.get("/api/platforms/squarespace/store-pages")
async def get_squarespace_store_pages() -> list[dict]:
    """Return the Squarespace store pages discoverable from existing products.

    Squarespace's API doesn't expose a direct "list commerce pages" endpoint,
    so this scans products and returns the unique storePageIds observed.
    Empty list if not connected or no products exist yet (Dad can fall back
    to entering a page ID manually in that case).
    """
    from listing_studio.platforms.squarespace import SquarespaceConnector

    connector = SquarespaceConnector()
    if not await connector.is_connected():
        return []

    return await connector.fetch_store_pages()


# Cross-platform category suggestions + recent-used


@app.get("/api/categories/suggestions")
async def get_category_suggestions(
    from_platform: str,
    from_id: str,
    to_platform: str,
) -> list[dict]:
    """Suggest target-platform categories matching a source category.

    Two-layer logic (the engine handles layer 1, this endpoint handles
    layer 2 because it requires an async call to the target connector):

      1. **Direct mappings** in category_mappings (shipped + learned).
      2. **Fuzzy name match** against the target platform's cached taxonomy,
         using the source category's display name as the query.

    Query params:
      from_platform: "reverb" | "ebay" | "squarespace"
      from_id:       The source platform's external_id (UUID for Reverb, etc.)
      to_platform:   The platform we want suggestions for.

    Returns a list of CategorySuggestion-shaped dicts ordered by confidence.
    """
    from listing_studio.core import category_suggest
    from listing_studio.core.models import CategoryUsage, Platform

    try:
        src = Platform(from_platform)
        dst = Platform(to_platform)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown platform: {exc}") from exc

    # Layer 1: direct mappings (in-DB lookup)
    with session_scope() as session:
        direct = category_suggest.suggest_for(
            session,
            from_platform=src,
            from_external_id=from_id,
            to_platform=dst,
        )
        if direct:
            return direct

        # Pull the source category's display name to use as a fuzzy hint
        usage = session.execute(
            select(CategoryUsage).where(
                CategoryUsage.platform == src,
                CategoryUsage.external_id == from_id,
            )
        ).scalar_one_or_none()
        hint = usage.display_name if usage else None

    # Layer 2: fuzzy match against the target platform's taxonomy.
    # Done outside the session because the connector calls are async/network.
    if not hint:
        return []

    if dst == Platform.REVERB:
        from listing_studio.platforms.reverb import ReverbConnector
        connector_r = ReverbConnector()
        if not await connector_r.is_connected():
            return []
        matches = await connector_r.search_taxonomy(hint, limit=5)
        return [
            {
                "platform": dst.value,
                "external_id": m["uuid"],
                "display_name": m["name"],
                "display_path": m.get("full_name") or m["name"],
                "confidence": 0.4,
                "source": "fuzzy",
            }
            for m in matches
        ]

    if dst == Platform.EBAY:
        from listing_studio.platforms.ebay import EbayConnector
        connector_e = EbayConnector()
        if not await connector_e.is_connected():
            return []
        matches = await connector_e.search_taxonomy(hint, limit=5)
        return [
            {
                "platform": dst.value,
                "external_id": str(m["category_id"]),
                "display_name": m["name"],
                "display_path": m.get("full_name") or m["name"],
                "confidence": 0.4 if m.get("is_leaf") else 0.2,
                "source": "fuzzy",
            }
            for m in matches
        ]

    # Squarespace has no enforced taxonomy to fuzzy-match against
    return []


@app.get("/api/categories/usage/recent")
async def get_recent_category_usage(platform: str, limit: int = 8) -> list[dict]:
    """Return the most recently used categories on a given platform.

    Feeds the "Recent" section above search results in each platform's
    category picker. Capped at ``limit`` rows (default 8).
    """
    from listing_studio.core import category_suggest
    from listing_studio.core.models import Platform

    try:
        plat = Platform(platform)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown platform: {platform}") from exc

    with session_scope() as session:
        return category_suggest.get_recent(session, plat, limit=limit)


# ---------------------------------------------------------------------------
# NAS photo browsing
# ---------------------------------------------------------------------------


@app.get("/api/nas/roots")
async def get_nas_roots() -> list[dict]:
    """Return the configured NAS roots with reachability flags."""
    from listing_studio.core.nas import get_roots
    return get_roots()


@app.post("/api/photos/pick-local")
async def pick_local_photos_endpoint() -> dict:
    """Open the OS native file dialog and return selected photo paths.

    Failover for when the NAS isn't reachable, but also useful when Dad has
    a one-off photo on his desktop he wants to use. The dialog is blocking,
    so we run it on a worker thread to avoid stalling FastAPI's event loop.

    Each returned file's parent directory is registered with the NAS module's
    in-memory allowlist, so the existing thumbnail/image/attach endpoints
    accept these paths the same way they accept NAS paths. The allowlist
    is session-scoped (cleared on restart) and only ever gets entries from
    this endpoint - paths from clients can't bypass NAS validation.

    Returns:
        {"paths": ["C:/Users/.../photo1.jpg", ...]} - empty if cancelled.
    """
    import asyncio
    import logging

    from listing_studio.core.local_picker import pick_local_photos
    from listing_studio.core.nas import PathOutsideRoots, register_local_file

    log = logging.getLogger(__name__)

    # The dialog blocks. Push to a thread so async handlers above us don't
    # stall while the user thinks about which photos to pick.
    paths = await asyncio.to_thread(pick_local_photos)

    registered: list[str] = []
    for path in paths:
        try:
            resolved = register_local_file(path)
            registered.append(str(resolved))
        except PathOutsideRoots as exc:
            # register_local_file rejects nonexistent files. Skip and log -
            # the dialog occasionally returns ghosts on some Windows shells.
            log.warning("Skipping unregisterable local path %s: %s", path, exc)

    return {"paths": registered}


@app.get("/api/nas/list")
async def list_nas_folder(path: str) -> dict:
    """List the contents of a NAS folder.

    Query param ``path`` must be inside one of the configured roots. Returns
    subfolders and image files; non-image files are filtered out.
    """
    from listing_studio.core.nas import (
        PathOutsideRoots,
        list_folder,
    )

    try:
        return list_folder(path)
    except PathOutsideRoots as exc:
        raise HTTPException(403, f"Path outside configured roots: {exc}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/nas/thumbnail")
async def get_nas_thumbnail(path: str) -> FileResponse:
    """Return a cached JPEG thumbnail for an image on the NAS.

    The first call for a given image generates the thumbnail (a few hundred
    milliseconds typically); subsequent calls serve straight from cache.
    """
    from listing_studio.core.nas import (
        PathOutsideRoots,
        get_thumbnail_path,
    )

    try:
        thumb = get_thumbnail_path(path)
    except PathOutsideRoots as exc:
        raise HTTPException(403, f"Path outside configured roots: {exc}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        # PIL errors (corrupt image, unsupported format) end up here
        raise HTTPException(500, f"Could not generate thumbnail: {exc}") from exc

    return FileResponse(thumb, media_type="image/jpeg")


@app.get("/api/nas/image")
async def get_nas_image(path: str) -> FileResponse:
    """Stream the full-resolution image from the NAS.

    Used for previews and (eventually) for uploading to marketplaces.
    """
    from listing_studio.core.nas import PathOutsideRoots, validate_path

    try:
        image = validate_path(path)
    except PathOutsideRoots as exc:
        raise HTTPException(403, f"Path outside configured roots: {exc}") from exc

    if not image.exists() or not image.is_file():
        raise HTTPException(404, f"Image not found: {path}")

    # Let FastAPI guess the media type from the extension. JPEG, PNG, etc all
    # map sensibly.
    return FileResponse(image)


# ---------------------------------------------------------------------------
# Reverb listing creation (draft mode for testing)
# ---------------------------------------------------------------------------


@app.get("/api/platforms/reverb/shipping-profiles")
async def get_reverb_shipping_profiles() -> list[dict]:
    """Return the user's Reverb shipping profiles for UI selection.

    Empty list if not connected or no profiles exist.
    """
    from listing_studio.platforms.reverb import ReverbConnector
    connector = ReverbConnector()
    if not await connector.is_connected():
        return []
    return await connector.fetch_shipping_profiles()


@app.post("/api/templates/{template_id}/post-to-reverb")
async def post_template_to_reverb(template_id: int, payload: dict | None = None) -> dict:
    """Create a draft Reverb listing from a template.

    Photo handling:
        Reverb wants public URLs, not binary uploads. If a photo host is
        configured (see /api/settings/photo-host), we normalize each NAS
        photo (EXIF-rotate, downscale, JPEG re-encode), upload it there, and
        pass the resulting URLs to Reverb. If no host is configured, the
        draft is created without photos and the UI prompts Dad to drag
        them into the Reverb web UI manually.

    Body (all optional):
        {
            "shipping_profile_id": "1234",
            "skip_photos": false   // force the no-photos manual-drag path
                                   // even if a host is configured
        }

    Returns:
        {
            "listing_id": "...",
            "state": "draft",
            "url": "https://reverb.com/...",
            "photo_results": {
                "uploaded": 3,
                "failed": 1,
                "errors": [...],
                "host_configured": true,    // whether auto-upload was attempted
                "host_display_name": "ImgBB" | null,
            }
        }
    """
    from listing_studio.core.models import Preference, Template
    from listing_studio.core.photo_host import get_configured_host
    from listing_studio.core.photo_processor import (
        NormalizeError,
        normalize_for_upload,
    )
    from listing_studio.platforms.base import PostingError
    from listing_studio.platforms.reverb import ReverbConnector

    payload = payload or {}
    shipping_profile_id = payload.get("shipping_profile_id")
    skip_photos = bool(payload.get("skip_photos", False))

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")

        # Pull "listing tail" boilerplate from preferences
        tail_pref = session.execute(
            select(Preference).where(Preference.key == "reverb_listing_tail")
        ).scalar_one_or_none()
        listing_tail = (tail_pref.value if tail_pref else "") or ""

        # Snapshot photo paths before we leave the session
        photo_paths = sorted(
            [(p.sort_order, p.source_path) for p in template.photos],
            key=lambda x: x[0],
        )
        photo_paths = [path for (_order, path) in photo_paths]

        # Pull category UUIDs if a category is assigned. These take precedence
        # over the legacy reverb_category string field when posting.
        category_reverb_uuid = None
        category_subcategory_uuids: list[str] = []
        if template.category_id and template.category:
            category_reverb_uuid = template.category.reverb_category_uuid
            category_subcategory_uuids = list(template.category.reverb_subcategory_uuids or [])

        # Need to access template fields outside the session for the async
        # connector call - detach by copying values we need
        template_copy_data = {
            "id": template.id,
            "name": template.name,
            "title": template.title,
            "description": template.description,
            "brand": template.brand,
            "model": template.model,
            "year": template.year,
            "finish": template.finish,
            "reverb_category": template.reverb_category,
            "reverb_subcategories": template.reverb_subcategories,
            "condition": template.condition,
            "base_price_cents": template.base_price_cents,
            "quantity": template.quantity,
            # Shipping config - per-listing rates beat any default profile
            "reverb_shipping_type": template.reverb_shipping_type,
            "reverb_shipping_flat_cents": template.reverb_shipping_flat_cents,
            # Category-resolved UUIDs - if set, the connector uses these
            # directly instead of resolving from the string field
            "_resolved_reverb_uuid": category_reverb_uuid,
            "_resolved_reverb_subcategory_uuids": category_subcategory_uuids,
        }

    # Now make the API calls outside the session (httpx is async)
    connector = ReverbConnector()
    if not await connector.is_connected():
        raise HTTPException(400, "Reverb not connected. Add token in Settings.")

    # Build a lightweight stand-in object that quacks like a Template for create_draft.
    # This avoids passing a detached SQLAlchemy instance across session boundaries.
    class _T:
        pass
    t = _T()
    for k, v in template_copy_data.items():
        setattr(t, k, v)

    # Photo pre-upload: normalize each NAS photo and ship it to the configured
    # image host. We do this BEFORE create_draft so we can pass the URLs into
    # the create payload (Reverb's API has no working way to attach photos
    # after-the-fact via binary upload; it only accepts URLs).
    photo_results: dict = {
        "uploaded": 0,
        "failed": 0,
        "errors": [],
        "host_configured": False,
        "host_display_name": None,
    }
    photo_urls: list[str] = []

    host = None if skip_photos else get_configured_host()
    if host is not None:
        photo_results["host_configured"] = True
        photo_results["host_display_name"] = host.display_name

    if host is not None and photo_paths:
        from pathlib import Path as PathLib

        from listing_studio.core.photo_host import PhotoHostError

        for idx, photo_path_str in enumerate(photo_paths):
            photo_path = PathLib(photo_path_str)
            display_name = photo_path.name
            try:
                normalized = normalize_for_upload(photo_path)
                # Prefix with sort order so if Dad later compares the host's
                # filenames they match his picker order.
                upload_filename = f"{idx + 1:02d}_{normalized.filename}"
                url = await host.upload(normalized.data, upload_filename)
                photo_urls.append(url)
                photo_results["uploaded"] += 1
            except NormalizeError as exc:
                photo_results["failed"] += 1
                photo_results["errors"].append(f"{display_name}: {exc}")
            except PhotoHostError as exc:
                photo_results["failed"] += 1
                photo_results["errors"].append(f"{display_name}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                photo_results["failed"] += 1
                photo_results["errors"].append(
                    f"{display_name}: {type(exc).__name__}: {exc}"
                )

    try:
        result = await connector.create_draft(
            t,
            listing_tail=listing_tail,
            shipping_profile_id=shipping_profile_id,
            photo_urls=photo_urls or None,
        )
    except PostingError as exc:
        raise HTTPException(400, str(exc)) from exc

    listing_id = result.get("id")
    if not listing_id:
        raise HTTPException(500, "Reverb didn't return a listing ID")

    return {
        "listing_id": str(listing_id),
        "state": result.get("state"),
        "url": result.get("url"),
        "photo_results": photo_results,
    }


@app.post("/api/templates/{template_id}/open-photo-folder")
async def open_template_photo_folder(template_id: int) -> dict:
    """Open Windows Explorer at the folder containing this template's photos.

    Pairs with the "Open Draft on Reverb" flow: Dad gets the Reverb draft
    edit page in his browser and Explorer pointing at the photos folder,
    side by side, for an easy drag-and-drop.

    If the template has photos from multiple folders, we open the deepest
    common ancestor. If it has no photos at all, we 400.

    Returns:
        {"opened_path": "Z:\\\\..."}  # the path we opened
    """
    import os
    import subprocess
    import sys

    from listing_studio.core.models import Template

    with session_scope() as session:
        template = session.get(Template, template_id)
        if template is None:
            raise HTTPException(404, f"Template {template_id} not found")

        photo_paths = [p.source_path for p in template.photos]

    if not photo_paths:
        raise HTTPException(400, "This template has no photos attached.")

    # Compute the folder to open. If all photos share a parent directory,
    # use that. Otherwise fall back to the deepest common ancestor across
    # all photos. This handles both "all photos in one folder" (the common
    # case) and "photos pulled from multiple folders" (rare but possible).
    photo_parents = [str(Path(p).parent) for p in photo_paths]
    if len(set(photo_parents)) == 1:
        folder_to_open = photo_parents[0]
    else:
        folder_to_open = os.path.commonpath(photo_parents)

    folder_path = Path(folder_to_open)
    if not folder_path.exists():
        raise HTTPException(
            404,
            f"Photo folder no longer exists: {folder_to_open}. "
            "The NAS may be disconnected or the folder was moved.",
        )

    # Open with the platform's file manager. On Windows we use Explorer
    # explicitly so we can also select a file if useful (we don't bother
    # selecting since the photos are usually adjacent and Dad wants to
    # multi-select them all). On Linux/Mac we fall back to xdg-open / open
    # for dev mode - Dad's machine is Windows so this is just safety.
    try:
        if sys.platform.startswith("win"):
            # os.startfile is the simplest Windows-native folder open
            os.startfile(str(folder_path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder_path)])
        else:
            subprocess.Popen(["xdg-open", str(folder_path)])
    except Exception as exc:
        raise HTTPException(500, f"Couldn't open folder: {exc}") from exc

    return {"opened_path": str(folder_path)}


# ---------------------------------------------------------------------------
# Static UI files
# ---------------------------------------------------------------------------


# Mount /static for CSS, JS, fonts, images
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    """Serve the main window HTML."""
    return FileResponse(_TEMPLATES_DIR / "index.html")

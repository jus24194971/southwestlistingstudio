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

from fastapi import FastAPI, HTTPException
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
        import threading

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
    from listing_studio.core.models import Tag, Template, TemplatePhoto, TemplateTag
    from listing_studio.core.nas import PathOutsideRoots, validate_path
    from datetime import datetime as _datetime

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
# NAS photo browsing
# ---------------------------------------------------------------------------


@app.get("/api/nas/roots")
async def get_nas_roots() -> list[dict]:
    """Return the configured NAS roots with reachability flags."""
    from listing_studio.core.nas import get_roots
    return get_roots()


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
# Static UI files
# ---------------------------------------------------------------------------


# Mount /static for CSS, JS, fonts, images
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    """Serve the main window HTML."""
    return FileResponse(_TEMPLATES_DIR / "index.html")

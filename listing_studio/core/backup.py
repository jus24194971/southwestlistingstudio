"""Backup and restore for Listing Studio data (.sals file format).

A .sals file is a plain ZIP archive with a fixed structure:

    manifest.json          - metadata: app version, exported_at, contents
    templates.json         - every Template + its photo references + per-platform overrides
    categories.json        - every Category with full Reverb/eBay/Squarespace mapping
    category_mappings.json - learned + shipped cross-platform pairings
    category_usage.json    - per-platform recently-used tracking
    tags.json              - tag dictionary
    preferences.json       - DB-stored user preferences
    credentials.json       - (optional) API tokens, ONLY if user opted in at export time

The format is deliberately readable - a sufficiently curious user can unzip it
and inspect/edit the JSON before re-importing. We chose ZIP over a sqlite dump
so the file is human-debuggable and portable across platforms.

Photo files themselves are NOT included in the backup (the source images live
on the NAS or local picker history). Their `source_path` strings are preserved,
so re-attaching on the same NAS is automatic; on a different machine the photos
need to be re-picked.

Credentials handling: opt-in only. The export endpoint requires an explicit
``include_credentials`` flag. There is no built-in encryption in v0.5.3 - the
user is expected to keep the .sals file in a secure location. Future versions
can add Fernet-based passphrase encryption without breaking the file format
(we'd add an encrypted file alongside the plaintext credentials.json).
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from listing_studio import __version__
from listing_studio.core.credentials import (
    clear_credentials,
    clear_service_credentials,
    load_credentials,
    load_service_credentials,
    store_credentials,
    store_service_credentials,
)
from listing_studio.core.models import (
    Category,
    CategoryMapping,
    CategoryUsage,
    Platform,
    Preference,
    Tag,
    Template,
    TemplatePhoto,
    TemplateTag,
)

logger = logging.getLogger(__name__)

# Manifest format version. Bump this if we make breaking structural changes
# to the file layout (e.g. rename a top-level file). Restore code can refuse
# to import a newer format than it knows about.
BACKUP_FORMAT_VERSION = 1


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_backup(session: Session, include_credentials: bool = False) -> bytes:
    """Build a .sals backup of the user's data and return it as bytes.

    Args:
        session: An active DB session for reading.
        include_credentials: If True, include stored API tokens from the
            keyring in the archive. The caller MUST surface a warning to
            the user before setting this to True - the resulting file
            contains secrets and should be treated like a password.

    Returns:
        ZIP archive bytes ready to write to a .sals file.
    """
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(
            _manifest(include_credentials=include_credentials),
            indent=2,
        ))
        zf.writestr("templates.json", json.dumps(_dump_templates(session), indent=2))
        zf.writestr("categories.json", json.dumps(_dump_categories(session), indent=2))
        zf.writestr("category_mappings.json",
                    json.dumps(_dump_category_mappings(session), indent=2))
        zf.writestr("category_usage.json",
                    json.dumps(_dump_category_usage(session), indent=2))
        zf.writestr("tags.json", json.dumps(_dump_tags(session), indent=2))
        zf.writestr("preferences.json", json.dumps(_dump_preferences(session), indent=2))
        if include_credentials:
            zf.writestr("credentials.json", json.dumps(_dump_credentials(), indent=2))

    payload.seek(0)
    return payload.read()


def _manifest(include_credentials: bool) -> dict[str, Any]:
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(),
        "contents": {
            "templates": True,
            "categories": True,
            "category_mappings": True,
            "category_usage": True,
            "tags": True,
            "preferences": True,
            "credentials": include_credentials,
        },
        "notes": (
            "This is a Listing Studio backup (.sals). It contains your "
            "templates, categories, and settings. " +
            ("Credentials INCLUDED - treat this file like a password." if include_credentials
             else "Credentials NOT included - reconnect each platform after import.")
        ),
    }


def _dump_templates(session: Session) -> list[dict]:
    rows = session.execute(select(Template)).scalars().all()
    out = []
    for t in rows:
        photos = sorted(t.photos, key=lambda p: p.sort_order)
        out.append({
            "id": t.id,
            "name": t.name,
            "title": t.title,
            "description": t.description,
            "brand": t.brand,
            "model": t.model,
            "year": t.year,
            "finish": t.finish,
            "reverb_category": t.reverb_category,
            "reverb_subcategories": t.reverb_subcategories,
            "condition": t.condition,
            "base_price_cents": t.base_price_cents,
            "quantity": t.quantity,
            "weight_oz": t.weight_oz,
            "category_id": t.category_id,
            "folder": t.folder,
            "is_starred": t.is_starred,
            "platform_overrides": t.platform_overrides,
            "default_platforms": t.default_platforms,
            "shipping_method": t.shipping_method,
            "shipping_cost_cents": t.shipping_cost_cents,
            "reverb_shipping_type": t.reverb_shipping_type,
            "reverb_shipping_flat_cents": t.reverb_shipping_flat_cents,
            "ebay_shipping_type": t.ebay_shipping_type,
            "ebay_shipping_override_cents": t.ebay_shipping_override_cents,
            "item_specifics": t.item_specifics or {},
            "last_posted_at": t.last_posted_at.isoformat() if t.last_posted_at else None,
            "post_count": t.post_count,
            "photos": [
                {
                    "source_path": p.source_path,
                    "file_hash": p.file_hash,
                    "sort_order": p.sort_order,
                }
                for p in photos
            ],
            "tag_names": [tag.name for tag in t.tags],
        })
    return out


def _dump_categories(session: Session) -> list[dict]:
    rows = session.execute(select(Category)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "reverb_category_uuid": c.reverb_category_uuid,
            "reverb_category_full_name": c.reverb_category_full_name,
            "reverb_subcategory_uuids": c.reverb_subcategory_uuids,
            "reverb_subcategory_names": c.reverb_subcategory_names,
            "ebay_category_id": c.ebay_category_id,
            "ebay_category_name": c.ebay_category_name,
            "ebay_category_path": c.ebay_category_path,
            "ebay_leaf": c.ebay_leaf,
            "squarespace_store_page_id": c.squarespace_store_page_id,
            "squarespace_store_page_name": c.squarespace_store_page_name,
            "platform_config": c.platform_config,
            "default_condition": c.default_condition,
            "default_weight_oz": c.default_weight_oz,
            "default_shipping_method": c.default_shipping_method,
        }
        for c in rows
    ]


def _dump_category_mappings(session: Session) -> list[dict]:
    rows = session.execute(select(CategoryMapping)).scalars().all()
    return [
        {
            "platform_a": m.platform_a.value,
            "external_id_a": m.external_id_a,
            "name_a": m.name_a,
            "platform_b": m.platform_b.value,
            "external_id_b": m.external_id_b,
            "name_b": m.name_b,
            "confidence": m.confidence,
            "source": m.source,
        }
        for m in rows
    ]


def _dump_category_usage(session: Session) -> list[dict]:
    rows = session.execute(select(CategoryUsage)).scalars().all()
    return [
        {
            "platform": u.platform.value,
            "external_id": u.external_id,
            "display_name": u.display_name,
            "display_path": u.display_path,
            "last_used_at": u.last_used_at.isoformat() if u.last_used_at else None,
            "use_count": u.use_count,
        }
        for u in rows
    ]


def _dump_tags(session: Session) -> list[dict]:
    rows = session.execute(select(Tag)).scalars().all()
    return [{"name": t.name} for t in rows]


def _dump_preferences(session: Session) -> dict[str, str]:
    rows = session.execute(select(Preference)).scalars().all()
    return {p.key: p.value for p in rows}


def _dump_credentials() -> dict[str, Any]:
    """Read every platform and service credential from the keyring.

    The output dict is keyed by category for clarity when humans read the
    JSON: ``{"platforms": {...}, "services": {...}}``.
    """
    platforms: dict[str, Any] = {}
    for platform in Platform:
        creds = load_credentials(platform)
        if creds is not None:
            platforms[platform.value] = creds

    # Known service credentials. Add more entries here as new services
    # (Cloudinary, R2, etc.) ship.
    services: dict[str, Any] = {}
    for service_name in ("imgbb",):
        creds = load_service_credentials(service_name)
        if creds is not None:
            services[service_name] = creds

    return {"platforms": platforms, "services": services}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_backup(session: Session, data: bytes, *, restore_credentials: bool = True) -> dict:
    """Restore a .sals backup into the current database.

    This is DESTRUCTIVE: it clears the existing templates, categories,
    mappings, usage, tags, and preferences before importing the backup's
    versions. The caller (the UI) is responsible for confirming with the
    user before calling this.

    Args:
        session: Active DB session. The caller commits.
        data: Raw bytes of the .sals file.
        restore_credentials: If False, skip restoring API tokens even if
            they're present in the archive (lets the user import data
            without overwriting locally-stored tokens).

    Returns:
        A dict summarizing what was restored - counts per category, plus
        a `warnings` list for any non-fatal issues found during parse.

    Raises:
        ValueError if the file isn't a valid .sals (bad zip, missing
        manifest, unknown format version).
    """
    warnings: list[str] = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid .sals file (bad zip): {exc}") from exc

    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError as exc:
        raise ValueError("Missing manifest.json - not a Listing Studio backup") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is malformed: {exc}") from exc

    fmt = manifest.get("format_version")
    if fmt is None or fmt > BACKUP_FORMAT_VERSION:
        raise ValueError(
            f"Backup format version {fmt} is newer than this app supports "
            f"({BACKUP_FORMAT_VERSION}). Update the app first.",
        )

    # Wipe existing data BEFORE inserting - if the import fails partway,
    # the user can re-import from a safety backup the UI made.
    _clear_user_data(session)

    counts: dict[str, int] = {}

    # Tags first (they may be referenced by templates)
    tag_lookup: dict[str, Tag] = {}
    try:
        tags = json.loads(zf.read("tags.json"))
    except KeyError:
        tags = []
    for entry in tags:
        name = (entry.get("name") or "").strip().lower()
        if not name:
            continue
        tag = Tag(name=name)
        session.add(tag)
        tag_lookup[name] = tag
    counts["tags"] = len(tag_lookup)
    session.flush()  # ensure tag IDs exist for the join inserts below

    # Categories (templates reference category_id)
    cat_lookup: dict[int, Category] = {}
    try:
        cats = json.loads(zf.read("categories.json"))
    except KeyError:
        cats = []
    for c in cats:
        cat = Category(
            name=c["name"],
            reverb_category_uuid=c.get("reverb_category_uuid"),
            reverb_category_full_name=c.get("reverb_category_full_name"),
            reverb_subcategory_uuids=c.get("reverb_subcategory_uuids") or [],
            reverb_subcategory_names=c.get("reverb_subcategory_names") or [],
            ebay_category_id=c.get("ebay_category_id"),
            ebay_category_name=c.get("ebay_category_name"),
            ebay_category_path=c.get("ebay_category_path"),
            ebay_leaf=c.get("ebay_leaf", True),
            squarespace_store_page_id=c.get("squarespace_store_page_id"),
            squarespace_store_page_name=c.get("squarespace_store_page_name"),
            platform_config=c.get("platform_config") or {},
            default_condition=c.get("default_condition"),
            default_weight_oz=c.get("default_weight_oz"),
            default_shipping_method=c.get("default_shipping_method"),
        )
        session.add(cat)
        # Remember the OLD id so templates can re-link.
        original_id = c.get("id")
        if original_id is not None:
            cat_lookup[original_id] = cat
    counts["categories"] = len(cat_lookup)
    session.flush()

    # Templates (with photos + tag links)
    try:
        templates = json.loads(zf.read("templates.json"))
    except KeyError:
        templates = []
    for t in templates:
        original_cat_id = t.get("category_id")
        cat_ref = cat_lookup.get(original_cat_id) if original_cat_id else None

        tmpl = Template(
            name=t["name"],
            title=t["title"],
            description=t.get("description", ""),
            brand=t.get("brand"),
            model=t.get("model"),
            year=t.get("year"),
            finish=t.get("finish"),
            reverb_category=t.get("reverb_category"),
            reverb_subcategories=t.get("reverb_subcategories"),
            condition=t.get("condition", "new_old_stock"),
            base_price_cents=t.get("base_price_cents", 0),
            quantity=t.get("quantity", 1),
            weight_oz=t.get("weight_oz", 0.0),
            folder=t.get("folder", "Uncategorized"),
            is_starred=t.get("is_starred", False),
            platform_overrides=t.get("platform_overrides") or {},
            default_platforms=t.get("default_platforms") or [],
            shipping_method=t.get("shipping_method", "usps_first_class"),
            shipping_cost_cents=t.get("shipping_cost_cents", 0),
            reverb_shipping_type=t.get("reverb_shipping_type"),
            reverb_shipping_flat_cents=t.get("reverb_shipping_flat_cents", 0),
            ebay_shipping_type=t.get("ebay_shipping_type"),
            ebay_shipping_override_cents=t.get("ebay_shipping_override_cents", 0),
            item_specifics=t.get("item_specifics") or {},
            post_count=t.get("post_count", 0),
        )
        if cat_ref is not None:
            tmpl.category = cat_ref
        if t.get("last_posted_at"):
            try:
                tmpl.last_posted_at = datetime.fromisoformat(t["last_posted_at"])
            except (TypeError, ValueError):
                warnings.append(f"Skipped bad last_posted_at on template '{t.get('name')}'")
        session.add(tmpl)
        session.flush()  # need tmpl.id for photo + tag links

        # Photos
        for p in t.get("photos") or []:
            session.add(TemplatePhoto(
                template_id=tmpl.id,
                source_path=p["source_path"],
                file_hash=p.get("file_hash"),
                sort_order=p.get("sort_order", 0),
            ))

        # Tag links
        for tag_name in t.get("tag_names") or []:
            tag = tag_lookup.get(tag_name.strip().lower())
            if tag is None:
                continue
            session.add(TemplateTag(template_id=tmpl.id, tag_id=tag.id))

    counts["templates"] = len(templates)

    # Category mappings + usage
    try:
        mappings = json.loads(zf.read("category_mappings.json"))
    except KeyError:
        mappings = []
    for m in mappings:
        try:
            session.add(CategoryMapping(
                platform_a=Platform(m["platform_a"]),
                external_id_a=m["external_id_a"],
                name_a=m["name_a"],
                platform_b=Platform(m["platform_b"]),
                external_id_b=m["external_id_b"],
                name_b=m["name_b"],
                confidence=m.get("confidence", 1.0),
                source=m.get("source", "learned"),
            ))
        except (KeyError, ValueError) as exc:
            warnings.append(f"Skipped malformed category mapping: {exc}")
    counts["category_mappings"] = len(mappings)

    try:
        usage = json.loads(zf.read("category_usage.json"))
    except KeyError:
        usage = []
    for u in usage:
        try:
            entry = CategoryUsage(
                platform=Platform(u["platform"]),
                external_id=u["external_id"],
                display_name=u["display_name"],
                display_path=u.get("display_path"),
                use_count=u.get("use_count", 1),
            )
            if u.get("last_used_at"):
                try:
                    entry.last_used_at = datetime.fromisoformat(u["last_used_at"])
                except (TypeError, ValueError):
                    pass
            session.add(entry)
        except (KeyError, ValueError) as exc:
            warnings.append(f"Skipped malformed category usage: {exc}")
    counts["category_usage"] = len(usage)

    # Preferences
    try:
        prefs = json.loads(zf.read("preferences.json"))
    except KeyError:
        prefs = {}
    for key, value in prefs.items():
        session.add(Preference(key=key, value=str(value)))
    counts["preferences"] = len(prefs)

    # Credentials (last - independent of DB session)
    counts["credentials"] = 0
    if restore_credentials and manifest.get("contents", {}).get("credentials"):
        try:
            creds = json.loads(zf.read("credentials.json"))
        except KeyError:
            creds = {}
        for platform_value, blob in (creds.get("platforms") or {}).items():
            try:
                store_credentials(Platform(platform_value), blob)
                counts["credentials"] += 1
            except (ValueError, RuntimeError) as exc:
                warnings.append(f"Couldn't restore {platform_value} credentials: {exc}")
        for service_name, blob in (creds.get("services") or {}).items():
            try:
                store_service_credentials(service_name, blob)
                counts["credentials"] += 1
            except RuntimeError as exc:
                warnings.append(f"Couldn't restore {service_name} credentials: {exc}")

    return {
        "manifest": manifest,
        "counts": counts,
        "warnings": warnings,
    }


def _clear_user_data(session: Session) -> None:
    """Wipe the tables that the backup overwrites, in FK-safe order."""
    # Junction first to satisfy FK constraints
    session.execute(TemplateTag.__table__.delete())
    session.execute(TemplatePhoto.__table__.delete())
    session.execute(Template.__table__.delete())
    session.execute(Category.__table__.delete())
    session.execute(CategoryMapping.__table__.delete())
    session.execute(CategoryUsage.__table__.delete())
    session.execute(Tag.__table__.delete())
    session.execute(Preference.__table__.delete())
    session.flush()


def clear_all_credentials() -> None:
    """Helper: remove every stored credential (for "wipe before import" UX).

    Currently unused but exposed for completeness so the import endpoint
    can offer "replace credentials" semantics in the future.
    """
    for platform in Platform:
        clear_credentials(platform)
    for service_name in ("imgbb",):
        clear_service_credentials(service_name)

"""Cross-platform category suggestion engine + recent-used tracking.

This module answers two questions:

1. **"Dad just picked a Reverb category. What's the corresponding eBay
   category?"** — and vice versa. Suggestions come from three layers, in
   confidence order:

      a) Shipped seed mappings (data/seed_category_mappings.json) — curated
         hand-picked pairs we know are right.
      b) Learned mappings (category_mappings table) — recorded automatically
         every time the user saves a Category with two or more platforms set.
      c) Fuzzy name match against the target platform's cached taxonomy —
         lowest confidence, used only when (a) and (b) come up empty.

2. **"Which categories has Dad been using recently on each platform?"** —
   tracked in the category_usage table, updated on every Category save.
   Powers the "Recent" section above search results in the pickers.

The two layers share storage but serve different purposes; keeping them in
one module keeps the call sites in api.py clean.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from listing_studio.core.models import CategoryMapping, CategoryUsage, Platform

logger = logging.getLogger(__name__)


# Path to the shipped JSON. Lives in listing_studio/data/ so it's bundled
# inside the .exe; reading via Path(__file__) works in both the dev and
# PyInstaller-packaged contexts.
_SEED_JSON_PATH = Path(__file__).parent.parent / "data" / "seed_category_mappings.json"


# ---------------------------------------------------------------------------
# Shipped seed loading (idempotent; safe to call every startup)
# ---------------------------------------------------------------------------


def seed_shipped_mappings_if_missing(session: Session) -> int:
    """Load the shipped seed JSON into the category_mappings table.

    Idempotent: rows already present (same a/b pair) are not duplicated.
    Entries with null external_ids on either side are skipped - they're
    placeholders waiting for verified IDs.

    Returns the number of mapping rows inserted (counts both directions of
    each pair as separate rows).
    """
    try:
        data = json.loads(_SEED_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Seed mappings file not found at %s", _SEED_JSON_PATH)
        return 0
    except json.JSONDecodeError as exc:
        logger.error("Seed mappings JSON is malformed: %s", exc)
        return 0

    entries = data.get("mappings") or []
    if not isinstance(entries, list):
        return 0

    inserted = 0
    for entry in entries:
        rev_uuid = entry.get("reverb_uuid")
        rev_name = entry.get("reverb_full_name") or entry.get("label") or ""
        ebay_id = entry.get("ebay_id")
        ebay_name = entry.get("ebay_full_name") or entry.get("label") or ""

        # Skip placeholders - we need both sides resolved to seed a pair
        if not rev_uuid or ebay_id is None or not ebay_name:
            continue

        # Insert both directions if not already present
        for (pa, ea, na, pb, eb, nb) in (
            (Platform.REVERB, rev_uuid, rev_name, Platform.EBAY, str(ebay_id), ebay_name),
            (Platform.EBAY, str(ebay_id), ebay_name, Platform.REVERB, rev_uuid, rev_name),
        ):
            exists = session.execute(
                select(CategoryMapping).where(
                    CategoryMapping.platform_a == pa,
                    CategoryMapping.external_id_a == ea,
                    CategoryMapping.platform_b == pb,
                    CategoryMapping.external_id_b == eb,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            session.add(CategoryMapping(
                platform_a=pa, external_id_a=ea, name_a=na,
                platform_b=pb, external_id_b=eb, name_b=nb,
                confidence=1.0, source="shipped",
            ))
            inserted += 1

    if inserted:
        logger.info("Seeded %d shipped category mapping rows", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Recording from Category saves
# ---------------------------------------------------------------------------


def record_category_save(session: Session, category) -> None:
    """Record cross-platform mappings + usage entries from a saved Category.

    Called from POST/PATCH /api/categories. We look at the Reverb, eBay,
    and Squarespace IDs on the saved row and:

    - Record a `CategoryUsage` bump for each populated platform (top of the
      "Recent" list next time Dad opens a picker).
    - Record `CategoryMapping` rows between every pair of populated
      platforms (so a Reverb pick can suggest the matching eBay next time,
      and vice versa).

    Both are upserts: existing rows are bumped/skipped, not duplicated.
    """
    # ---- Usage ----
    if category.reverb_category_uuid:
        record_usage(
            session,
            Platform.REVERB,
            category.reverb_category_uuid,
            category.reverb_category_full_name or category.name,
            category.reverb_category_full_name,
        )
    if category.ebay_category_id:
        record_usage(
            session,
            Platform.EBAY,
            str(category.ebay_category_id),
            category.ebay_category_name or category.name,
            category.ebay_category_path,
        )
    if category.squarespace_store_page_id:
        record_usage(
            session,
            Platform.SQUARESPACE,
            category.squarespace_store_page_id,
            category.squarespace_store_page_name or category.name,
            None,
        )

    # ---- Mappings (between any two populated platforms) ----
    triples: list[tuple[Platform, str, str]] = []
    if category.reverb_category_uuid:
        triples.append((
            Platform.REVERB, category.reverb_category_uuid,
            category.reverb_category_full_name or category.name,
        ))
    if category.ebay_category_id:
        triples.append((
            Platform.EBAY, str(category.ebay_category_id),
            category.ebay_category_path or category.ebay_category_name or category.name,
        ))
    if category.squarespace_store_page_id:
        triples.append((
            Platform.SQUARESPACE, category.squarespace_store_page_id,
            category.squarespace_store_page_name or category.name,
        ))

    # Record both directions for each unordered pair
    for i, (pa, ea, na) in enumerate(triples):
        for (pb, eb, nb) in triples[i + 1:]:
            _upsert_mapping(session, pa, ea, na, pb, eb, nb, source="learned")
            _upsert_mapping(session, pb, eb, nb, pa, ea, na, source="learned")


def _upsert_mapping(
    session: Session,
    pa: Platform, ea: str, na: str,
    pb: Platform, eb: str, nb: str,
    source: str = "learned",
) -> None:
    """Insert a CategoryMapping if the (a, ea, b, eb) pair doesn't exist."""
    exists = session.execute(
        select(CategoryMapping).where(
            CategoryMapping.platform_a == pa,
            CategoryMapping.external_id_a == ea,
            CategoryMapping.platform_b == pb,
            CategoryMapping.external_id_b == eb,
        )
    ).scalar_one_or_none()
    if exists is not None:
        # Optionally refresh the display name in case it changed
        if exists.name_a != na or exists.name_b != nb:
            exists.name_a = na
            exists.name_b = nb
        return
    session.add(CategoryMapping(
        platform_a=pa, external_id_a=ea, name_a=na,
        platform_b=pb, external_id_b=eb, name_b=nb,
        confidence=1.0, source=source,
    ))


def record_usage(
    session: Session,
    platform: Platform,
    external_id: str,
    display_name: str,
    display_path: str | None = None,
) -> None:
    """Insert-or-bump a CategoryUsage row.

    Increments use_count and refreshes last_used_at for existing rows;
    creates fresh rows otherwise.
    """
    existing = session.execute(
        select(CategoryUsage).where(
            CategoryUsage.platform == platform,
            CategoryUsage.external_id == external_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.use_count += 1
        existing.last_used_at = datetime.now()
        existing.display_name = display_name  # refresh in case it changed
        if display_path:
            existing.display_path = display_path
        return
    session.add(CategoryUsage(
        platform=platform,
        external_id=external_id,
        display_name=display_name,
        display_path=display_path,
        use_count=1,
        last_used_at=datetime.now(),
    ))


# ---------------------------------------------------------------------------
# Querying for the UI
# ---------------------------------------------------------------------------


def get_recent(session: Session, platform: Platform, limit: int = 8) -> list[dict]:
    """Return the most-recently-used categories on a given platform.

    Used by the picker's "Recent" header. Output is JSON-ready dicts to
    match the existing taxonomy-search shape.
    """
    stmt = (
        select(CategoryUsage)
        .where(CategoryUsage.platform == platform)
        .order_by(CategoryUsage.last_used_at.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "platform": platform.value,
            "external_id": r.external_id,
            "display_name": r.display_name,
            "display_path": r.display_path,
            "last_used_at": r.last_used_at.isoformat(),
            "use_count": r.use_count,
        }
        for r in rows
    ]


def suggest_for(
    session: Session,
    from_platform: Platform,
    from_external_id: str,
    to_platform: Platform,
    fuzzy_search: Callable[[str], list[dict]] | None = None,
    fuzzy_query_hint: str | None = None,
) -> list[dict]:
    """Suggest target-platform categories matching a source category.

    Three layers, returned in confidence order:

    1. **Direct mappings** in category_mappings (both shipped + learned).
       Highest confidence; if any found, we return them first.
    2. **Fuzzy fallback** via the optional ``fuzzy_search`` callable.
       Called only if layer 1 returned nothing AND ``fuzzy_query_hint`` is
       provided. The callable should take a query string and return a list
       of taxonomy entries shaped like ``{external_id, name, full_name}``.
       This is how we use Reverb's or eBay's cached taxonomy without this
       module needing to import the connectors.

    Output: list of dicts (JSON-ready) ranked by confidence.
    """
    suggestions: list[dict] = []

    # Layer 1: direct mappings (shipped + learned together)
    stmt = (
        select(CategoryMapping)
        .where(
            CategoryMapping.platform_a == from_platform,
            CategoryMapping.external_id_a == from_external_id,
            CategoryMapping.platform_b == to_platform,
        )
        .order_by(CategoryMapping.confidence.desc())
    )
    for row in session.execute(stmt).scalars():
        suggestions.append({
            "platform": to_platform.value,
            "external_id": row.external_id_b,
            "display_name": row.name_b,
            "display_path": row.name_b,  # name_b is typically the breadcrumb
            "confidence": row.confidence,
            "source": row.source,
        })

    if suggestions:
        return suggestions

    # Layer 2: fuzzy match if a hint and a search function were provided
    if fuzzy_search and fuzzy_query_hint:
        try:
            matches = fuzzy_search(fuzzy_query_hint)
        except Exception as exc:  # noqa: BLE001 - search may hit network
            logger.warning("Fuzzy search failed: %s", exc)
            matches = []
        # Cap at 5 - we don't want to drown the UI in low-confidence picks
        for m in matches[:5]:
            suggestions.append({
                "platform": to_platform.value,
                "external_id": str(m.get("external_id") or m.get("uuid") or ""),
                "display_name": m.get("name") or m.get("full_name") or "",
                "display_path": m.get("full_name") or m.get("name") or "",
                "confidence": 0.4,  # weak signal
                "source": "fuzzy",
            })

    return suggestions

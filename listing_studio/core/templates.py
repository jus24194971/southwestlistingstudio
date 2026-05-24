"""Template CRUD operations.

These functions sit between the API layer (FastAPI handlers) and the ORM
models. They take a Session and primitive arguments, return ORM models or
Pydantic schemas. Business rules (validation, defaults) live here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from listing_studio.core.models import Platform, Template
from listing_studio.core.schemas import TemplateCreate, TemplateUpdate


def list_templates(session: Session) -> list[Template]:
    """Return all templates, lightweight (no photos eagerly loaded)."""
    stmt = select(Template).order_by(
        Template.folder,
        Template.is_starred.desc(),
        Template.name,
    )
    return list(session.execute(stmt).scalars().all())


def list_templates_by_folder(session: Session) -> dict[str, list[Template]]:
    """Group templates by folder for the library sidebar."""
    templates = list_templates(session)
    grouped: dict[str, list[Template]] = {}
    for tmpl in templates:
        grouped.setdefault(tmpl.folder, []).append(tmpl)
    return grouped


def get_template(session: Session, template_id: int) -> Template | None:
    """Fetch one template by ID, with photos eagerly loaded."""
    stmt = (
        select(Template)
        .where(Template.id == template_id)
        .options(selectinload(Template.photos), selectinload(Template.tags))
    )
    return session.execute(stmt).scalar_one_or_none()


def create_template(session: Session, payload: TemplateCreate) -> Template:
    """Create a new template from a TemplateCreate payload."""
    tmpl = Template(
        name=payload.name,
        title=payload.title,
        description=payload.description,
        brand=payload.brand,
        model=payload.model,
        year=payload.year,
        finish=payload.finish,
        reverb_category=payload.reverb_category,
        reverb_subcategories=payload.reverb_subcategories,
        condition=payload.condition,
        base_price_cents=payload.base_price_cents,
        quantity=payload.quantity,
        weight_oz=payload.weight_oz,
        folder=payload.folder,
        category_id=payload.category_id,
        default_platforms=[p.value for p in payload.default_platforms],
        shipping_method=payload.shipping_method,
        shipping_cost_cents=payload.shipping_cost_cents,
        reverb_shipping_type=payload.reverb_shipping_type,
        reverb_shipping_flat_cents=payload.reverb_shipping_flat_cents,
        ebay_shipping_type=payload.ebay_shipping_type,
        ebay_shipping_override_cents=payload.ebay_shipping_override_cents,
        platform_overrides={},
    )
    session.add(tmpl)
    session.flush()  # Populate ID without committing
    return tmpl


def update_template(
    session: Session, template_id: int, payload: TemplateUpdate
) -> Template | None:
    """Patch an existing template. Only provided fields are touched."""
    tmpl = get_template(session, template_id)
    if tmpl is None:
        return None

    # ``model_dump(exclude_unset=True)`` only gives us fields the caller actually sent
    data = payload.model_dump(exclude_unset=True)

    # Special handling for fields that need transformation
    if "default_platforms" in data and data["default_platforms"] is not None:
        data["default_platforms"] = [
            p.value if isinstance(p, Platform) else p for p in data["default_platforms"]
        ]
    if "platform_overrides" in data and data["platform_overrides"] is not None:
        # Pydantic returns these as Pydantic models; convert to plain dicts for JSON storage
        data["platform_overrides"] = {
            k: (v.model_dump() if hasattr(v, "model_dump") else v)
            for k, v in data["platform_overrides"].items()
        }

    for key, value in data.items():
        setattr(tmpl, key, value)

    tmpl.updated_at = datetime.now(timezone.utc)
    return tmpl


def delete_template(session: Session, template_id: int) -> bool:
    """Delete a template (and cascade to its photos). Returns True if found."""
    tmpl = session.get(Template, template_id)
    if tmpl is None:
        return False
    session.delete(tmpl)
    return True


def record_post_attempt(session: Session, template_id: int) -> None:
    """Bump the template's last_posted_at and post_count.

    Called by the posting orchestrator after a Post Listing action completes,
    regardless of whether all platforms succeeded - we still want to remember
    that the user tried.
    """
    tmpl = session.get(Template, template_id)
    if tmpl is None:
        return
    tmpl.last_posted_at = datetime.now(timezone.utc)
    tmpl.post_count = (tmpl.post_count or 0) + 1


def resolve_price_cents(template: Template, platform: Platform) -> int:
    """Return the price (in cents) for this platform, applying any override."""
    override = template.platform_overrides.get(platform.value, {})
    return override.get("price_cents") or template.base_price_cents


def resolve_title(template: Template, platform: Platform) -> str:
    """Return the title to use for this platform, applying any override."""
    override = template.platform_overrides.get(platform.value, {})
    return override.get("title") or template.title


def resolve_description(template: Template, platform: Platform) -> str:
    """Return the description to use for this platform, applying any override."""
    override = template.platform_overrides.get(platform.value, {})
    return override.get("description") or template.description

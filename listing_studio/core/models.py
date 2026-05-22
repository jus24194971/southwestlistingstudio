"""SQLAlchemy ORM models.

Schema mirrors the technical spec but with Squarespace-aware additions:
- Per-platform price/title/description overrides include Squarespace
- ``Post`` records the platform's external listing ID so we can update or
  remove the listing later (e.g. set quantity to 0 after a sale elsewhere)
- ``InventorySyncLog`` records when we update quantities, for debugging
- ``WebhookSubscription`` tracks active webhook registrations (currently
  unused since we're starting with polling, but reserved for later)
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped  # noqa: F811  (re-imported for clarity)


class Base(DeclarativeBase):
    """Common base class for all ORM models."""

    pass


# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------


class Platform(str, enum.Enum):
    """Supported posting destinations.

    String-valued so the value persists cleanly to SQLite and JSON.
    """

    REVERB = "reverb"
    EBAY = "ebay"
    ETSY = "etsy"
    SQUARESPACE = "squarespace"
    FACEBOOK = "facebook"

    @classmethod
    def auto_post_platforms(cls) -> list["Platform"]:
        """Platforms we can post to via API (excludes Facebook)."""
        return [cls.REVERB, cls.EBAY, cls.ETSY, cls.SQUARESPACE]

    @classmethod
    def marketplace_platforms(cls) -> list["Platform"]:
        """Marketplaces (where Dad pays per-listing or per-sale fees)."""
        return [cls.REVERB, cls.EBAY, cls.ETSY]

    @property
    def display_name(self) -> str:
        return {
            Platform.REVERB: "Reverb",
            Platform.EBAY: "eBay",
            Platform.ETSY: "Etsy",
            Platform.SQUARESPACE: "Squarespace",
            Platform.FACEBOOK: "Facebook Marketplace",
        }[self]


# ---------------------------------------------------------------------------
# Categories - Dad's organizational buckets, with marketplace mappings
# ---------------------------------------------------------------------------


class Category(Base):
    """A user-defined category like "Tuners", "Pickups", or "Acoustic Guitars".

    Categories are the bridge between Dad's mental organization (he thinks
    "tuners") and each marketplace's required taxonomy (Reverb wants a UUID
    for "Parts > Tuners > Locking", eBay wants its own category_id, etc).

    Define once per category, reuse across many templates. Defaults stored
    here pre-fill the template form when creating a new template in this
    category (e.g. all tuners weigh ~3oz and ship USPS First Class).

    The ``platform_config`` JSON blob holds future per-platform mappings
    (eBay category_id, Etsy taxonomy_id, Squarespace store_page) that we'll
    add as we wire each platform. For now only Reverb fields are populated.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Dad's display name. Unique - we use it for the library sidebar grouping.
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)

    # Reverb-specific taxonomy mapping
    reverb_category_uuid: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reverb_category_full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Up to 2 subcategory UUIDs (Reverb allows max 3 categories total)
    reverb_subcategory_uuids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reverb_subcategory_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Future-proofing: per-platform extra config (eBay category_id, etc).
    # Keyed by platform.value: {"ebay": {...}, "etsy": {...}}
    platform_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Optional defaults that pre-fill template fields when creating a template
    # in this category. All nullable - if unset, no pre-fill.
    default_condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_weight_oz: Mapped[float | None] = mapped_column(nullable=True)
    default_shipping_method: Mapped[str | None] = mapped_column(String(60), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    templates: Mapped[list["Template"]] = relationship(back_populates="category")


# ---------------------------------------------------------------------------
# Templates - reusable listing definitions
# ---------------------------------------------------------------------------


class Template(Base):
    """A reusable listing template.

    Templates store the canonical data for a guitar part Dad sells repeatedly.
    Per-platform overrides live in ``platform_overrides`` (a JSON blob keyed by
    platform name).
    """

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Canonical fields (shared across all platforms unless overridden)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Reverb-aligned product fields. Optional because we may not always have them
    # (e.g. accessories like picks don't have a year). When creating a Reverb
    # listing we fall back to defaults if these are unset.
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    finish: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Reverb's category taxonomy uses UUIDs that we resolve via their API.
    # We store the human-readable name (e.g. "Acoustic Guitars") and an
    # optional subcategory string (comma-separated like "Built-in Electronics, Concert").
    # The connector turns these into the actual UUIDs at post time.
    reverb_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reverb_subcategories: Mapped[str | None] = mapped_column(String(300), nullable=True)

    condition: Mapped[str] = mapped_column(String(40), nullable=False, default="new_old_stock")
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    weight_oz: Mapped[float] = mapped_column(nullable=False, default=0.0)

    # Categorization
    # category_id is the new model - links to a Category row that holds Reverb
    # taxonomy UUIDs, defaults, etc. ``folder`` is kept for backward compatibility
    # with existing data; over time it'll be phased out in favor of category.
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    folder: Mapped[str] = mapped_column(String(120), nullable=False, default="Uncategorized", index=True)
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Per-platform overrides. Schema:
    #   {
    #     "reverb": {"price_cents": 9400, "title": "...", "description": "..."},
    #     "ebay":   {"price_cents": 9500, "category_id": "33034", ...},
    #     "etsy":   {"price_cents": 9200, ...},
    #     "squarespace": {"price_cents": 8500, ...},
    #     "facebook": {"price_cents": 8500, ...},
    #   }
    # Missing keys = use the canonical value.
    platform_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Which platforms are enabled by default for this template
    default_platforms: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Shipping defaults
    shipping_method: Mapped[str] = mapped_column(String(60), nullable=False, default="usps_first_class")
    shipping_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    last_posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    post_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    category: Mapped["Category | None"] = relationship(back_populates="templates")
    photos: Mapped[list["TemplatePhoto"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplatePhoto.sort_order",
    )
    posts: Mapped[list["Post"]] = relationship(back_populates="template")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="template_tags",
        back_populates="templates",
    )

    def __repr__(self) -> str:
        return f"<Template id={self.id} name={self.name!r}>"


class TemplatePhoto(Base):
    """A photo associated with a template.

    Stores a *path reference* to the source on the NAS, not the image bytes.
    The thumbnail cache (managed elsewhere) stores small JPGs locally for the UI.
    """

    __tablename__ = "template_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The path on the NAS (UNC or mapped drive, depending on Dad's machine)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # File-content hash for change detection (we re-thumbnail when this differs)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Where the cached thumbnail lives (relative to settings.thumbnail_cache_dir)
    thumb_filename: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Display order (0 = primary)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Last time we successfully read this file (None if the path is currently broken)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template: Mapped[Template] = relationship(back_populates="photos")

    __table_args__ = (
        Index("ix_template_photos_template_order", "template_id", "sort_order"),
    )


# ---------------------------------------------------------------------------
# Posts - history of actual postings
# ---------------------------------------------------------------------------


class PostStatus(str, enum.Enum):
    """Outcome of a posting attempt to a single platform."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    MANUAL = "manual"  # Facebook copy-paste package generated, not auto-posted
    REMOVED = "removed"  # Listing was active but we (or the platform) removed it


class Post(Base):
    """A single template-to-platform posting attempt.

    One ``Post`` row per (template, platform) attempt. The whole-button
    "Post Listing" action creates N rows (one per enabled platform).
    """

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False), nullable=False, index=True
    )

    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False), nullable=False, default=PostStatus.PENDING
    )

    # Pricing actually used (may differ from template's base_price + override)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # The platform's identifier for the resulting listing, if any.
    # We need this to update inventory later (e.g. set quantity to 0 after a sale).
    external_listing_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    external_listing_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Error message (if status == FAILED)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template: Mapped[Template] = relationship(back_populates="posts")

    __table_args__ = (
        Index("ix_posts_external", "platform", "external_listing_id"),
    )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class Tag(Base):
    """A user-defined tag that can be applied to templates.

    Tags are global (not per-template). The mockup shows tagging photos during
    the picker workflow; those tags get applied to the parent template.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    templates: Mapped[list[Template]] = relationship(
        secondary="template_tags",
        back_populates="tags",
    )


class TemplateTag(Base):
    """Join table between templates and tags."""

    __tablename__ = "template_tags"

    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Folder history - powers the "pinned" / "recent" lists in the photo picker
# ---------------------------------------------------------------------------


class FolderHistory(Base):
    """Tracks NAS folders Dad has visited or pinned in the photo picker.

    Keeps the cryptic folder name problem manageable - he pins KLU-VTG-NIC-2023
    once with a friendly alias and we surface it in the sidebar after that.
    """

    __tablename__ = "folder_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The folder path (normalized to forward slashes for cross-platform)
    path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True, index=True)

    # Optional friendly name override (Dad can rename "KLU-VTG-NIC-2023" to "Kluson nickel")
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True)

    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_visited_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Inventory sync - the Squarespace-specific bookkeeping
# ---------------------------------------------------------------------------


class InventorySyncLog(Base):
    """One row per inventory update we attempt.

    Triggered when a sale is detected on any platform - we update the others
    to match. Logged for debugging because cross-platform sync is the kind of
    thing that fails in subtle ways (rate limits, stale prices, etc.).
    """

    __tablename__ = "inventory_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The sale that triggered this sync
    triggering_platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False), nullable=False
    )
    triggering_listing_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # The post being updated
    target_post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    old_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    new_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False), nullable=False, default=PostStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebhookSubscription(Base):
    """Tracks webhook subscriptions registered with a platform.

    Currently unused (we're starting with polling for Squarespace order events)
    but reserved for when we want to upgrade to push notifications.
    """

    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, native_enum=False), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_subscription_id: Mapped[str] = mapped_column(String(120), nullable=False)
    target_url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("platform", "external_subscription_id", name="uq_webhook_platform_extid"),
    )


# ---------------------------------------------------------------------------
# Polling cursor - track where we left off in Squarespace order polling
# ---------------------------------------------------------------------------


class PollingCursor(Base):
    """Remembers the last-seen order timestamp per platform.

    Each time we poll Squarespace for new orders, we ask "anything since
    last_seen_at". After processing we advance the cursor. Survives restarts.
    """

    __tablename__ = "polling_cursors"

    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False), primary_key=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Preferences - user-tweakable settings stored in the DB
# ---------------------------------------------------------------------------


class Preference(Base):
    """Key-value store for user preferences set via the UI.

    Values from ``settings`` in ``config.py`` are the defaults; entries here
    override them. Stored as TEXT and parsed at read time based on the key.

    Why a generic K/V table rather than a wide row with named columns: keeps
    schema migrations simple as we add more preferences over time. We never
    have many preferences, so the lookup cost is irrelevant.
    """

    __tablename__ = "preferences"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

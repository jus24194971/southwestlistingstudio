"""Pydantic schemas used by the FastAPI layer.

These are separate from the SQLAlchemy ORM models because:
- We don't want the UI to see every internal field
- They're easier to evolve independently
- Pydantic gives us free JSON serialization with validation
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from listing_studio.core.models import Platform, PostStatus


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryOut(BaseModel):
    """A category as exposed to the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str

    # Reverb mapping
    reverb_category_uuid: str | None
    reverb_category_full_name: str | None
    reverb_subcategory_uuids: list[str] = Field(default_factory=list)
    reverb_subcategory_names: list[str] = Field(default_factory=list)

    # eBay mapping
    ebay_category_id: int | None = None
    ebay_category_name: str | None = None
    ebay_category_path: str | None = None
    ebay_leaf: bool = True

    # Squarespace mapping (store page, not a strict taxonomy)
    squarespace_store_page_id: str | None = None
    squarespace_store_page_name: str | None = None

    platform_config: dict = Field(default_factory=dict)
    default_condition: str | None
    default_weight_oz: float | None
    default_shipping_method: str | None
    template_count: int = 0  # populated by the API layer
    created_at: datetime
    updated_at: datetime


class CategoryCreate(BaseModel):
    """Body for creating a new category."""

    name: str

    # Reverb
    reverb_category_uuid: str | None = None
    reverb_category_full_name: str | None = None
    reverb_subcategory_uuids: list[str] = Field(default_factory=list)
    reverb_subcategory_names: list[str] = Field(default_factory=list)

    # eBay
    ebay_category_id: int | None = None
    ebay_category_name: str | None = None
    ebay_category_path: str | None = None
    ebay_leaf: bool = True

    # Squarespace
    squarespace_store_page_id: str | None = None
    squarespace_store_page_name: str | None = None

    default_condition: str | None = None
    default_weight_oz: float | None = None
    default_shipping_method: str | None = None


class CategoryUpdate(BaseModel):
    """Body for updating an existing category. All fields optional."""

    name: str | None = None

    reverb_category_uuid: str | None = None
    reverb_category_full_name: str | None = None
    reverb_subcategory_uuids: list[str] | None = None
    reverb_subcategory_names: list[str] | None = None

    ebay_category_id: int | None = None
    ebay_category_name: str | None = None
    ebay_category_path: str | None = None
    ebay_leaf: bool | None = None

    squarespace_store_page_id: str | None = None
    squarespace_store_page_name: str | None = None

    default_condition: str | None = None
    default_weight_oz: float | None = None
    default_shipping_method: str | None = None


class ReverbTaxonomyMatch(BaseModel):
    """One match from the Reverb taxonomy search."""

    uuid: str
    name: str
    full_name: str
    parent_uuid: str | None = None


class EbayTaxonomyMatch(BaseModel):
    """One match from the eBay taxonomy search."""

    category_id: int
    name: str
    full_name: str        # The breadcrumb path
    is_leaf: bool         # eBay only allows listings on leaves


class SquarespaceStorePage(BaseModel):
    """One Squarespace store page (the Squarespace equivalent of a category)."""

    id: str
    name: str


# Cross-platform category suggestion structures


class CategorySuggestion(BaseModel):
    """A single suggested mapping on a target platform.

    Returned from /api/categories/suggestions. Multiple suggestions may be
    returned for one query; UI shows them ranked by confidence.
    """

    platform: str         # "reverb" | "ebay" | "squarespace"
    external_id: str
    display_name: str
    display_path: str | None = None
    confidence: float     # 0.0-1.0
    source: str           # "shipped" | "learned" | "fuzzy"


class CategoryUsageEntry(BaseModel):
    """A recently-used category, for the "Recent" section of pickers."""

    platform: str
    external_id: str
    display_name: str
    display_path: str | None = None
    last_used_at: datetime
    use_count: int


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class PlatformOverride(BaseModel):
    """Per-platform field overrides stored on a template.

    Any subset of fields may be present. Missing = use the template's canonical value.
    """

    price_cents: int | None = None
    title: str | None = None
    description: str | None = None

    # Platform-specific extras (eBay category, Etsy section, etc.)
    extras: dict[str, str | int | bool] = Field(default_factory=dict)


class TemplatePhotoOut(BaseModel):
    """A photo as exposed to the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_path: str
    thumb_filename: str | None
    sort_order: int
    last_seen_at: datetime | None


class TemplateOut(BaseModel):
    """Full template detail returned to the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    description: str
    brand: str | None
    model: str | None = None
    year: str | None = None
    finish: str | None = None
    reverb_category: str | None = None
    reverb_subcategories: str | None = None
    condition: str
    base_price_cents: int
    quantity: int
    weight_oz: float
    folder: str
    category_id: int | None = None
    is_starred: bool
    platform_overrides: dict[str, PlatformOverride]
    default_platforms: list[Platform]
    shipping_method: str
    shipping_cost_cents: int
    reverb_shipping_type: str | None = None
    reverb_shipping_flat_cents: int = 0
    ebay_shipping_type: str | None = None
    ebay_shipping_override_cents: int = 0
    created_at: datetime
    updated_at: datetime
    last_posted_at: datetime | None
    post_count: int
    photos: list[TemplatePhotoOut] = Field(default_factory=list)


class TemplateSummary(BaseModel):
    """Compact template info for the library sidebar list.

    Lighter than ``TemplateOut`` so we can render a 200-row sidebar quickly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    folder: str
    category_id: int | None = None
    is_starred: bool
    last_posted_at: datetime | None
    post_count: int


class TemplateCreate(BaseModel):
    """Body for creating a new template from the UI."""

    name: str
    title: str
    description: str = ""
    brand: str | None = None
    model: str | None = None
    year: str | None = None
    finish: str | None = None
    reverb_category: str | None = None
    reverb_subcategories: str | None = None
    condition: str = "new_old_stock"
    base_price_cents: int = 0
    quantity: int = 1
    weight_oz: float = 0.0
    folder: str = "Uncategorized"
    category_id: int | None = None
    default_platforms: list[Platform] = Field(default_factory=list)
    shipping_method: str = "usps_first_class"
    shipping_cost_cents: int = 0
    reverb_shipping_type: str | None = None
    reverb_shipping_flat_cents: int = 0
    ebay_shipping_type: str | None = None
    ebay_shipping_override_cents: int = 0


class TemplateUpdate(BaseModel):
    """Body for updating an existing template. All fields optional - we patch."""

    name: str | None = None
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    year: str | None = None
    finish: str | None = None
    reverb_category: str | None = None
    reverb_subcategories: str | None = None
    condition: str | None = None
    base_price_cents: int | None = None
    quantity: int | None = None
    weight_oz: float | None = None
    folder: str | None = None
    category_id: int | None = None
    is_starred: bool | None = None
    platform_overrides: dict[str, PlatformOverride] | None = None
    default_platforms: list[Platform] | None = None
    shipping_method: str | None = None
    shipping_cost_cents: int | None = None
    reverb_shipping_type: str | None = None
    reverb_shipping_flat_cents: int | None = None
    ebay_shipping_type: str | None = None
    ebay_shipping_override_cents: int | None = None


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


class PostRequest(BaseModel):
    """Body for the 'Post Listing' button.

    Lists which platforms to post to and optional per-platform overrides
    captured in the form (which may differ from the saved template).
    """

    template_id: int
    platforms: list[Platform]
    overrides: dict[Platform, PlatformOverride] = Field(default_factory=dict)


class PostResult(BaseModel):
    """The result of posting a single template to a single platform."""

    platform: Platform
    status: PostStatus
    price_cents: int
    external_listing_id: str | None = None
    external_listing_url: str | None = None
    error_message: str | None = None
    elapsed_ms: int


class PostResponse(BaseModel):
    """Aggregate response for a full 'Post Listing' action."""

    template_id: int
    results: list[PostResult]
    total_elapsed_ms: int
    facebook_package: "FacebookPackage | None" = None


# ---------------------------------------------------------------------------
# Facebook copy-paste package
# ---------------------------------------------------------------------------


class FacebookPackage(BaseModel):
    """The handoff payload for the manual Facebook Marketplace step."""

    title: str
    price_cents: int
    description: str
    photo_paths: list[str]  # Resized copies in the fb_temp folder
    photo_temp_dir: str  # The folder Dad can open in Explorer


# Resolve the forward reference
PostResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Settings (platform connection status, preferences)
# ---------------------------------------------------------------------------


class PlatformConnectionStatus(BaseModel):
    """Status of a single platform's connection (shown on the settings screen)."""

    platform: Platform
    is_connected: bool
    account_label: str | None = None  # E.g. "southwest-acoustics" for Reverb
    token_expires_at: datetime | None = None
    last_used_at: datetime | None = None
    error: str | None = None


class AppPreferences(BaseModel):
    """User-tweakable preferences from the settings screen."""

    post_parallel: bool = True
    post_best_effort: bool = True
    stale_price_warning_days: int = 90
    auto_copy_fb_description: bool = True
    photo_background_removal: bool = False
    default_platforms: list[Platform] = Field(default_factory=list)
    reverb_listing_tail: str = ""

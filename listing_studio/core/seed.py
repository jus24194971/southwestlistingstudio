"""Sample data for first-run.

Inserts a handful of realistic templates so the UI library sidebar isn't empty
when Dad first opens the app. Idempotent: skips if there are already any
templates in the DB.
"""

from __future__ import annotations

from listing_studio.core.db import session_scope
from listing_studio.core.models import Platform, Template


_SAMPLE_TEMPLATES = [
    {
        "name": "Kluson Vintage, Nickel",
        "title": "Kluson Vintage-style Tuners, Nickel - Set of 6 (3+3), New Old Stock",
        "description": (
            "Set of 6 Kluson-style vintage tuners in nickel finish. Configured for 3-per-side "
            "headstock layout (Les Paul, SG, ES-series). Direct drop-in replacement for "
            "traditional vintage tuners. Quality reproduction parts, never installed.\n\n"
            "Specifications:\n"
            "- 15:1 gear ratio for smooth, accurate tuning\n"
            "- 6mm peg hole compatible\n"
            "- Includes mounting screws and bushings\n"
            "- Total weight: 4.2 oz\n\n"
            "Ships next business day from Tucson, Arizona.\n\n"
            "From Southwest Acoustics - your trusted source for guitar parts and accessories."
        ),
        "brand": "Kluson",
        "condition": "new_old_stock",
        "base_price_cents": 8900,
        "quantity": 1,
        "weight_oz": 4.2,
        "folder": "Tuners",
        "is_starred": True,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.ETSY, Platform.SQUARESPACE],
        "platform_overrides": {
            "reverb": {"price_cents": 9400},
            "ebay": {"price_cents": 9500},
            "etsy": {"price_cents": 9200},
            "squarespace": {"price_cents": 8500},
            "facebook": {"price_cents": 8500},
        },
        "shipping_method": "usps_first_class",
        "shipping_cost_cents": 0,
    },
    {
        "name": "Kluson Vintage, Gold",
        "title": "Kluson Vintage-style Tuners, Gold - Set of 6 (3+3)",
        "description": "Set of 6 Kluson-style vintage tuners in gold finish.",
        "brand": "Kluson",
        "condition": "new_old_stock",
        "base_price_cents": 9900,
        "quantity": 1,
        "weight_oz": 4.2,
        "folder": "Tuners",
        "is_starred": True,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_first_class",
    },
    {
        "name": "Grover 102G Rotomatic",
        "title": "Grover 102G Rotomatic Tuners, Gold - Set of 6",
        "description": "Grover Rotomatic tuners in gold finish.",
        "brand": "Grover",
        "condition": "new",
        "base_price_cents": 12500,
        "quantity": 1,
        "weight_oz": 5.0,
        "folder": "Tuners",
        "is_starred": False,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_first_class",
    },
    {
        "name": "Schaller M6 Mini, Chrome",
        "title": "Schaller M6 Mini Tuners, Chrome - Set of 6",
        "description": "Schaller M6 Mini in chrome finish.",
        "brand": "Schaller",
        "condition": "new",
        "base_price_cents": 14500,
        "quantity": 1,
        "weight_oz": 4.8,
        "folder": "Tuners",
        "is_starred": False,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_first_class",
    },
    {
        "name": "Alnico V Humbucker, Bridge",
        "title": "Alnico V Humbucker Pickup, Bridge Position - Vintage Voice",
        "description": "Vintage-voiced Alnico V humbucker for the bridge position.",
        "brand": "Generic",
        "condition": "new",
        "base_price_cents": 4500,
        "quantity": 1,
        "weight_oz": 6.0,
        "folder": "Pickups",
        "is_starred": True,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.ETSY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_first_class",
    },
    {
        "name": "PAF-style Set, Aged Nickel",
        "title": "PAF-style Humbucker Set, Aged Nickel Covers",
        "description": "Pair of PAF-style humbuckers with aged nickel covers.",
        "brand": "Generic",
        "condition": "new",
        "base_price_cents": 14000,
        "quantity": 1,
        "weight_oz": 12.0,
        "folder": "Pickups",
        "is_starred": False,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_priority",
    },
    {
        "name": "Single-Coil, Strat-style",
        "title": "Single-Coil Pickup, Strat-style - Vintage Output",
        "description": "Vintage-output single-coil pickup, Strat-style.",
        "brand": "Generic",
        "condition": "new",
        "base_price_cents": 3500,
        "quantity": 1,
        "weight_oz": 3.0,
        "folder": "Pickups",
        "is_starred": False,
        "default_platforms": [Platform.REVERB, Platform.EBAY, Platform.SQUARESPACE],
        "platform_overrides": {},
        "shipping_method": "usps_first_class",
    },
]


def seed_sample_data_if_empty() -> bool:
    """Insert sample templates if none exist. Returns True if anything was inserted."""
    with session_scope() as session:
        existing_count = session.query(Template).count()
        if existing_count > 0:
            return False

        for item in _SAMPLE_TEMPLATES:
            # Convert Platform enums to strings for JSON storage
            default_platforms_str = [p.value for p in item["default_platforms"]]
            tmpl = Template(
                name=item["name"],
                title=item["title"],
                description=item["description"],
                brand=item["brand"],
                condition=item["condition"],
                base_price_cents=item["base_price_cents"],
                quantity=item["quantity"],
                weight_oz=item["weight_oz"],
                folder=item["folder"],
                is_starred=item["is_starred"],
                default_platforms=default_platforms_str,
                platform_overrides=item["platform_overrides"],
                shipping_method=item["shipping_method"],
                shipping_cost_cents=item.get("shipping_cost_cents", 0),
            )
            session.add(tmpl)
        return True

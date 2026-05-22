"""Preferences read/write.

User-tweakable settings stored in the database (so they survive restarts and
aren't lost when the app updates). Read calls fall back to defaults from
``config.settings`` when no DB override exists.

The set of valid preferences is fixed (defined in ``_PREFERENCE_SPECS``)
because letting the UI write arbitrary keys would be a security and
maintenance hazard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from listing_studio.config import settings
from listing_studio.core.models import Platform, Preference


@dataclass(frozen=True)
class PreferenceSpec:
    """Describes one preference: its type, default, and parser."""

    key: str
    value_type: str  # "bool" | "int" | "list[str]"
    default: Any  # Either a fixed value or callable returning the default

    def coerce(self, raw_value: str) -> Any:
        """Parse a string from the DB back into the typed Python value."""
        if self.value_type == "bool":
            return raw_value.lower() in ("true", "1", "yes")
        if self.value_type == "int":
            try:
                return int(raw_value)
            except ValueError:
                return self._resolve_default()
        if self.value_type == "list[str]":
            try:
                return json.loads(raw_value)
            except json.JSONDecodeError:
                return self._resolve_default()
        return raw_value

    def serialize(self, value: Any) -> str:
        """Convert a typed value to a string for DB storage."""
        if self.value_type == "bool":
            return "true" if value else "false"
        if self.value_type == "int":
            return str(int(value))
        if self.value_type == "list[str]":
            return json.dumps(list(value))
        return str(value)

    def _resolve_default(self) -> Any:
        return self.default() if callable(self.default) else self.default


# All known preferences. Adding a new one means adding an entry here plus
# updating the AppPreferences schema in core/schemas.py.
_PREFERENCE_SPECS: dict[str, PreferenceSpec] = {
    "post_parallel": PreferenceSpec("post_parallel", "bool",
                                    lambda: settings.post_parallel),
    "post_best_effort": PreferenceSpec("post_best_effort", "bool",
                                       lambda: settings.post_best_effort),
    "stale_price_warning_days": PreferenceSpec("stale_price_warning_days", "int",
                                               lambda: settings.stale_price_warning_days),
    "auto_copy_fb_description": PreferenceSpec("auto_copy_fb_description", "bool", True),
    "photo_background_removal": PreferenceSpec("photo_background_removal", "bool", False),
    "default_platforms": PreferenceSpec("default_platforms", "list[str]",
                                        lambda: [Platform.REVERB.value, Platform.EBAY.value,
                                                Platform.SQUARESPACE.value]),
}


def get_preference(session: Session, key: str) -> Any:
    """Get a single preference value (DB if present, default otherwise)."""
    spec = _PREFERENCE_SPECS.get(key)
    if spec is None:
        raise KeyError(f"Unknown preference: {key}")

    pref = session.get(Preference, key)
    if pref is None:
        return spec._resolve_default()
    return spec.coerce(pref.value)


def get_all_preferences(session: Session) -> dict[str, Any]:
    """Get all preferences as a dict.

    Includes defaults for any preferences not yet in the DB.
    """
    out: dict[str, Any] = {}
    stmt = select(Preference)
    db_prefs = {p.key: p.value for p in session.execute(stmt).scalars()}

    for key, spec in _PREFERENCE_SPECS.items():
        if key in db_prefs:
            out[key] = spec.coerce(db_prefs[key])
        else:
            out[key] = spec._resolve_default()

    return out


def set_preference(session: Session, key: str, value: Any) -> None:
    """Set a single preference. Creates or updates the row."""
    spec = _PREFERENCE_SPECS.get(key)
    if spec is None:
        raise KeyError(f"Unknown preference: {key}")

    serialized = spec.serialize(value)
    pref = session.get(Preference, key)
    if pref is None:
        pref = Preference(key=key, value=serialized)
        session.add(pref)
    else:
        pref.value = serialized


def set_preferences(session: Session, values: dict[str, Any]) -> None:
    """Bulk-set preferences from a dict. Unknown keys are ignored."""
    for key, value in values.items():
        if key in _PREFERENCE_SPECS:
            set_preference(session, key, value)

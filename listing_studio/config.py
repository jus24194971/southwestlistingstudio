"""Application configuration.

Centralizes filesystem paths, default values, and environment-overridable settings.
Anything else in the code should import from here rather than hard-coding values.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Where the SQLite DB, thumbnail cache, and logs live.

    Uses the standard per-OS app-data location:
    - Windows: %LOCALAPPDATA%\\ListingStudio
    - macOS:   ~/Library/Application Support/ListingStudio
    - Linux:   ~/.local/share/listing-studio
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "ListingStudio"
    elif os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
        return Path.home() / "Library" / "Application Support" / "ListingStudio"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "listing-studio"


class Settings(BaseSettings):
    """Application settings.

    Values can be overridden via:
    1. Environment variables prefixed with ``LISTING_STUDIO_`` (e.g. ``LISTING_STUDIO_API_PORT``)
    2. A ``.env`` file in the working directory
    """

    model_config = SettingsConfigDict(
        env_prefix="LISTING_STUDIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Window
    window_title: str = "Listing Studio - Southwest Acoustics"
    window_width: int = 1280
    window_height: int = 820
    window_min_width: int = 1000
    window_min_height: int = 700

    # Embedded API server
    api_host: str = "127.0.0.1"
    api_port: int = 8731  # Arbitrary high port unlikely to conflict

    # Data paths
    data_dir: Path = Field(default_factory=_default_data_dir)

    # Defaults
    stale_price_warning_days: int = 90
    post_parallel: bool = True
    post_best_effort: bool = True

    # Squarespace order polling. Dad's storefront is the source of truth for
    # inventory sync; we poll it for new orders and decrement quantities on
    # the marketplaces. 5-10 min is the sweet spot between freshness and
    # API quota - real-time webhooks would need a public URL we don't have.
    squarespace_poll_enabled: bool = True
    squarespace_poll_interval_seconds: int = 300  # 5 minutes
    squarespace_poll_max_consecutive_failures: int = 5  # Back off after this many

    # Facebook package
    fb_max_image_size: int = 2048  # FB recommends max 2048 on the long edge
    fb_max_images: int = 10

    # Keyring service name used for OAuth tokens
    keyring_service: str = "listing-studio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "listing_studio.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def thumbnail_cache_dir(self) -> Path:
        return self.data_dir / "thumbnail_cache"

    @property
    def fb_temp_dir(self) -> Path:
        return self.data_dir / "fb_temp"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        """Create all required directories on disk. Safe to call repeatedly."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_cache_dir.mkdir(parents=True, exist_ok=True)
        self.fb_temp_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


# Module-level singleton. Other modules do `from listing_studio.config import settings`.
settings = Settings()

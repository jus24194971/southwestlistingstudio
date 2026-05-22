"""Stdout/stderr handling for windowed PyInstaller builds.

In a windowed Windows .exe (PyInstaller spec ``console=False``), Python's
sys.stdout and sys.stderr are NOT connected to anything useful. Writes can
hang or crash the app. This breaks uvicorn, FastAPI, our own logging - any
module that prints anywhere during startup will silently kill the process.

The fix is to redirect both streams to a log file at startup, before any
other module gets a chance to import them. This module does that.

Behavior:

* Running from source (no ``sys.frozen``): does nothing. Dev gets normal
  terminal output.
* Running as a bundled .exe with console=False: redirects stdout and stderr
  to ``{data_dir}/logs/runtime.log``, with auto-rotation when the file gets
  large.
* Running as a bundled .exe with console=True (current state): the redirect
  is harmless - we just write to the file in addition to whatever console
  output happens. So this code is safe to run unconditionally in bundled
  builds.

We want to keep ``console=False`` going forward (cleaner user experience,
no flashing terminal window) once we know stdout is redirected.

Order matters: this module's ``setup`` must be called BEFORE importing
uvicorn, fastapi, the listing_studio.app module, or anything that emits log
output during import.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_bundled() -> bool:
    """True if we're running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_log_path() -> Path:
    """Compute where the runtime log lives.

    Can't import listing_studio.config here because that triggers pydantic-settings
    which might write to stdout during import. We re-derive the data_dir path
    using the same logic.
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data_dir = base / "ListingStudio"
    elif sys.platform == "darwin":
        data_dir = Path.home() / "Library" / "Application Support" / "ListingStudio"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        data_dir = base / "listing-studio"

    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "runtime.log"


def setup() -> Path | None:
    """If running bundled, redirect stdout and stderr to a log file.

    Returns the path the log was redirected to (for the running session to
    surface in the UI later if useful), or None if no redirect was done.

    The redirect is one-way - we don't preserve the original stdout/stderr.
    The .exe doesn't have anything to print to anyway when console=False.

    Rotation: if the existing log is over 5 MB, rename it to runtime.log.old
    (overwriting any previous .old) and start fresh. Simple two-file rotation
    keeps us from filling Dad's disk while preserving the last big chunk
    for debugging.
    """
    if not is_bundled():
        return None

    try:
        log_path = get_log_path()

        # Rotate if too large
        if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
            old_path = log_path.with_suffix(".log.old")
            try:
                if old_path.exists():
                    old_path.unlink()
                log_path.rename(old_path)
            except OSError:
                # Can't rotate? Best effort - we'll just append.
                pass

        # Open the log file in append+unbuffered text mode and assign to
        # both stdout and stderr. line_buffering=True flushes on every newline,
        # which we want for log usefulness.
        log_file = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)

        # Write a session-start marker so we can tell where each run begins
        import datetime
        log_file.write(f"\n========== Listing Studio start: {datetime.datetime.now().isoformat()} ==========\n")
        log_file.flush()

        sys.stdout = log_file
        sys.stderr = log_file

        return log_path
    except Exception:
        # If we can't redirect, fall back to silently doing nothing.
        # The app may still hang due to the original problem, but at least
        # this module didn't make it worse.
        return None

"""Auto-update mechanism.

Checks GitHub Releases for a newer version of the app, downloads the new
build, extracts it alongside the current one, and arranges for the app to
restart on the new version.

Architecture rationale:

* We use GitHub Releases as the distribution channel - free, versioned,
  and we're already on GitHub. The release tag drives the version number
  (e.g. tag "v0.2.1" -> version "0.2.1").

* We install each version into its own folder under data_dir/versions/<tag>/.
  A "current" pointer (a small text file) tells the launcher which one to
  run. This makes rollback trivial - just edit current.txt back.

* We never overwrite the currently-running executable. Windows file locks
  on running .exe files would make that impossible anyway. Instead we
  extract the new version while the old one keeps running, then trigger
  a restart that launches the new version.

* All update I/O happens in the UI process (not the FastAPI thread), to
  keep the UI responsive and let it surface progress.

* The check itself is rate-limited to once per launch + once per 6 hours
  for long-running sessions. GitHub's anonymous API allows 60 reqs/hour
  per IP which is plenty, but we don't need to be aggressive.

Where this code runs:

* When packaged as an .exe: this is the production path. The "app directory"
  is something like %LOCALAPPDATA%/ListingStudio/versions/v0.2.0/, and we
  extract new versions as siblings.

* When run from source (python -m listing_studio): the updater detects this
  and disables itself - we don't want a dev install to overwrite itself.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from listing_studio import __version__
from listing_studio.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# GitHub repo where releases are published. Set to None to disable updates.
# When you create the repo, update this to "yourname/listing-studio" or similar.
GITHUB_REPO: str | None = "jus24194971/southwestlistingstudio"

# How long to cache "no update available" before re-checking (during a long session)
RECHECK_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours

# How long to wait for GitHub API to respond
GITHUB_API_TIMEOUT_SECONDS = 10.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseInfo:
    """A GitHub release that's newer than the current version."""

    tag_name: str            # e.g. "v0.2.1"
    version: str             # e.g. "0.2.1" (tag with leading 'v' stripped)
    name: str                # Human-readable release name
    body: str                # Release notes (markdown)
    published_at: str        # ISO timestamp
    download_url: str        # Direct URL to the .zip asset
    download_size: int       # Size in bytes


# ---------------------------------------------------------------------------
# Detection: is this an installed build, or a dev run?
# ---------------------------------------------------------------------------


def is_packaged_build() -> bool:
    """Return True when running from a PyInstaller bundle.

    PyInstaller sets sys.frozen at runtime. When we're running from source
    via `python -m listing_studio`, this is False and we should skip all
    update behavior - we don't want a dev environment to update itself.
    """
    return getattr(sys, "frozen", False)


def get_install_root() -> Path | None:
    """Return the path of the currently-running install directory.

    Layout when packaged:
        <data_dir>/versions/<tag>/ListingStudio/      <- this dir
            ListingStudio.exe                          <- sys.executable
            _internal/                                 <- bundled deps

    Returns None if running from source (dev mode).
    """
    if not is_packaged_build():
        return None
    # sys.executable is the path to ListingStudio.exe; .parent is the install dir
    return Path(sys.executable).resolve().parent


def get_versions_root() -> Path:
    """Return the directory that holds all installed versions.

    Layout: <data_dir>/versions/<tag>/ListingStudio/
                                     ^^^^^^^^^^^^^^ install root
                       ^^^^^^^^^^^^^^^ this function's parent
            ^^^^^^^^^^^^ this function returns this
    """
    return settings.data_dir / "versions"


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _parse_version(s: str) -> tuple[int, ...]:
    """Parse '0.2.1' or 'v0.2.1' into (0, 2, 1) for comparison.

    Ignores anything after a hyphen (so 'v0.2.1-beta' becomes (0, 2, 1)).
    Returns (0, 0, 0) on parse failure - which compares as "ancient" so we
    don't auto-update from a malformed version string.
    """
    s = s.strip().lstrip("v").split("-", 1)[0]
    try:
        return tuple(int(p) for p in s.split("."))
    except ValueError:
        return (0, 0, 0)


def is_newer(remote_version: str, local_version: str) -> bool:
    """Return True if remote_version > local_version."""
    return _parse_version(remote_version) > _parse_version(local_version)


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------


def fetch_latest_release() -> ReleaseInfo | None:
    """Hit GitHub's API for the latest release. Returns None if no update.

    We treat any of these as "no update available" without crashing:
    - GITHUB_REPO is None (updates disabled)
    - Network error / timeout
    - No releases yet
    - Latest release is same or older than our version
    - Release exists but has no .zip asset (build incomplete)

    Any unexpected case just logs and returns None. Failing the update
    check should never break the app.
    """
    if GITHUB_REPO is None:
        return None

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

    try:
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ListingStudio-Updater",
        })
        with urllib.request.urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.info("Update check failed (will retry later): %s", exc)
        return None

    tag = payload.get("tag_name", "")
    if not tag:
        return None

    remote_version = tag.lstrip("v")
    if not is_newer(remote_version, __version__):
        return None

    # Find the Windows .zip asset. We expect the build action to upload one
    # named like "ListingStudio-v0.2.1-windows.zip".
    download_url = None
    download_size = 0
    for asset in payload.get("assets", []):
        name = asset.get("name", "")
        if name.endswith("-windows.zip"):
            download_url = asset.get("browser_download_url")
            download_size = asset.get("size", 0)
            break

    if not download_url:
        logger.warning("Release %s has no Windows zip asset; skipping update", tag)
        return None

    return ReleaseInfo(
        tag_name=tag,
        version=remote_version,
        name=payload.get("name") or tag,
        body=payload.get("body") or "",
        published_at=payload.get("published_at", ""),
        download_url=download_url,
        download_size=download_size,
    )


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def download_and_extract(
    release: ReleaseInfo,
    progress_callback=None,
) -> Path:
    """Download the release zip and extract to versions/<tag>/.

    Args:
        release: The release to install.
        progress_callback: Optional callable taking (bytes_done, bytes_total).
            Called periodically during download for UI progress bars.

    Returns:
        Path to the extracted install root (the folder containing the .exe).

    Raises:
        Exception on any failure. Caller should catch and surface to user.
    """
    versions_root = get_versions_root()
    versions_root.mkdir(parents=True, exist_ok=True)

    target_dir = versions_root / release.tag_name

    # If the target dir already exists from a previous failed attempt, clear it
    if target_dir.exists():
        logger.info("Removing previous incomplete install at %s", target_dir)
        shutil.rmtree(target_dir, ignore_errors=True)

    # Download to a temp file so partial downloads can't be mistaken for installs
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        logger.info("Downloading %s to %s", release.download_url, tmp_path)
        _download_with_progress(release.download_url, tmp_path,
                                release.download_size, progress_callback)

        logger.info("Extracting to %s", target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(target_dir)

        # Find the actual install root inside the extracted contents.
        # PyInstaller's COLLECT output is `dist/ListingStudio/`, so the zip
        # should contain a single top-level "ListingStudio" folder.
        candidates = [p for p in target_dir.iterdir() if p.is_dir()]
        if len(candidates) == 1:
            install_root = candidates[0]
        else:
            install_root = target_dir

        # Sanity check
        exe_name = "ListingStudio.exe" if os.name == "nt" else "ListingStudio"
        if not (install_root / exe_name).exists():
            raise FileNotFoundError(
                f"Extracted update is missing {exe_name} at {install_root}"
            )

        return install_root

    finally:
        # Always remove the temp zip
        tmp_path.unlink(missing_ok=True)


def _download_with_progress(url: str, dest: Path, expected_size: int,
                            progress_callback=None) -> None:
    """Stream a download to disk, calling progress_callback periodically."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "ListingStudio-Updater",
    })

    with urllib.request.urlopen(request, timeout=30) as response:
        bytes_done = 0
        chunk_size = 64 * 1024  # 64 KB chunks
        last_progress_update = 0.0

        with open(dest, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_done += len(chunk)

                # Throttle progress updates to once every 100ms to avoid UI spam
                now = time.monotonic()
                if progress_callback and (now - last_progress_update) > 0.1:
                    progress_callback(bytes_done, expected_size)
                    last_progress_update = now

        # Final progress notification at 100%
        if progress_callback:
            progress_callback(bytes_done, expected_size)


def set_current_version(install_root: Path) -> None:
    """Record this install as the 'current' version.

    Writes a pointer file at <data_dir>/current.txt containing the path
    to the active install. The launcher / restart logic reads this to know
    which version to start.
    """
    pointer_path = settings.data_dir / "current.txt"
    pointer_path.write_text(str(install_root), encoding="utf-8")
    logger.info("Set current install to %s", install_root)


def read_current_version() -> Path | None:
    """Return the path of the current install, or None if not set."""
    pointer_path = settings.data_dir / "current.txt"
    if not pointer_path.exists():
        return None
    try:
        return Path(pointer_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Restart logic
# ---------------------------------------------------------------------------


def restart_into(install_root: Path) -> None:
    """Spawn the new version and exit this process.

    The new process is detached - we don't want it tied to our process group
    or it'd die when we exit. After spawning, we exit immediately so the
    window closes and the new version's window opens.

    On Windows we use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS.
    On Mac/Linux we use os.spawn with the no-wait flag.
    """
    exe_name = "ListingStudio.exe" if os.name == "nt" else "ListingStudio"
    exe_path = install_root / exe_name

    if not exe_path.exists():
        raise FileNotFoundError(f"Updated exe not found: {exe_path}")

    logger.info("Restarting into %s", exe_path)

    if os.name == "nt":
        # Windows: detached process so it survives our exit
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(install_root),
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
    else:
        # macOS / Linux: fork+exec via subprocess, detached
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(install_root),
            start_new_session=True,
            close_fds=True,
        )

    # Give the new process a moment to start before we exit
    time.sleep(0.5)
    os._exit(0)


# ---------------------------------------------------------------------------
# High-level orchestration (this is what UI/API calls)
# ---------------------------------------------------------------------------


# Module-level cache so we don't hit GitHub on every UI render
_cached_release: ReleaseInfo | None = None
_last_check_at: float = 0.0
_check_lock = threading.Lock()


def check_for_update(force: bool = False) -> ReleaseInfo | None:
    """Return the latest release if newer than ours, else None.

    Thread-safe. Caches results for RECHECK_INTERVAL_SECONDS to avoid
    hammering GitHub. Pass force=True to ignore the cache.
    """
    global _cached_release, _last_check_at

    if not is_packaged_build():
        # Dev mode: skip updates
        return None

    with _check_lock:
        now = time.monotonic()
        if not force and (now - _last_check_at) < RECHECK_INTERVAL_SECONDS:
            return _cached_release

        _cached_release = fetch_latest_release()
        _last_check_at = now
        return _cached_release


def install_update(
    release: ReleaseInfo,
    progress_callback=None,
) -> Path:
    """Download, extract, and mark as current. Doesn't restart.

    Caller (typically the API) should call this, then return success, then
    schedule a restart shortly after so the response can reach the UI.

    Returns the install root of the new version.
    """
    install_root = download_and_extract(release, progress_callback)
    set_current_version(install_root)
    return install_root


def cleanup_old_versions(keep_count: int = 2) -> None:
    """Remove old version directories, keeping the most recent N.

    Called occasionally to reclaim disk space. We always keep the current
    version plus a few before it (in case the user wants to roll back).
    """
    versions_root = get_versions_root()
    if not versions_root.exists():
        return

    current = read_current_version()
    current_parent = current.parent if current else None

    # All version dirs, newest first by mtime
    version_dirs = sorted(
        [d for d in versions_root.iterdir() if d.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    # Always preserve the currently-running version
    to_delete: list[Path] = []
    for i, version_dir in enumerate(version_dirs):
        if version_dir == current_parent:
            continue
        if i >= keep_count:
            to_delete.append(version_dir)

    for version_dir in to_delete:
        logger.info("Removing old version: %s", version_dir)
        shutil.rmtree(version_dir, ignore_errors=True)

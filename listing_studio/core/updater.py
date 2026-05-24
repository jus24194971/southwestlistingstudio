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
    """Replace the running process with the new version.

    Race condition we have to handle: when we exit and spawn the new process,
    Windows holds our TCP socket in TIME_WAIT for some time after we die.
    The new process tries to bind the same port (8731) and fails. Result is
    "can't reach this page" in the new app even though the .exe launched.

    Fix: write a tiny launcher .bat that
      1. Waits 2 seconds (long enough for our socket to release)
      2. Starts the new exe

    Then we exit IMMEDIATELY (no sleep, no overlap). The launcher script
    holds the gap between processes. After spawning the launcher we use
    os._exit() to bypass any cleanup that could hold the port longer.
    """
    exe_name = "ListingStudio.exe" if os.name == "nt" else "ListingStudio"
    exe_path = install_root / exe_name

    if not exe_path.exists():
        raise FileNotFoundError(f"Updated exe not found: {exe_path}")

    logger.info("Restarting into %s", exe_path)

    if os.name == "nt":
        # Write a launcher .bat that waits for our process and port to clear,
        # then starts the new exe. We don't use Popen directly because we
        # need the new process to start AFTER we've fully died.
        launcher_path = settings.data_dir / "_relaunch.bat"
        launcher_content = (
            "@echo off\r\n"
            # Wait 3 seconds for the old process and TIME_WAIT to clear.
            # ping is the standard idiom for "wait N seconds" in batch.
            "ping 127.0.0.1 -n 4 > nul\r\n"
            # Launch new exe detached from this script
            f'start "" "{exe_path}"\r\n'
            # Delete this script after we're done (we don't litter %LOCALAPPDATA%)
            'del "%~f0"\r\n'
        )
        launcher_path.write_text(launcher_content, encoding="ascii")

        # Spawn the launcher detached so it survives our exit
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd.exe", "/c", str(launcher_path)],
            cwd=str(install_root),
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )
    else:
        # macOS / Linux: same idea but with a shell script
        launcher_path = settings.data_dir / "_relaunch.sh"
        launcher_content = (
            "#!/bin/sh\n"
            "sleep 3\n"
            f'"{exe_path}" &\n'
            f'rm -- "$0"\n'
        )
        launcher_path.write_text(launcher_content, encoding="ascii")
        launcher_path.chmod(0o755)
        subprocess.Popen(
            [str(launcher_path)],
            cwd=str(install_root),
            start_new_session=True,
            close_fds=True,
        )

    # Exit immediately - don't sleep, don't wait. The launcher takes it from here.
    # os._exit bypasses Python's normal shutdown hooks (atexit, daemon threads)
    # which could otherwise hold the socket open longer.
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
    # Rewrite any existing Windows .lnk shortcuts to point at the new install
    # location. Best-effort: failures don't block the update.
    try:
        updated = refresh_shortcuts(install_root)
        if updated:
            logger.info("Refreshed %d shortcut(s) to point at new install", updated)
    except Exception as exc:  # noqa: BLE001 - shortcut refresh must never break the update
        logger.warning("Shortcut refresh skipped: %s", exc)
    return install_root


# ---------------------------------------------------------------------------
# Shortcut refresh - keep desktop/Start Menu .lnk files current
# ---------------------------------------------------------------------------
#
# Each update installs to a new versioned directory under
# %LOCALAPPDATA%/ListingStudio/versions/<tag>/, but any desktop or Start
# Menu shortcut would still point at the OLD path until rewritten. After
# every install_update we scan the user's standard shortcut locations,
# identify any .lnk targeting a ListingStudio.exe, and rewrite it to
# target the new install. Side effect: Windows invalidates its icon
# cache for the modified .lnk, so a new app icon shows up immediately
# instead of needing a reboot.


def refresh_shortcuts(install_root: Path) -> int:
    """Rewrite Windows .lnk shortcuts that target ListingStudio.exe.

    Scans the user's Desktop (OneDrive-aware) and Start Menu Programs
    folders. For every .lnk whose target's basename is ``ListingStudio.exe``,
    updates its target, working directory, and icon to point at the new
    install. Returns the count of shortcuts updated.

    Best-effort: returns 0 (and logs) on any failure rather than raising,
    so a missing pywin32 or an exotic locale never breaks the update.
    """
    if os.name != "nt":
        return 0

    try:
        from win32com.client import Dispatch
    except ImportError:
        logger.info("pywin32 not available; skipping shortcut refresh")
        return 0

    exe_name = "ListingStudio.exe"
    exe_path = install_root / exe_name
    exe_path_str = str(exe_path)
    install_root_str = str(install_root)

    shell = Dispatch("WScript.Shell")

    # Candidate directories to scan. SpecialFolders handles OneDrive-redirected
    # Desktop transparently (returns the actual resolved path).
    candidates: list[Path] = []
    for folder_name in ("Desktop", "Programs", "AllUsersDesktop", "AllUsersPrograms"):
        try:
            value = shell.SpecialFolders(folder_name)
            if value:
                candidates.append(Path(str(value)))
        except Exception:  # noqa: BLE001 - some specials may not exist on all systems
            continue

    updated = 0
    for dir_path in candidates:
        if not dir_path.exists():
            continue
        for lnk in dir_path.rglob("*.lnk"):
            try:
                # CreateShortcut on an existing .lnk reads it; .Save() writes back.
                shortcut = shell.CreateShortcut(str(lnk))
                target = str(shortcut.TargetPath or "")
                if not target:
                    continue
                # Match by basename - this catches shortcuts at any path that
                # launch our exe, including the bootstrap install location and
                # any older versioned dirs from previous updates.
                if Path(target).name.lower() != exe_name.lower():
                    continue
                if target.lower() == exe_path_str.lower():
                    # Already pointing at the right place
                    continue
                shortcut.TargetPath = exe_path_str
                shortcut.WorkingDirectory = install_root_str
                shortcut.IconLocation = f"{exe_path_str},0"
                shortcut.Save()
                updated += 1
                logger.info("Refreshed shortcut: %s -> %s", lnk, exe_path_str)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Couldn't refresh shortcut %s: %s", lnk, exc)

    return updated


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

"""NAS photo browsing.

Reads images from a local filesystem path (typically a mapped network drive
like Z:\\, but works with any directory). Generates thumbnails on demand and
caches them locally for fast subsequent loads.

Security model: every path passed through this module must be either equal
to or a descendant of one of the configured NAS roots. We resolve symlinks
and check the resolved path's prefix against the roots. This prevents
crafted URLs from escaping the configured scope (e.g. ``?path=C:\\Windows``).

Thumbnail caching: thumbnails live in ``settings.thumbnail_cache_dir``, named
by a hash of (source path + mtime + size). When the source image changes,
the cache key changes, so we never serve a stale thumbnail.

Why a cache key includes mtime+size rather than content hash: hashing the
file content would mean reading every photo on every request, defeating the
point of caching. mtime+size is good enough - the only way to fool it would
be saving a different image with the exact same byte length at the exact
same millisecond, which doesn't happen in practice.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from listing_studio.config import settings

logger = logging.getLogger(__name__)


# Image extensions we recognize. Case-insensitive. Anything else is filtered
# out of the picker (descriptions, lock files, raw camera formats we can't
# render in the browser, etc).
IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif",
    # HEIC requires extra dependencies and may not be available - we accept
    # it but PIL will raise if the codec isn't installed; we catch and skip.
    ".heic", ".heif",
})

# Maximum thumbnail edge length (pixels). 320 is enough for a crisp ~160px
# grid tile on retina displays without exploding cache size.
THUMBNAIL_MAX_EDGE = 320

# Quality for cached JPEG thumbnails. 80 is the visual-quality vs file-size
# sweet spot - smaller files quantize too aggressively, larger barely visible.
THUMBNAIL_JPEG_QUALITY = 80


# ---------------------------------------------------------------------------
# Default roots (Dad's specific config)
# ---------------------------------------------------------------------------

# Hardcoded for now. Later these become editable in Settings → NAS.
# Path names match what we saw on Dad's NAS during initial setup.
DEFAULT_ROOTS: list[dict[str, str]] = [
    {
        "id": "guitars",
        "label": "Guitar Pictures",
        "path": r"Z:\All Product Pictures\Product Pictures\SW Acoustics Pictures\Guitar Pictures\Guitar Pictures",
    },
    {
        "id": "parts",
        "label": "Guitar Parts",
        # Note: the source folder is misspelled as "Gutiar Parts" on the NAS.
        # We keep the typo here because we have to match Dad's actual filesystem.
        # If/when he renames it on the NAS, we update this string.
        "path": r"Z:\All Product Pictures\Product Pictures\SW Acoustics Pictures\Gutiar Parts",
    },
]


def get_roots() -> list[dict[str, str]]:
    """Return the list of configured root folders, with reachability flags."""
    out = []
    for root in DEFAULT_ROOTS:
        path = Path(root["path"])
        out.append({
            "id": root["id"],
            "label": root["label"],
            "path": str(path),
            "exists": path.exists() and path.is_dir(),
        })
    return out


# ---------------------------------------------------------------------------
# Path security
# ---------------------------------------------------------------------------


class PathOutsideRoots(ValueError):
    """Raised when a requested path isn't under any configured root."""


def validate_path(requested: str | Path) -> Path:
    """Confirm ``requested`` is under one of the configured NAS roots.

    Returns the resolved Path on success. Raises PathOutsideRoots if the
    requested path tries to escape (e.g. via ``..`` or by being an unrelated
    absolute path like ``C:\\Windows``).

    This is the security boundary for everything in this module.
    """
    requested_path = Path(requested)

    # Resolve to absolute, normalized form. resolve(strict=False) handles
    # paths that don't exist yet without raising.
    try:
        resolved = requested_path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        # Bad path (e.g. broken symlink cycle). Treat as invalid.
        raise PathOutsideRoots(f"Cannot resolve path: {requested}") from exc

    for root in DEFAULT_ROOTS:
        root_path = Path(root["path"]).resolve(strict=False)
        try:
            resolved.relative_to(root_path)
            return resolved
        except ValueError:
            continue  # Try the next root

    raise PathOutsideRoots(
        f"Path is not under any configured NAS root: {requested}"
    )


# ---------------------------------------------------------------------------
# Folder listing
# ---------------------------------------------------------------------------


@dataclass
class FolderEntry:
    """One item shown in the picker."""
    name: str
    path: str
    kind: str           # "folder" or "image"
    size_bytes: int     # 0 for folders
    mtime: float        # Unix timestamp (used for thumbnail cache key)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
        }


def list_folder(path: str | Path) -> dict:
    """Enumerate a folder's contents.

    Returns a dict with two sorted lists - subfolders first (alphabetical),
    then images (alphabetical). Non-image files and hidden files are filtered out.

    Raises PathOutsideRoots if the path is outside configured NAS scope.
    Raises FileNotFoundError if the path doesn't exist.
    """
    folder = validate_path(path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")

    folders: list[FolderEntry] = []
    images: list[FolderEntry] = []

    try:
        entries = list(folder.iterdir())
    except PermissionError as exc:
        logger.warning("Permission denied listing %s: %s", folder, exc)
        return {"path": str(folder), "folders": [], "images": [], "error": "Permission denied"}

    for entry in entries:
        name = entry.name
        # Skip hidden files and Office lock files
        if name.startswith(".") or name.startswith("~$"):
            continue

        try:
            stat = entry.stat()
        except (PermissionError, OSError):
            continue

        if entry.is_dir():
            folders.append(FolderEntry(
                name=name, path=str(entry), kind="folder",
                size_bytes=0, mtime=stat.st_mtime,
            ))
        elif entry.is_file():
            ext = entry.suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            images.append(FolderEntry(
                name=name, path=str(entry), kind="image",
                size_bytes=stat.st_size, mtime=stat.st_mtime,
            ))

    # Case-insensitive alphabetical sort
    folders.sort(key=lambda e: e.name.lower())
    images.sort(key=lambda e: e.name.lower())

    return {
        "path": str(folder),
        "folders": [e.to_dict() for e in folders],
        "images": [e.to_dict() for e in images],
    }


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------


def _thumb_cache_key(image_path: Path, mtime: float, size: int) -> str:
    """Build a stable cache key for a thumbnail.

    Includes the path so different files don't collide, plus mtime+size so
    the key changes when the file changes - giving us implicit cache busting.
    """
    h = hashlib.sha256()
    h.update(str(image_path).encode("utf-8", errors="replace"))
    h.update(f"|{mtime}|{size}".encode("ascii"))
    return h.hexdigest()


def get_thumbnail_path(image_path: str | Path) -> Path:
    """Return the on-disk path to the cached thumbnail, generating if needed.

    Always returns a path; if generation fails (corrupt image, unsupported
    format), returns a path that doesn't exist - the caller should check
    .exists() and serve a placeholder.
    """
    source = validate_path(image_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Image not found: {source}")

    stat = source.stat()
    cache_key = _thumb_cache_key(source, stat.st_mtime, stat.st_size)
    cache_dir = settings.thumbnail_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.jpg"

    # If already cached, return immediately
    if cache_path.exists():
        return cache_path

    # Generate
    try:
        with Image.open(source) as img:
            # Apply EXIF orientation so the thumbnail isn't rotated wrong
            img = ImageOps.exif_transpose(img)

            # Convert to RGB for JPEG output (handles RGBA, palette, etc.)
            if img.mode not in ("RGB",):
                img = img.convert("RGB")

            img.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), Image.LANCZOS)
            img.save(cache_path, "JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)
    except Exception as exc:
        logger.warning("Failed to generate thumbnail for %s: %s", source, exc)
        # Make sure we don't leave a partial file behind
        cache_path.unlink(missing_ok=True)
        raise

    return cache_path


def stat_cache() -> dict:
    """Return cache directory stats for diagnostics."""
    cache_dir = settings.thumbnail_cache_dir
    if not cache_dir.exists():
        return {"path": str(cache_dir), "exists": False, "file_count": 0, "total_bytes": 0}

    file_count = 0
    total_bytes = 0
    for f in cache_dir.iterdir():
        if f.is_file():
            file_count += 1
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
    return {
        "path": str(cache_dir),
        "exists": True,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def clear_cache() -> int:
    """Delete all cached thumbnails. Returns the count deleted."""
    cache_dir = settings.thumbnail_cache_dir
    if not cache_dir.exists():
        return 0

    count = 0
    for f in cache_dir.iterdir():
        if f.is_file():
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
    return count

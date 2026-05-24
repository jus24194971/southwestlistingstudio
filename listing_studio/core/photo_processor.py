"""Photo normalization for marketplace uploads.

We can't ship the raw NAS file to a remote host or marketplace because:

- Phone shots are 10-40 MB JPEGs or HEICs; most upload endpoints reject the
  larger ones, and the slow uploads make the UI feel hung.
- Phone shots carry EXIF orientation metadata. PIL's default render ignores
  it, so a "portrait" shot uploaded raw shows up sideways on Reverb.
- Some sources are HEIC, which most marketplace CDNs don't accept.

This module produces a normalized JPEG variant in memory: EXIF-rotated to its
correct orientation, downscaled if huge, encoded at a quality that looks good
on Reverb's product gallery without ballooning size.

It does not write to disk. The caller (uploader, host client) decides what to
do with the bytes.

HEIC note: PIL supports HEIC only when the ``pillow-heif`` plugin is installed.
We try to register it once at import time; if it's not available, .heic/.heif
inputs raise NormalizeError with a clear message instead of a cryptic PIL error.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)


# Long-edge max in pixels. Reverb's gallery serves photos at ~1600px wide
# max; 2048 gives them a hair of headroom for retina without bloating the
# upload size. Picked the same number the FB package uses (config.fb_max_image_size)
# for visual consistency across the app.
MAX_LONG_EDGE = 2048

# JPEG encoder quality. 88 is the visual-quality-vs-size sweet spot we
# settled on for thumbnails too; the difference at 92+ isn't visible on
# product photos and the file grows ~30%.
JPEG_QUALITY = 88


# Try to register HEIC support once at import. If pillow-heif isn't installed
# this is a no-op; the actual NormalizeError happens later when we try to open
# a .heic file. This pattern avoids a hard dependency.
try:  # pragma: no cover - depends on optional dep being installed
    import pillow_heif

    pillow_heif.register_heif_opener()
    _HEIC_AVAILABLE = True
except ImportError:
    _HEIC_AVAILABLE = False


class NormalizeError(Exception):
    """Raised when a photo can't be normalized for upload.

    Carries a human-readable message suitable for surfacing in the UI's
    "failed photos" list. The original exception (if any) is chained.
    """


@dataclass(frozen=True)
class NormalizedPhoto:
    """The result of normalize_for_upload(): JPEG bytes + a suggested filename."""

    data: bytes
    filename: str
    width: int
    height: int

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def normalize_for_upload(source_path: str | Path) -> NormalizedPhoto:
    """Open ``source_path``, normalize it, and return JPEG bytes ready to upload.

    Raises NormalizeError if the file is missing, unreadable, in a format we
    can't decode (typically HEIC without pillow-heif), or PIL chokes on it.

    The returned filename has a ``.jpg`` extension regardless of the input
    extension - downstream hosts and marketplaces want the suffix to match
    the actual content type.
    """
    path = Path(source_path)

    if not path.exists() or not path.is_file():
        raise NormalizeError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix in (".heic", ".heif") and not _HEIC_AVAILABLE:
        raise NormalizeError(
            f"HEIC support not installed. Install pillow-heif to upload {path.name}, "
            f"or convert it to JPEG first."
        )

    try:
        with Image.open(path) as img:
            # Apply EXIF orientation so portrait phone shots don't upload sideways.
            img = ImageOps.exif_transpose(img)

            # Marketplaces want RGB. P-mode (palette), LA (luminance+alpha),
            # RGBA, etc all need flattening; PIL's convert handles transparency
            # by compositing on black, which is fine for product photos.
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Downscale only if the long edge exceeds our limit. Image.thumbnail
            # preserves aspect ratio and modifies in place. We skip when the
            # image is already small enough so we don't waste work re-resampling.
            long_edge = max(img.width, img.height)
            if long_edge > MAX_LONG_EDGE:
                img.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.LANCZOS)

            width, height = img.width, img.height

            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
            data = buf.getvalue()
    except UnidentifiedImageError as exc:
        raise NormalizeError(f"Not a recognized image format: {path.name}") from exc
    except OSError as exc:
        # PIL raises plain OSError for truncated files, decoder failures, etc.
        raise NormalizeError(f"Couldn't read {path.name}: {exc}") from exc

    # Always emit .jpg - the bytes are JPEG regardless of source extension.
    out_name = path.stem + ".jpg"

    return NormalizedPhoto(data=data, filename=out_name, width=width, height=height)

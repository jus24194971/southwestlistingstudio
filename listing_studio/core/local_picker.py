"""Local filesystem photo picker.

Failover for when the NAS isn't reachable (Z: drive unmounted, network down,
or Dad just has a one-off photo on his desktop). Opens the OS's native file
picker dialog via pywebview and returns the selected paths.

This is the only place we shell out to pywebview from outside the GUI thread,
and it has a couple of subtleties worth knowing:

- ``create_file_dialog`` is *blocking* - it doesn't return until the user
  picks or cancels. Calling it from inside an async FastAPI handler would
  freeze the request loop, so callers must wrap it with ``asyncio.to_thread``.
- It must be called from a non-GUI thread (which a FastAPI worker is, so
  that's fine). Calling it from the main thread can deadlock on some OSes.
- ``webview.windows`` is empty before ``webview.start()`` runs - if someone
  invokes this from a non-GUI context (e.g. pytest, headless CLI), we
  return an empty list rather than crash.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# File types accepted by the dialog. The format is pywebview's: a tuple of
# strings where each string is "Label (*.ext;*.ext2;...)". We list the same
# extensions the NAS picker accepts so the failover doesn't surprise Dad by
# refusing a format he could use over the NAS.
IMAGE_FILE_FILTER: tuple[str, ...] = (
    "Image Files (*.jpg;*.jpeg;*.png;*.webp;*.gif;*.bmp;*.tiff;*.tif;*.heic;*.heif)",
    "All Files (*.*)",
)


def pick_local_photos() -> list[str]:
    """Open the native file dialog and return the selected file paths.

    Returns an empty list if the user cancelled, if multiple selection
    returned nothing, or if no pywebview window exists yet (e.g. called
    from a context where the GUI hasn't started).

    Filters non-existent paths defensively - some OS dialogs can return
    paths to phantom items in rare cases.
    """
    try:
        import webview  # imported lazily so non-GUI callers don't pay the cost
    except ImportError:
        logger.warning("pywebview not importable; local picker unavailable")
        return []

    if not webview.windows:
        logger.warning("No pywebview window active; local picker unavailable")
        return []

    window = webview.windows[0]

    try:
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=IMAGE_FILE_FILTER,
        )
    except Exception as exc:  # pragma: no cover - depends on OS dialog
        logger.warning("File dialog failed: %s", exc)
        return []

    # pywebview returns None on cancel, or a tuple/list of paths on success.
    # Normalize to a list of validated string paths.
    if not result:
        return []

    paths: list[str] = []
    for raw in result:
        if not raw:
            continue
        candidate = Path(str(raw))
        if candidate.exists() and candidate.is_file():
            paths.append(str(candidate.resolve()))
        else:
            logger.warning("Picker returned non-existent path: %s", raw)

    return paths

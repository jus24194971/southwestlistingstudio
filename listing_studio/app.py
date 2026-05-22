"""Application launcher.

Starts the embedded FastAPI server on a background thread, then opens the
pywebview window pointed at the local server. When the window closes, the
process exits (the FastAPI thread is a daemon, so it dies with us).

The two-process-in-one-process arrangement is the standard pywebview pattern
for "Python desktop app that uses a web UI". It's simpler than IPC and lets
us use FastAPI's full feature set (auto-generated docs at /docs, etc.).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

import uvicorn

from listing_studio import __app_name__
from listing_studio.config import settings
from listing_studio.core.db import init_db
from listing_studio.core.seed import seed_sample_data_if_empty
from listing_studio.ui.api import app as fastapi_app

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _run_uvicorn() -> None:
    """Run uvicorn in this thread, blocking forever.

    Retries binding for up to ~15 seconds if the port is in use. This handles
    the case where we restarted after an auto-update and the old process's
    socket is still in TIME_WAIT. Without retry, the new process would die
    on startup and the user would see "can't reach this page".
    """
    # Lower the access-log noise; we don't need a line per UI request
    log_config = uvicorn.config.LOGGING_CONFIG  # type: ignore[attr-defined]
    log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"

    last_error = None
    for attempt in range(15):  # ~15 attempts at 1s apart
        try:
            uvicorn.run(
                fastapi_app,
                host=settings.api_host,
                port=settings.api_port,
                log_level="info",
                log_config=log_config,
                # No reload - we're embedded, not in dev mode
            )
            return  # uvicorn.run blocks; if it returns, we shut down cleanly
        except OSError as exc:
            # Errno 10048 = WSAEADDRINUSE on Windows; 98 = EADDRINUSE on Unix
            if getattr(exc, "errno", None) in (10048, 98) or "address already in use" in str(exc).lower():
                last_error = exc
                logger.warning(
                    "Port %s busy on attempt %d/15, retrying in 1s",
                    settings.api_port, attempt + 1,
                )
                time.sleep(1.0)
                continue
            raise  # Different error - don't swallow

    logger.error("Failed to bind port %s after 15 attempts: %s",
                 settings.api_port, last_error)
    raise RuntimeError(
        f"Could not bind port {settings.api_port} after retries. "
        f"Another Listing Studio instance may already be running."
    )


def _start_api_thread() -> threading.Thread:
    """Spawn the FastAPI server on a daemon thread and return the thread."""
    t = threading.Thread(target=_run_uvicorn, daemon=True, name="listing-studio-api")
    t.start()

    # Wait briefly for the server to start. This is a pragmatic
    # alternative to polling - the API is local and very fast to start.
    # If it takes longer than a few seconds something is wrong, and the
    # window will just show a connection error in the UI anyway.
    time.sleep(0.5)
    return t


def _wait_for_api(timeout_seconds: float = 20.0) -> bool:
    """Poll the local API until it responds (or we time out).

    Timeout is generous (20s) to handle the post-update restart case where
    uvicorn may be retrying the bind while the old process's socket clears
    out of TIME_WAIT.
    """
    import httpx

    start = time.monotonic()
    url = f"http://{settings.api_host}:{settings.api_port}/api/health"
    while time.monotonic() - start < timeout_seconds:
        try:
            response = httpx.get(url, timeout=0.5)
            if response.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(0.1)
    return False


def run() -> None:
    """Boot the database, start the API, open the window."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Initializing database at %s", settings.db_path)
    settings.ensure_dirs()
    init_db()

    if seed_sample_data_if_empty():
        logger.info("Seeded sample data (first-run)")

    logger.info("Starting embedded API on %s:%s", settings.api_host, settings.api_port)
    _start_api_thread()

    if not _wait_for_api():
        logger.warning("API didn't respond within 5s - opening window anyway")

    # Import pywebview late so we don't take the GUI dependency during DB-only flows
    # (e.g. running migrations or tests).
    import webview

    url = f"http://{settings.api_host}:{settings.api_port}/"
    logger.info("Opening window: %s", url)

    webview.create_window(
        title=settings.window_title,
        url=url,
        width=settings.window_width,
        height=settings.window_height,
        min_size=(settings.window_min_width, settings.window_min_height),
        background_color="#1B1813",
    )

    # Block until the window closes
    webview.start(debug=False)
    logger.info("Window closed, exiting")

"""Background polling service for Squarespace orders.

Runs on a background asyncio task started by ``app.py``. Every
``settings.squarespace_poll_interval_seconds`` it asks Squarespace
"any new orders since the last cursor?" and feeds new orders into
the inventory sync logic.

Currently a skeleton: the actual Squarespace API call lives in
``platforms.squarespace.SquarespaceConnector.fetch_recent_orders`` (also
stubbed). The orchestration and error handling here are real and will
work as soon as that one method does.

Design:
  - Single async task, one poll at a time (no concurrency within a single
    platform - keeps the cursor logic simple)
  - Exponential backoff on consecutive failures (don't hammer Squarespace
    if their API is down)
  - Cursor persisted to ``PollingCursor`` table after each successful poll
  - Disable-able via ``settings.squarespace_poll_enabled`` (useful for tests)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from listing_studio.config import settings
from listing_studio.core.db import session_scope
from listing_studio.core.models import Platform, PollingCursor
from listing_studio.platforms.squarespace import SquarespaceConnector

logger = logging.getLogger(__name__)


async def _poll_once() -> None:
    """Do one poll cycle. Reads the cursor, asks Squarespace for new orders,
    updates the cursor on success.

    Doesn't raise - any exception is logged and reflected in the cursor's
    ``consecutive_failures`` count so callers can decide whether to back off.
    """
    connector = SquarespaceConnector()
    if not await connector.is_connected():
        logger.debug("Squarespace not connected; skipping poll")
        return

    # Load or create the cursor
    with session_scope() as session:
        cursor = session.get(PollingCursor, Platform.SQUARESPACE)
        if cursor is None:
            cursor = PollingCursor(
                platform=Platform.SQUARESPACE,
                last_seen_at=None,
                last_polled_at=None,
                consecutive_failures=0,
            )
            session.add(cursor)
            session.flush()

        since = cursor.last_seen_at or datetime.now(timezone.utc)
        consecutive_failures = cursor.consecutive_failures

    # Make the API call outside the DB session
    try:
        orders = await connector.fetch_recent_orders(since)
    except Exception as exc:
        # Squarespace API failed - bump failure count, don't advance cursor
        logger.warning("Squarespace poll failed: %s", exc)
        with session_scope() as session:
            cursor = session.get(PollingCursor, Platform.SQUARESPACE)
            if cursor is not None:
                cursor.consecutive_failures = consecutive_failures + 1
                cursor.last_error = str(exc)
                cursor.last_polled_at = datetime.now(timezone.utc)
        return

    # Success path: process orders, advance cursor, reset failure count
    logger.info("Squarespace poll: %d new order(s)", len(orders))
    # TODO: dispatch each order to inventory sync logic (decrement other platforms)

    with session_scope() as session:
        cursor = session.get(PollingCursor, Platform.SQUARESPACE)
        if cursor is not None:
            cursor.last_seen_at = datetime.now(timezone.utc)
            cursor.last_polled_at = datetime.now(timezone.utc)
            cursor.consecutive_failures = 0
            cursor.last_error = None


async def run_polling_loop() -> None:
    """Long-running task: poll Squarespace forever.

    Cancelled when the app exits (it's run via ``asyncio.create_task`` in
    ``app.py`` after the FastAPI thread is up).
    """
    if not settings.squarespace_poll_enabled:
        logger.info("Squarespace polling disabled by config")
        return

    interval = settings.squarespace_poll_interval_seconds
    max_failures = settings.squarespace_poll_max_consecutive_failures

    logger.info("Squarespace polling started (every %ds)", interval)

    while True:
        try:
            await _poll_once()
        except Exception as exc:  # pragma: no cover - last-resort catch
            logger.exception("Squarespace polling loop error: %s", exc)

        # Read latest cursor to check failure count for backoff
        with session_scope() as session:
            cursor = session.get(PollingCursor, Platform.SQUARESPACE)
            failures = cursor.consecutive_failures if cursor else 0

        # Exponential backoff after repeated failures: 1x, 2x, 4x... up to 8x interval.
        # Keeps us from hammering Squarespace if their API is having a bad day.
        if failures >= max_failures:
            backoff_multiplier = min(2 ** (failures - max_failures + 1), 8)
            sleep_for = interval * backoff_multiplier
            logger.warning(
                "Squarespace poll has failed %d times; backing off to %ds",
                failures, sleep_for,
            )
        else:
            sleep_for = interval

        await asyncio.sleep(sleep_for)

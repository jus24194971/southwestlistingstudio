"""Posting orchestrator: coordinates posting one template to multiple platforms.

The 'Post Listing' button calls ``post_to_platforms()``. It:

  1. Resolves the connector for each requested platform
  2. Applies any per-platform overrides from the form
  3. Posts to all platforms in parallel (if ``post_parallel`` is on)
  4. Records each attempt in the ``posts`` table
  5. Returns a ``PostResponse`` for the UI to display

Parallel + best-effort by default: one platform failing doesn't abort the others.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from listing_studio.config import settings
from listing_studio.core import templates as templates_repo
from listing_studio.core.db import session_scope
from listing_studio.core.models import Platform, Post, PostStatus, Template
from listing_studio.core.schemas import (
    FacebookPackage,
    PlatformOverride,
    PostRequest,
    PostResponse,
    PostResult,
)
from listing_studio.platforms.base import PlatformConnector, PostOutcome, PostingError
from listing_studio.platforms.ebay import EbayConnector
from listing_studio.platforms.etsy import EtsyConnector
from listing_studio.platforms.facebook_package import FacebookConnector
from listing_studio.platforms.reverb import ReverbConnector
from listing_studio.platforms.squarespace import SquarespaceConnector

# Map each platform to its connector class. Instances are created per-request
# because connectors are stateless - cheap to construct.
_CONNECTOR_CLASSES: dict[Platform, type[PlatformConnector]] = {
    Platform.REVERB: ReverbConnector,
    Platform.EBAY: EbayConnector,
    Platform.ETSY: EtsyConnector,
    Platform.SQUARESPACE: SquarespaceConnector,
    Platform.FACEBOOK: FacebookConnector,
}


def get_connector(platform: Platform) -> PlatformConnector:
    """Return a fresh connector instance for the given platform."""
    return _CONNECTOR_CLASSES[platform]()


def _resolve_price(template: Template, platform: Platform, override: PlatformOverride | None) -> int:
    """Determine the price to send to a platform.

    Precedence: explicit override > template's per-platform override > base price.
    """
    if override and override.price_cents is not None:
        return override.price_cents
    return templates_repo.resolve_price_cents(template, platform)


async def _post_to_single(
    template: Template,
    platform: Platform,
    override: PlatformOverride | None,
) -> tuple[PostResult, PostOutcome]:
    """Post to one platform and return (PostResult, raw_outcome).

    The raw outcome is returned alongside so the orchestrator can extract
    things like the Facebook package without re-running anything.
    """
    connector = get_connector(platform)
    price_cents = _resolve_price(template, platform, override)
    started = time.monotonic()

    try:
        outcome = await connector.post(template, price_cents, template.quantity)
        elapsed = int((time.monotonic() - started) * 1000)
        result = PostResult(
            platform=platform,
            status=outcome.status,
            price_cents=price_cents,
            external_listing_id=outcome.external_listing_id,
            external_listing_url=outcome.external_listing_url,
            error_message=outcome.error_message,
            elapsed_ms=elapsed,
        )
        return result, outcome
    except PostingError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        result = PostResult(
            platform=platform,
            status=PostStatus.FAILED,
            price_cents=price_cents,
            error_message=exc.message,
            elapsed_ms=elapsed,
        )
        return result, PostOutcome(status=PostStatus.FAILED, error_message=exc.message)
    except Exception as exc:  # pragma: no cover - defensive against unexpected errors
        elapsed = int((time.monotonic() - started) * 1000)
        result = PostResult(
            platform=platform,
            status=PostStatus.FAILED,
            price_cents=price_cents,
            error_message=f"Unexpected error: {exc}",
            elapsed_ms=elapsed,
        )
        return result, PostOutcome(status=PostStatus.FAILED, error_message=str(exc))


async def post_to_platforms(request: PostRequest) -> PostResponse:
    """Post a template to all requested platforms.

    Honors ``settings.post_parallel`` to decide between concurrent and serial.
    Honors ``settings.post_best_effort`` to decide whether one failure aborts
    the others.
    """
    overall_start = time.monotonic()

    # Load the template once, outside the connector loop, so we don't hammer the DB.
    with session_scope() as session:
        template = templates_repo.get_template(session, request.template_id)
        if template is None:
            raise ValueError(f"Template {request.template_id} not found")

        # Snapshot template attributes we need (we leave the session scope before posting)
        template_id = template.id
        # Detach so we can use it outside the session
        session.expunge(template)

    # Build per-platform tasks
    async def _task(platform: Platform) -> tuple[PostResult, PostOutcome]:
        override = request.overrides.get(platform)
        return await _post_to_single(template, platform, override)

    results: list[PostResult] = []
    raw_outcomes: list[PostOutcome] = []

    if settings.post_parallel:
        # All in parallel
        outputs = await asyncio.gather(
            *[_task(p) for p in request.platforms],
            return_exceptions=False,
        )
        for result, outcome in outputs:
            results.append(result)
            raw_outcomes.append(outcome)
    else:
        # Sequential, with early-stop if not best-effort
        for platform in request.platforms:
            result, outcome = await _task(platform)
            results.append(result)
            raw_outcomes.append(outcome)
            if result.status == PostStatus.FAILED and not settings.post_best_effort:
                break

    # Persist Post rows and bump template counters in a single transaction
    with session_scope() as session:
        for result in results:
            session.add(
                Post(
                    template_id=template_id,
                    platform=result.platform,
                    status=result.status,
                    price_cents=result.price_cents,
                    quantity=template.quantity,
                    external_listing_id=result.external_listing_id,
                    external_listing_url=result.external_listing_url,
                    error_message=result.error_message,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
            )
        templates_repo.record_post_attempt(session, template_id)

    # Extract the Facebook package if FB was one of the targets
    fb_package = None
    for outcome in raw_outcomes:
        if outcome.facebook_package is not None:
            fb_package = FacebookPackage(**outcome.facebook_package)
            break

    total_ms = int((time.monotonic() - overall_start) * 1000)
    return PostResponse(
        template_id=template_id,
        results=results,
        total_elapsed_ms=total_ms,
        facebook_package=fb_package,
    )

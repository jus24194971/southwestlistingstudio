"""Platform connectors (Reverb, eBay, Etsy, Squarespace, Facebook).

All connectors implement ``PlatformConnector`` so the posting orchestrator
can treat them uniformly. Each connector wraps the platform's HTTP API and
maps between our internal Template model and the platform's listing format.
"""

from listing_studio.platforms.base import PlatformConnector, PostingError

__all__ = ["PlatformConnector", "PostingError"]

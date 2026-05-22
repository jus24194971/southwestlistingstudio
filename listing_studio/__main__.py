"""Entry point: `python -m listing_studio`."""

from __future__ import annotations

import sys


def main() -> int:
    """Launch Listing Studio."""
    # Import here, not at module level, so that the package can be imported
    # without immediately initializing pywebview / FastAPI (useful for tests).
    from listing_studio.app import run

    try:
        run()
        return 0
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        return 0
    except Exception as exc:  # pragma: no cover - top-level catch
        print(f"Fatal error: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Entry point: `python -m listing_studio` or the bundled .exe.

IMPORTANT: Order of operations matters here.

When running as a windowed PyInstaller bundle (console=False), Python's
stdout and stderr point to invalid handles. Any module that prints during
import - uvicorn's loggers, FastAPI's startup messages, pydantic-settings -
will hang or crash the bundled app.

The fix is to redirect stdout/stderr to a log file BEFORE any other module
imports. So we deliberately do _stdout_setup FIRST, then import everything
else. Don't reorder these imports.
"""

from __future__ import annotations

# === Stdout redirect MUST happen first, before any other imports ===
from listing_studio import _stdout_setup

_redirected_to = _stdout_setup.setup()

# Now safe to import everything else
import sys


def main() -> int:
    """Launch Listing Studio."""
    # Import here, not at module level, so that the package can be imported
    # without immediately initializing pywebview / FastAPI (useful for tests).
    from listing_studio.app import run

    if _redirected_to is not None:
        # Helpful breadcrumb so we can find the log if Dad reports a problem
        print(f"Logging to: {_redirected_to}")

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

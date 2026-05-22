# Listing Studio

Cross-platform marketplace listing tool for Southwest Acoustics. Lets Dad post a guitar
part once and have it cross-listed to Reverb, eBay, and Etsy automatically, plus generate
a ready-to-paste package for Facebook Marketplace.

## Status: Framework scaffold (v0.1.0)

This is the **scaffolded skeleton**. It runs end-to-end (window opens, UI loads, backend
talks to SQLite database) but no real platform APIs are wired up yet.

What works today:
- Native desktop window via pywebview
- HTML UI loaded from `listing_studio/ui/templates/`
- FastAPI backend running embedded in the same process
- SQLite database initialized with the full schema
- Mock template data seeded on first run so the UI has something to show
- Platform connector abstraction defined (Reverb, eBay, Etsy, Facebook stubs)

What does NOT work yet:
- Actual API calls to Reverb, eBay, Etsy
- NAS photo browsing (modal is stubbed)
- OAuth token flows (settings stubbed)
- Facebook copy-paste package generation

## Running locally

```bash
# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate       # macOS/Linux

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the app
python -m listing_studio
```

First launch will create `~/.listing_studio/listing_studio.db` and seed it with sample
template data so the UI has something to display.

## Project layout

```
listing_studio/
+-- pyproject.toml                       # Dependencies + project metadata
+-- README.md                            # You are here
+-- listing_studio/                      # The Python package
|   +-- __init__.py                      # Package version
|   +-- __main__.py                      # `python -m listing_studio` entry point
|   +-- config.py                        # Settings (paths, ports, defaults)
|   +-- app.py                           # pywebview window + FastAPI launcher
|   +-- core/
|   |   +-- __init__.py
|   |   +-- db.py                        # SQLAlchemy engine, session, init
|   |   +-- models.py                    # ORM models (Template, Post, etc.)
|   |   +-- schemas.py                   # Pydantic request/response shapes
|   |   +-- templates.py                 # Template CRUD operations
|   |   +-- posting.py                   # Parallel posting orchestrator
|   |   +-- credentials.py               # Keyring wrapper for OAuth tokens
|   |   +-- seed.py                      # Sample data for first run
|   +-- platforms/
|   |   +-- __init__.py
|   |   +-- base.py                      # PlatformConnector abstract base class
|   |   +-- reverb.py                    # Reverb API client (stub)
|   |   +-- ebay.py                      # eBay API client (stub)
|   |   +-- etsy.py                      # Etsy API client (stub)
|   |   +-- facebook_package.py          # FB copy-paste generator (stub)
|   +-- ui/
|   |   +-- __init__.py
|   |   +-- api.py                       # FastAPI routes (called from the HTML UI via fetch)
|   |   +-- templates/
|   |   |   +-- index.html               # The main window (from our mockup)
|   |   +-- static/
|   |       +-- app.js                   # Client-side bridge to FastAPI
|   |       +-- styles.css               # Extracted from the mockup
|   +-- assets/
|       +-- southwest_logo.png           # Brand logo
+-- tests/                               # (empty for now)
```

## Key architectural decisions (recap)

- **pywebview** wraps Chromium in a native window. The UI is HTML/CSS/JS exactly
  matching the mockups. The JS calls a local FastAPI server (also running in this
  process) via `fetch()`. No browser, no internet required for the UI itself.
- **SQLite** is the data store. The DB file lives at `~/.listing_studio/`.
- **Keyring** stores OAuth tokens in the OS credential store (Windows Credential
  Manager, macOS Keychain, etc.). Never touches the filesystem.
- **httpx** is the HTTP client for talking to platform APIs. Async-capable so we
  can post to multiple platforms in parallel.
- **Pillow** handles thumbnail generation and the photo resizing for the Facebook
  package handoff.

## Development workflow

```bash
# Format + lint
ruff format .
ruff check . --fix

# Run tests (once we have them)
pytest

# Type-check
mypy listing_studio
```

## What to build next (in order)

1. Wire the photo picker modal to a stub NAS browser endpoint
2. Implement the Reverb connector against the real Reverb API (start with sandbox)
3. Add OAuth flow handling (Reverb first, then Etsy)
4. Implement the Facebook copy-paste package generation
5. eBay connector (needs eBay developer account first)
6. Etsy connector
7. PyInstaller packaging for Windows distribution

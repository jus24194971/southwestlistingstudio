# Listing Studio — project context for Claude Code

This file tells Claude Code (and you, when you come back to this in three
months) the things about this project that aren't obvious from the code or
git history.

## What this is

A Windows/Mac desktop app for Southwest Acoustics — a small guitar-parts
business. It lets the shop owner post a part once and have it cross-listed
to Reverb, eBay, Etsy, plus generate a copy-paste package for Facebook
Marketplace.

The single user is **Dad** (Justin's father). He runs the business; he's
not a developer. UX decisions skew toward "fewer clicks, plain-English
error messages, no jargon." When you propose a change, ask: would this
make sense to someone who hasn't touched the codebase?

## Architecture, in one paragraph

[pywebview](https://pywebview.flowrl.com/) wraps a Chromium window around a
local FastAPI server (both in the same Python process). The UI is plain
HTML/CSS/JS in `listing_studio/ui/static/`; the JS calls the FastAPI
backend over `fetch()`. SQLite at `%LOCALAPPDATA%\ListingStudio\` is the
data store. OAuth tokens and API keys live in **Windows Credential
Manager** via `keyring` — never on disk. Auto-update pulls signed releases
from GitHub Releases.

Entry point: `python -m listing_studio` (or the bundled `.exe`).

## Reverb photo handling — the important architectural quirk

**Reverb's API does not accept binary photo uploads.** The endpoint
`POST /listings/{id}/images` that looks like it would work returns 405.
The only working way to attach photos is to pass **publicly fetchable
URLs** in the create/update payload's `photos` field; Reverb fetches the
images server-side.

This shapes the code:

- `listing_studio/core/photo_processor.py` — opens a NAS photo via PIL,
  applies EXIF orientation, downscales to 2048px long edge, re-encodes as
  JPEG q88. Returns bytes ready to upload.
- `listing_studio/core/photo_host.py` — abstract `PhotoHost` interface +
  concrete `ImgBBHost`. Upload returns a public URL.
- `listing_studio/ui/api.py:post_template_to_reverb` — if a photo host is
  configured, normalizes each NAS photo, uploads to the host, collects
  URLs, then calls `ReverbConnector.create_draft(..., photo_urls=urls)`.
  Without a host configured, the draft is created photoless and the UI
  prompts Dad to drag photos in via the Reverb web UI.

When you touch this area, the relevant docs are:
- https://www.reverb-api.com/docs/create-listings (the `photos` field)
- https://api.imgbb.com/ (single-key upload endpoint)

Don't reintroduce code that POSTs binary photo data to Reverb. It can't
work.

## NAS quirks

Dad's photos live on a network drive mapped at `Z:\`. The two roots in
use today are hardcoded in `listing_studio/core/nas.py:DEFAULT_ROOTS`:

- `Z:\All Product Pictures\Product Pictures\SW Acoustics Pictures\Guitar Pictures\Guitar Pictures`
- `Z:\All Product Pictures\Product Pictures\SW Acoustics Pictures\Gutiar Parts`  ← intentional typo

The "Gutiar Parts" misspelling exists on Dad's actual NAS. If we fix the
code, the path breaks. If Dad renames the folder, we update the constant.
Don't silently "correct" it.

The picker uses a thumbnail cache at `%LOCALAPPDATA%\ListingStudio\thumbnail_cache\`.
Cache keys include `(source_path, mtime, size)` so we invalidate
automatically when a file changes.

### Local-file failover (v0.3.1+)

When the NAS isn't reachable, the picker falls back to the OS native file
dialog via `listing_studio/core/local_picker.py`. Architecture:

- `local_picker.pick_local_photos()` wraps `webview.create_file_dialog()`.
  It's blocking, so the API handler runs it via `asyncio.to_thread`.
- `nas._extra_allowed_dirs` is an in-memory set of directories whose
  contents are allowed through `validate_path()`. Each successful
  `register_local_file(path)` call (from `/api/photos/pick-local`) adds
  the file's parent directory.
- Once registered, locally-picked photos are indistinguishable from NAS
  photos to the rest of the app — same `TemplatePhoto.source_path`,
  same thumbnail endpoint, same photo-host upload pipeline.

Security note: the allowlist is *write-only by the local picker endpoint*.
A client can't manually whitelist `C:\Windows\` by crafting a request —
the file path has to come back from the OS dialog. The allowlist clears
on restart, which is fine: re-attaching previously-saved local photos
still works because `validate_path` checks the file's directory and the
user can re-pick to refresh the allowlist if they need to add more from
the same folder.

## Drafts only, for now

Every posting flow currently creates **drafts**, not live listings. Dad
reviews them on the marketplace and publishes manually. We're not ready
to flip the "auto-publish" switch until:

1. The photo path is solid end-to-end (in progress).
2. Reverb's category/condition UUID resolution has been battle-tested
   across the full catalog.
3. We have an "undo" or "delete a posted listing" affordance in case of
   misfires.

If you're adding a new platform connector, default to draft creation and
leave the publish step as a follow-up endpoint.

## Credentials

`listing_studio/core/credentials.py` has two parallel APIs:

- **Platform credentials** — keyed by `Platform` enum. Used for Reverb's
  personal access token, Squarespace API key, etc. Keyring username
  scheme: `oauth_token::<platform_value>`.
- **Service credentials** — keyed by free-form service name. Used for
  non-platform services like the ImgBB image host. Keyring username
  scheme: `service::<name>`.

Both serialize the credential blob as JSON and store it via Windows
Credential Manager (or the OS equivalent). The blob can carry arbitrary
extra fields (`account_label`, `expires_at`, etc.) — only `api_key` is
strictly required.

## Settings UI pattern

`listing_studio/ui/static/js/settings.js` renders the Settings screen.
The pattern for adding a new connectable service:

1. Backend: implement a connector with `test_connection()`. Wire connect/
   disconnect/test endpoints.
2. UI: add a card builder (`buildXCard`) and a connect modal
   (`openXConnectModal`). For platform-style API-key auth, see
   `buildPhotoHostCard` and `openPhotoHostConnectModal` as the cleanest
   example (it's separate from `openApiKeyConnectModal` because the URL
   namespace differs).

## Folders worth knowing

```
listing_studio/                 # the Python package
├── __main__.py                 # `python -m listing_studio` entry point
├── app.py                      # pywebview window + FastAPI launcher
├── _stdout_setup.py            # MUST be imported first (PyInstaller bundle redirects)
├── config.py                   # settings (paths, ports, defaults)
├── core/
│   ├── db.py                   # SQLAlchemy engine + session_scope context manager
│   ├── models.py               # ORM models (Template, Post, Category, ...)
│   ├── credentials.py          # keyring wrapper (platform + service flavors)
│   ├── nas.py                  # NAS browsing, thumbnail cache
│   ├── photo_processor.py      # normalize NAS photos for upload
│   ├── photo_host.py           # PhotoHost abstract + ImgBBHost
│   ├── posting.py              # cross-platform post orchestrator
│   ├── preferences.py          # DB-stored user preferences
│   ├── seed.py                 # first-run sample data
│   └── templates.py            # template CRUD
├── platforms/
│   ├── base.py                 # PlatformConnector ABC
│   ├── reverb.py               # the most mature connector
│   ├── ebay.py / etsy.py       # stubs
│   ├── facebook_package.py     # copy-paste FB output (no API)
│   └── squarespace.py
└── ui/
    ├── api.py                  # all FastAPI routes
    ├── templates/index.html    # the single-page UI
    └── static/                 # css/, js/, brand logo
```

## Dev workflow

```powershell
# Activate venv
.venv\Scripts\activate

# Format + lint
ruff format .
ruff check . --fix

# Type-check
mypy listing_studio

# Tests (no tests yet — see the empty tests/ folder; aspirational)
pytest

# Run the app against your local DB
python -m listing_studio
```

The log file each run produces lives at
`%LOCALAPPDATA%\ListingStudio\logs\` — useful when a packaged build
misbehaves and you can't see stderr.

## Version + release process

Version lives in `listing_studio/__init__.py` (`__version__`). Bump it
before tagging a release. The auto-updater (`listing_studio/core/updater.py`)
checks GitHub Releases on the configured repo; misconfigured `GITHUB_REPO`
is a real failure mode that's bitten us before (see commit `05add4c`).

PyInstaller specs:
- `listing_studio.spec` — Windows build
- `listing_studio_mac.spec` — macOS build
- `BUILD_WINDOWS.md` — packaging notes
- `AUTO_UPDATE.md` — how the in-app updater works

## Conventions

- Type-annotate everything. mypy strict-ish; we tolerate `Any` only at
  third-party boundaries (Reverb's JSON, keyring blobs).
- Docstrings explain *why*, not *what*. The "what" is what code reading
  is for; the "why" is what's hard to recover later.
- Avoid hardcoding NAS paths in new code — read from `core.nas.DEFAULT_ROOTS`
  or whatever supersedes it. If you find a hardcode, it's tech debt worth
  flagging.
- Error messages that surface to Dad should be plain English, not
  framework-speak. `"Reverb rejected the token"` good, `"401 Unauthorized
  from /api/my/account"` bad.
- Don't introduce dependencies casually. Each one is one more thing
  PyInstaller has to handle on a Windows build that runs on a non-dev
  machine.

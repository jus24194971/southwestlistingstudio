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

## Cross-platform category mapping (v0.4.0+)

Each marketplace has a different taxonomy model:

- **Reverb** — strict UUID hierarchy (~700 categories). Fetched via
  `ReverbConnector.search_taxonomy()`, cached in-memory.
- **eBay** — strict numeric ID hierarchy (~24,000 categories). Listings
  are only valid on leaves. Fetched via `EbayConnector.search_taxonomy()`
  using the US default tree (`tree_id="0"`), cached in-memory.
- **Squarespace** — no strict taxonomy. Products live on store pages the
  user defined. `SquarespaceConnector.fetch_store_pages()` infers them
  from existing products.

The `Category` model carries first-class fields for all three:
`reverb_*`, `ebay_*`, `squarespace_*`. The generic `platform_config` JSON
remains for future platforms (Etsy) that don't yet have schema columns.

### Suggestion engine (`core/category_suggest.py`)

When Dad picks a category on one platform, the engine suggests the
matching category on another. Two layers:

1. **Direct mappings** (`category_mappings` table). Two sources:
   - `source='shipped'`: loaded once at first run from
     `data/seed_category_mappings.json` — hand-curated for Dad's known
     inventory. Some entries start with null eBay IDs as placeholders
     and get verified post-launch.
   - `source='learned'`: recorded automatically every time the user
     saves a Category with two or more platforms populated. Both
     directions (A→B and B→A) are inserted so suggestions work either way.
2. **Fuzzy name match** against the target platform's cached taxonomy,
   using the source category's display name as the query. Lowest
   confidence; only invoked if direct lookup is empty. Handled at the
   API endpoint (it needs async access to the connector); the engine
   itself is sync.

### Recently-used tracking (`category_usage` table)

Updated on every Category save: one row per (platform, external_id) with
last_used_at and use_count. The picker UIs query
`/api/categories/usage/recent?platform=...` and show the top 6 as pills
above the search results.

## eBay credentials (the two-tier story)

eBay has two distinct token types, both implemented in v0.5.0:

- **App token** (`client_credentials` grant from the developer app's
  `client_id` + `client_secret`). Read-only; works for the taxonomy API
  and other public endpoints. Lives in memory only, refreshed every ~2hr.
  No user consent required. The category picker uses this exclusively.
- **User token** (`authorization_code` grant via OAuth redirect). Tied to
  Dad's actual eBay seller account; required for inventory/listing
  endpoints. Stored in the keyring alongside the app credentials.
  Refresh logic is automatic — `_get_user_token()` checks expiry and
  refreshes via the refresh_token if needed (60s safety buffer).

### eBay OAuth flow (browser-based)

1. **Settings → eBay → Connect** opens `openEbayConnectModal` in
   settings.js. The modal collects `client_id`, `client_secret`, and
   `ru_name` (RuName — eBay's registered redirect identifier).
2. Step 1 POSTs to `/api/settings/platforms/ebay/connect`. The backend
   validates by fetching an app token, then stores the three fields.
3. Step 2's "Authorize Seller Account" button calls
   `/api/ebay/oauth/start`, which constructs the authorize URL (using
   the RuName as `redirect_uri`, not a real URL) and opens the system
   browser via Python's `webbrowser` module.
4. The user logs in to eBay and approves. eBay redirects to the URL
   associated with the RuName in eBay's dashboard — configured to be
   `http://localhost:8731/api/ebay/oauth/callback`.
5. The callback endpoint exchanges the `code` query param for
   access_token + refresh_token via `EbayConnector.exchange_code_for_tokens`,
   stores them in the credentials blob, and returns a styled HTML "you
   can close this tab" page.
6. The modal polls `/api/settings/platforms/ebay/oauth-status` every
   2 seconds until `has_user_token: true`, then transforms to show
   the "Done" button.

The RuName-to-URL mapping is configured in eBay's developer dashboard,
NOT in our code. If we ever change the callback URL we have to update
the eBay side too.

Credentials blob shape after a full connect + authorize:

```
{
    "client_id":  "...",
    "client_secret": "...",
    "ru_name": "...",
    "user_access_token":  "...",   # 2hr lifetime
    "user_refresh_token": "...",   # 18mo lifetime
    "user_token_expires_at": "ISO timestamp",
    "user_refresh_expires_at": "ISO timestamp",
    "account_label": "<eBay seller username>"
}
```

## In-app Help view (v0.5.0+)

`ui/static/js/help.js` defines a SECTIONS array — each entry is one
help topic with `{id, icon, title, subtitle, content}`. The TOC and
content pane both render from this array, so adding a new help section
means appending one object. Content is HTML; keep it self-contained and
use the `.help-*` classes from `css/help.css` for styling (callouts,
step lists, Q&A blocks).

When you add a feature elsewhere in the app, add a help section here
too — Dad uses this when he's stuck.

The keyring blob shape:
```
{
    "client_id":  "...",      # App ID
    "client_secret": "...",   # Cert ID (shown once at creation)
    "dev_id":     "...",      # optional, legacy APIs
    "user_access_token":  "...",  # populated by future OAuth flow
    "user_refresh_token": "...",
    "user_token_expires_at": "ISO timestamp",
    "account_label": "<eBay user id>"
}
```

`EbayConnector.is_connected()` returns true once `client_id` +
`client_secret` are present — the minimum-viable state for taxonomy
reads. Posting will additionally require the user tokens.

## Accessibility (v0.5.3+)

Two preferences live in the `preferences` table and feed CSS rules in
`ui/static/css/base.css`:

- `font_scale` (`"normal"` / `"large"` / `"xlarge"`) — applied as a CSS
  `zoom` on `<body>`. Chromium's `zoom` scales every nested px-value at
  once, avoiding the need to refactor every stylesheet to use rem.
- `high_contrast` (bool) — adds `.high-contrast` class on `<body>`. The
  class override block in base.css remaps the brand token vars to a
  brighter palette (white instead of cream, sharper gold).

Both prefs are applied at boot in `main.js`'s `applyAccessibilityPrefs()`
function. Settings page exposes them in a top-of-page Accessibility
section. Toggling in Settings re-applies immediately without a reload.

## Backup / Transfer (.sals file, v0.5.3+)

`core/backup.py` exposes `export_backup(session, include_credentials)`
and `import_backup(session, bytes)`. The file format is a ZIP archive
with these entries:

```
manifest.json          - format_version, app_version, exported_at, contents map
templates.json         - every Template + photos (paths only) + tag links
categories.json        - every Category w/ Reverb/eBay/Squarespace mappings
category_mappings.json - learned + shipped pairings
category_usage.json    - recent-used tracking
tags.json              - tag dictionary
preferences.json       - DB-stored prefs
credentials.json       - (optional) API tokens, when include_credentials=True
```

Photo files themselves are NOT bundled — only their `source_path` strings.
On the same NAS, photos reattach automatically; on a different machine
the user re-picks them via the local file dialog.

Import is destructive (wipes all user data before insert). The UI's
import modal auto-triggers a current-state export first as a safety
backup. The `BACKUP_FORMAT_VERSION` constant guards against importing
files from newer app versions than this build supports.

No encryption in v1. Future versions can add Fernet+passphrase by
appending an `encrypted.json` to the archive and gating credentials
restore on the passphrase, without breaking the file format.

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

# Tests (none yet; there's no tests/ folder, so pytest exits 5 "no tests ran")
pytest

# Run the app against your local DB
python -m listing_studio
```

The log file each run produces lives at
`%LOCALAPPDATA%\ListingStudio\logs\` — useful when a packaged build
misbehaves and you can't see stderr.

## Dev setup on macOS (Justin's Mac, rebuilt 2026-10-22)

The app ships for Dad's Windows machine. Justin develops on a Mac, which
was reformatted and set up again on 2026-10-22.

- **Python 3.12** from Homebrew (`/opt/homebrew/bin/python3.12`), the same
  version the CI build uses (`.github/workflows/build-and-release.yml`).
  macOS's own `/usr/bin/python3` is 3.9, which is below
  `requires-python = ">=3.11"`. If `brew` is missing from a new shell, run
  `eval "$(/opt/homebrew/bin/brew shellenv zsh)"`.
- **venv** lives at `.venv/` (gitignored):

  ```bash
  /opt/homebrew/bin/python3.12 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
  source .venv/bin/activate
  python -m listing_studio      # opens the window; close it to quit
  ```

- **Dependencies are unpinned** (only `>=`, no lockfile), so every fresh
  install, CI included, pulls the newest versions. On 2026-10-22 those were
  FastAPI 0.161, Starlette 1.9, SQLAlchemy 2.1, Pydantic 2.14,
  pywebview 6.2.1 and uvicorn 0.54, and the app ran on all of them. If
  something breaks after a reinstall, suspect a dependency upgrade first.
- **Where data lives on the Mac:** `~/Library/Application Support/ListingStudio/`
  holds the DB, thumbnail cache and logs.
- **Where credentials go:** the **macOS Keychain** (service `listing-studio`,
  accounts `oauth_token::<platform>` and `service::<name>`). Blobs too
  large for the Keychain fall back to `<data dir>/credentials/*.cred`.
  Never put credentials in the repo. Settings can be overridden with
  `LISTING_STUDIO_*` environment variables or a gitignored `.env` in the
  working directory. As of 2026-10-22 this Mac has no credentials stored.
  Connect platforms in the app's Settings screen when you need them.
- The NAS roots (`Z:\...`) don't exist on the Mac, so the photo picker
  falls back to the native file dialog.

### Safe smoke test (no window, no Keychain, no marketplace calls)

Point the data dir at a temp folder, swap in the null keyring, and call
local read-only routes through FastAPI's TestClient:

```bash
LISTING_STUDIO_DATA_DIR="$(mktemp -d)" PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring .venv/bin/python -c '
from fastapi.testclient import TestClient
from listing_studio.config import settings
from listing_studio.core.db import init_db
from listing_studio.core.seed import seed_sample_data_if_empty
settings.ensure_dirs(); init_db(); seed_sample_data_if_empty()
from listing_studio.ui.api import app
c = TestClient(app)
for p in ["/api/health", "/", "/api/templates", "/api/templates/1", "/api/settings/platforms", "/api/categories", "/api/fees", "/api/templates/1/ebay-preview"]:
    print(c.get(p).status_code, p)'
```

Leave out `/api/platforms/*`, `/api/ebay/*`, `/api/updates/*` and every
POST. They call Reverb, eBay, Squarespace or GitHub. A normal launch
makes one outbound call on boot: `/api/updates/check`, which reads GitHub
Releases. Launching the real app also opens a window on Justin's screen,
so use the headless test when you only need to know the backend works.

Baseline at v0.5.21 on 2026-10-22, so new breakage can be told apart from
existing problems:

- The smoke test returns 200 on every route listed above. A full launch
  loads the UI with every request returning 200.
- `ruff check .` reports 49 findings (28 auto-fixable).
  `ruff format --check .` would reformat 21 files.
- `mypy listing_studio` reports 29 errors in 9 files.

## Open items (recorded 2026-10-22, not acted on)

- **Personal email in public history.** The repo is public, and 10 of the
  38 commits carry Justin's personal Gmail as author. The rest use the
  GitHub noreply address, which is what `git config user.email` is set to
  now. Rewriting history would change every later commit hash and break
  the release tags the auto-updater depends on, so the plan is to leave it.
- **`.gitignore` gaps.** It doesn't cover `node_modules/` or `.dev.vars`
  (Cloudflare Worker secrets). Neither exists in this repo today. Add both
  if JS tooling or a Worker ever lands here. Also note that `*.spec` is
  ignored. The two spec files are already tracked, but a new one would
  need `git add -f`.
- **eBay RuName redirect docs may be wrong.** The Cloudflare Worker in
  `../ebay-deletion-notify` serves eBay's account-deletion notification
  endpoint, a `/privacy` page, and an HTTPS `/oauth/callback` bridge that
  forwards eBay's redirect to `http://localhost:8731/api/ebay/oauth/callback`.
  Its README infers that the RuName's accept URL is that Worker bridge,
  since eBay requires HTTPS. This repo still says the RuName points
  straight at localhost and never mentions the Worker: see the "eBay OAuth
  flow" section above, the RuName help text in `ui/static/js/settings.js`,
  and `platforms/ebay.py`. Only the eBay developer portal shows which URL
  is registered, so check there before changing the docs.
- **Stale branch.** `origin/feat/reverb-photo-host-imgbb` points at the
  v0.5.0 commit (`093440a`) and is fully merged into `main`: 0 commits
  ahead, 22 behind. It can be deleted on GitHub.
- **README is out of date.** It still describes the v0.1.0 scaffold ("no
  real platform APIs") and says the DB lives in `~/.listing_studio/`.
  Treat this file as the current reference.

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

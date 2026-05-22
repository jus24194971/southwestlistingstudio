# Auto-update workflow

## How it works

The app checks GitHub Releases on launch (and every 6 hours during long sessions). When a newer version is available, the user sees a banner at the top of the window:

```
↑  Update available: v0.2.1                    [Later] [Update Now]
   You're on v0.2.0 · 64.2 MB download
```

Clicking **Update Now** downloads the new .exe in the background, then prompts the user to restart. The actual restart takes 5-10 seconds.

## Your release workflow

To ship a new version:

```bash
# 1. Make changes, commit, push
git add .
git commit -m "Add Facebook copy-paste package"
git push

# 2. Bump version in listing_studio/__init__.py
#    (open the file, change __version__ = "0.1.0" to "0.2.0")
git add listing_studio/__init__.py
git commit -m "Bump version to 0.2.0"

# 3. Tag the release
git tag v0.2.0
git push --tags
```

That's it. GitHub Actions takes over from here:

1. A Windows runner spins up
2. Runs `pyinstaller listing_studio.spec`
3. Zips the result as `ListingStudio-v0.2.0-windows.zip`
4. Publishes a GitHub Release with that zip attached
5. Notifies your dad's app the next time it checks (within seconds-to-hours)

Total time from `git push --tags` to "available to users": about 5 minutes.

## First-time setup (one-time per project)

### 1. Create a GitHub repo

Go to <https://github.com/new>, create `listing-studio` (or whatever you want to call it). Public is easiest; private requires extra token plumbing.

### 2. Push your code

```bash
cd listing_studio
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOURNAME/listing-studio.git
git branch -M main
git push -u origin main
```

### 3. Update the repo path in code

In `listing_studio/core/updater.py`, change this line:

```python
GITHUB_REPO: str | None = "southwestacoustics/listing-studio"
```

to your actual repo path (e.g. `"justinhamilton/listing-studio"`). Commit and push.

### 4. Verify the Actions workflow

Visit the **Actions** tab on your GitHub repo. The workflow should appear after your first push. To test it without a real tag:

- Click "Build and Release"
- Click "Run workflow" → main → "Run workflow"
- Wait ~5 minutes
- Check the run completed successfully and an artifact was uploaded

### 5. Create your first release

```bash
git tag v0.1.0
git push --tags
```

Check the **Releases** tab on your repo. You should see "v0.1.0" with `ListingStudio-v0.1.0-windows.zip` attached. Done.

## How to verify Dad's app will pick it up

Once a release exists on GitHub:

1. Open the app on his machine (assuming it's the older version)
2. Within a few seconds, the update banner should appear at the top
3. Clicking "Update Now" downloads and installs

If the banner doesn't appear, check:

- Is `GITHUB_REPO` set correctly in `updater.py`?
- Does the release's zip asset filename end in `-windows.zip`?
- Is the current version actually older than the release tag?
- Is his network connecting to api.github.com? (test in his browser)

You can also force a check via the API: open `http://127.0.0.1:8731/api/updates/check?force=true` in his browser while the app is running.

## Rolling back a bad release

If you ship a broken version and want to revert your dad to the previous one:

1. On his machine, open `%LOCALAPPDATA%\ListingStudio\current.txt`
2. Edit it to point to the previous version's path (e.g. change `v0.2.1` to `v0.2.0` in the path)
3. Restart the app

The old version's files are still on disk in `versions/v0.2.0/` until you delete them.

For preventing the bad release from being installed by users who haven't updated yet:

- Edit the release on GitHub
- Either delete it or mark as "draft"
- New checks will see the previous release as latest

## Where things live on Dad's machine

```
C:\Users\Dad\AppData\Local\ListingStudio\
├── current.txt                 <- pointer to active install
├── versions\
│   ├── v0.1.0\
│   │   └── ListingStudio\
│   │       └── ListingStudio.exe
│   └── v0.2.0\
│       └── ListingStudio\
│           └── ListingStudio.exe
├── listing_studio.db           <- his data
├── thumbnail_cache\
└── logs\
```

The desktop shortcut points to one of the version directories. After an update, the shortcut keeps working because we don't move the old version — we just install a new one alongside and update `current.txt`.

(Note: the desktop shortcut continues pointing to whichever version was active when it was created. After an update, the *shortcut still works* but launches the *old* version. Dad's pinned-to-taskbar icon will launch the old version too. This is fixable — see "Future work" below.)

## Why the old version stays around

We keep the previous version (or two) on disk for two reasons:
1. **Rollback** in case the new version is broken
2. **Crash recovery** — if the new version fails to launch, the old one's still there

The `cleanup_old_versions(keep_count=2)` function removes anything older than the last 2. It's not called automatically right now — we can wire it into a "Maintenance" tab later, or just call it occasionally from the updater.

## Future work (when needed)

**Launcher stub.** A tiny `ListingStudio.exe` at a fixed path that reads `current.txt` and exec's the real binary. Solves the "shortcut points to old version" issue. ~50 lines of Python.

**Code signing.** A signed binary won't trigger SmartScreen. Costs ~$10/month via Microsoft Trusted Signing or ~$100/year via Sectigo etc. Not blocking — your dad clicks "Run anyway" once and it's fine forever.

**Delta updates.** Right now updates re-download the entire ~60MB app. For frequent small updates, we could use `bsdiff` to ship deltas. Not worth it until updates get tiresome to download.

**Release notes UI polish.** Currently we show the raw GitHub release body (which is markdown). We could render it nicely. Low priority.

**Update channels.** "Stable" vs "Beta" releases, so you can test pre-releases without affecting Dad. Worth doing if you have other early testers.

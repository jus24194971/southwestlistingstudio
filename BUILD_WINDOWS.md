# Building Listing Studio for Windows

## Prerequisites on Dad's machine

1. **Python 3.11 or newer.** Check with `python --version` in a Command Prompt.
   - If not installed: download from <https://www.python.org/downloads/>
   - **Critical:** during install, check "Add Python to PATH"

2. **A working command prompt or PowerShell.** Either is fine.

## One-time setup

In a Command Prompt or PowerShell, from a directory where you want the project to live:

```powershell
# Extract the scaffold zip to this location, then:
cd listing_studio

# Create a virtual environment
python -m venv .venv

# Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1

# OR activate it (Command Prompt)
.\.venv\Scripts\activate.bat

# Install dependencies
pip install -e ".[dev,windows]"

# Install PyInstaller for the build
pip install pyinstaller
```

If `Activate.ps1` complains about execution policy, run this first (one time, in PowerShell):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Test it runs from source

Before building, confirm the app works from source:

```powershell
python -m listing_studio
```

A window should open showing the Listing Studio UI. If yes, kill it and proceed to the build.

## Build the .exe

```powershell
pyinstaller listing_studio.spec
```

PyInstaller will churn for 1-3 minutes. When it's done, you'll have:

```
dist/ListingStudio/
├── ListingStudio.exe       <- The launcher
├── _internal/              <- Bundled Python + dependencies
│   ├── (lots of .dll, .pyd files)
│   ├── listing_studio/     <- Our static files, templates, assets
│   └── ...
└── (other support files)
```

## Test the built .exe

Double-click `dist/ListingStudio/ListingStudio.exe`. The app should launch identically to running it from source.

**First-launch SmartScreen warning:**
- Windows may show "Microsoft Defender SmartScreen prevented an unrecognized app from starting."
- Click "More info"
- Click "Run anyway"
- After one successful run, Windows usually remembers and won't ask again.

## What to ship

The entire `dist/ListingStudio/` folder is the app. Copy it to wherever Dad wants:
- A folder on his Desktop
- `C:\Program Files\ListingStudio\` (requires admin)
- A USB stick (for backup)

He runs the app by double-clicking `ListingStudio.exe` inside that folder.

## Creating a Desktop shortcut

Right-click `ListingStudio.exe` → Send to → Desktop (create shortcut).

That's it. He can also right-click → Pin to taskbar / Start menu if he wants.

## Data and database location

The SQLite database and stored credentials live in:
```
C:\Users\<dad's username>\AppData\Local\ListingStudio\
```

This survives reinstalls of the .exe.

## If something goes wrong during the build

Common PyInstaller issues:

**`ModuleNotFoundError` during build:** Run `pip install <module>` then rebuild.

**App opens but errors out on startup:** Open a Command Prompt, navigate to `dist/ListingStudio/`, and run `ListingStudio.exe` from there. The console output shows the real error.

**App opens but UI is blank:** WebView2 Runtime may be missing. Download from <https://developer.microsoft.com/en-us/microsoft-edge/webview2/> (the "Evergreen Bootstrapper" - tiny ~2MB installer).

**Antivirus flags the .exe:** PyInstaller binaries sometimes trigger heuristic flags. Add an exclusion or build with `console=True` in the spec to verify it's actually our code running.

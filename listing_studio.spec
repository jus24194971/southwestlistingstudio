# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Listing Studio - Windows build.
#
# Usage (from this directory, on a Windows machine with the venv activated):
#
#     pyinstaller listing_studio.spec
#
# Output:
#
#     dist/ListingStudio/ListingStudio.exe   (single-folder build, ~80 MB)
#
# After building, the entire `dist/ListingStudio/` folder is what gets shipped
# to Dad's computer. He can put it anywhere - Desktop, Program Files, a USB stick.
# Double-clicking ListingStudio.exe launches the app.
#
# Why single-folder rather than single-file (one .exe)?
#   - Faster startup (no extraction-to-temp on every launch)
#   - Easier debugging if something goes wrong (we can see what's bundled)
#   - We can hand-edit the bundled SQLite DB or static files for troubleshooting
#     without rebuilding
#
# If you want a single .exe later, change `onefile=True` in the EXE() call and
# delete the COLLECT() call.
#
# Note: This must be built ON Windows. Cross-compiling from macOS is not supported.

import sys
from pathlib import Path

# Determine the project root (this spec file's directory). When PyInstaller
# runs the spec, __file__ is not always defined, so we fall back to cwd.
try:
    PROJECT_ROOT = Path(__file__).parent.resolve()
except NameError:
    PROJECT_ROOT = Path.cwd().resolve()

PACKAGE_DIR = PROJECT_ROOT / "listing_studio"

# Static and template files need to be explicitly included since PyInstaller
# only auto-detects .py imports. Each tuple is (source, destination-in-bundle).
# Destinations use forward slashes even on Windows (PyInstaller normalizes them).
datas = [
    (str(PACKAGE_DIR / "ui" / "static"), "listing_studio/ui/static"),
    (str(PACKAGE_DIR / "ui" / "templates"), "listing_studio/ui/templates"),
    (str(PACKAGE_DIR / "assets"), "listing_studio/assets"),
]

# Hidden imports - modules PyInstaller's static analysis doesn't see because
# they're imported dynamically (e.g. via fastapi/uvicorn/sqlalchemy plugins).
hiddenimports = [
    # uvicorn loads these via string names
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # SQLAlchemy dialects
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    # Keyring backend for Windows credential storage
    "keyring.backends.Windows",
    # Email validator (sometimes needed by Pydantic)
    "email_validator",
]

# Excluded modules - we don't need these in the bundle, removing them shrinks
# the binary. PyInstaller sometimes pulls in test infrastructure or unused
# database drivers; we explicitly exclude them here.
excludes = [
    "tkinter",      # We use pywebview not tkinter
    "test",         # Standard library test suite
    "unittest",     # Unit testing framework
    "pytest",       # Pytest
    "pip",          # Pip (the bundled Python doesn't need pip)
    "setuptools",   # Setuptools
    "wheel",        # Wheel
    # Database drivers we don't use
    "psycopg2",
    "MySQLdb",
    "pymysql",
]


# -- Analysis: walks the dependency tree starting from the entry point ----

a = Analysis(
    [str(PACKAGE_DIR / "__main__.py")],   # Entry point
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# -- Executable: the actual .exe file ----------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ListingStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX compression can trigger antivirus false positives
    console=False,      # No console window - this is a GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Use the brand logo as the .exe icon. PyInstaller wants a .ico file
    # specifically on Windows; we'll need to convert the PNG. For now we
    # fall back to PyInstaller's default if the .ico isn't there.
    icon=str(PACKAGE_DIR / "assets" / "listing_studio.ico")
        if (PACKAGE_DIR / "assets" / "listing_studio.ico").exists() else None,
)

# -- Collect: bundles the executable with its dependencies into dist/ -------

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ListingStudio",
)

# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Listing Studio - macOS build.
#
# Usage (from this directory, with venv activated):
#
#     pyinstaller listing_studio_mac.spec
#
# Output:
#
#     dist/ListingStudio.app   (the .app bundle)
#
# To test: double-click dist/ListingStudio.app, or `open dist/ListingStudio.app`
# To package into a DMG: run ./build_dmg.sh (which calls this spec then packages)
#
# Notes on macOS specifics:
#   - We use BUNDLE() at the bottom to produce a .app instead of just an .exe
#   - bundle_identifier follows reverse-DNS (com.southwestacoustics.listingstudio)
#   - On first launch, Gatekeeper will say "cannot be opened because the developer
#     cannot be verified". User must right-click → Open the first time. Or in
#     System Settings → Privacy & Security → "Open Anyway".
#   - For real distribution you'd need an Apple Developer account ($99/yr) to
#     sign and notarize. Not needed for personal/dev testing.

from pathlib import Path

try:
    PROJECT_ROOT = Path(__file__).parent.resolve()
except NameError:
    PROJECT_ROOT = Path.cwd().resolve()

PACKAGE_DIR = PROJECT_ROOT / "listing_studio"

# Static and template files
datas = [
    (str(PACKAGE_DIR / "ui" / "static"), "listing_studio/ui/static"),
    (str(PACKAGE_DIR / "ui" / "templates"), "listing_studio/ui/templates"),
    (str(PACKAGE_DIR / "assets"), "listing_studio/assets"),
]

# Hidden imports - dynamically-loaded modules PyInstaller can't see
hiddenimports = [
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
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "keyring.backends.macOS",          # Native macOS Keychain backend
    "email_validator",
]

excludes = [
    "tkinter",
    "test",
    "unittest",
    "pytest",
    "pip",
    "setuptools",
    "wheel",
    "psycopg2",
    "MySQLdb",
    "pymysql",
]


a = Analysis(
    [str(PACKAGE_DIR / "__main__.py")],
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ListingStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,           # Will build for whichever arch you're on (arm64 or x86_64)
    codesign_identity=None,     # No signing for dev builds
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ListingStudio",
)

# BUNDLE wraps the COLLECT output into a proper .app bundle
app = BUNDLE(
    coll,
    name="ListingStudio.app",
    icon=str(PACKAGE_DIR / "assets" / "listing_studio.icns")
        if (PACKAGE_DIR / "assets" / "listing_studio.icns").exists() else None,
    bundle_identifier="com.southwestacoustics.listingstudio",
    version="0.1.0",
    info_plist={
        "CFBundleName": "Listing Studio",
        "CFBundleDisplayName": "Listing Studio",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        # High-DPI/Retina support
        "NSHighResolutionCapable": True,
        # Tell macOS this is a GUI app (not a CLI tool)
        "LSUIElement": False,
        # Minimum macOS version - reasonable floor for modern WebKit
        "LSMinimumSystemVersion": "11.0",
        # Optional: appears in About box
        "NSHumanReadableCopyright": "© Southwest Acoustics",
    },
)

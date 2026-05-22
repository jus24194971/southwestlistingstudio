#!/usr/bin/env bash
#
# Build a .dmg installer for Listing Studio (macOS).
#
# Usage:
#     ./build_dmg.sh
#
# Prerequisites:
#     - Active venv with pyinstaller installed:
#         source .venv/bin/activate
#         pip install pyinstaller
#     - hdiutil (built into macOS, no install needed)
#
# Output:
#     dist/ListingStudio.app   - the app bundle (testable directly)
#     dist/ListingStudio.dmg   - the disk image (for distribution)

set -e  # Exit on error

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Verify we're running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script must be run on macOS."
    echo "Current OS: $OSTYPE"
    exit 1
fi

# Verify pyinstaller is available
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: pyinstaller not found in PATH."
    echo "Activate your venv and install it:"
    echo "    source .venv/bin/activate"
    echo "    pip install pyinstaller"
    exit 1
fi

echo "============================================"
echo "Building Listing Studio for macOS"
echo "============================================"
echo

# Clean previous build artifacts
echo "[1/4] Cleaning previous build artifacts..."
rm -rf build/ dist/ListingStudio dist/ListingStudio.app dist/ListingStudio.dmg
echo "Done."
echo

# Run PyInstaller
echo "[2/4] Running PyInstaller (this takes 1-3 minutes)..."
pyinstaller listing_studio_mac.spec --clean --noconfirm
echo "Done."
echo

# Verify the .app was created
APP_PATH="dist/ListingStudio.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "Error: $APP_PATH was not created. Check PyInstaller output above."
    exit 1
fi

echo "[3/4] App bundle created at $APP_PATH"
APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
echo "      Size: $APP_SIZE"
echo

# Build the DMG using hdiutil
DMG_PATH="dist/ListingStudio.dmg"
DMG_VOLNAME="Listing Studio"
DMG_TEMP_DIR="dist/_dmg_staging"

echo "[4/4] Building DMG..."

# Create a staging directory containing the .app and a symlink to /Applications
rm -rf "$DMG_TEMP_DIR"
mkdir -p "$DMG_TEMP_DIR"
cp -R "$APP_PATH" "$DMG_TEMP_DIR/"
ln -s /Applications "$DMG_TEMP_DIR/Applications"

# hdiutil creates the DMG. Options:
#   -volname     - the volume name shown in Finder when mounted
#   -srcfolder   - the directory whose contents go into the DMG
#   -ov          - overwrite existing DMG
#   -format UDZO - compressed zlib (smaller file, slightly slower mount)
hdiutil create \
    -volname "$DMG_VOLNAME" \
    -srcfolder "$DMG_TEMP_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# Cleanup staging
rm -rf "$DMG_TEMP_DIR"

DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)
echo "Done."
echo
echo "============================================"
echo "Build complete!"
echo "============================================"
echo
echo "  App bundle:  $APP_PATH ($APP_SIZE)"
echo "  DMG:         $DMG_PATH ($DMG_SIZE)"
echo
echo "To test:"
echo "  open $APP_PATH"
echo
echo "Or open the DMG, drag ListingStudio to Applications:"
echo "  open $DMG_PATH"
echo
echo "First launch will trigger Gatekeeper since the app isn't"
echo "code-signed. Right-click the app → Open, then click Open"
echo "in the dialog. macOS remembers your choice."

"""Generate the Listing Studio app icon - SA monogram.

Renders an "SA" monogram on a deep brand-brown background with gold letters,
optionally framed by a subtle inset border at larger sizes. Output is a
Windows multi-size .ico (16/24/32/48/64/128/256) plus a preview PNG that
arranges all sizes in a grid so you can sanity-check the result before
PyInstaller bakes it into the .exe.

Usage:
    .venv/Scripts/python.exe scripts/generate_icon.py

Outputs:
    listing_studio/assets/listing_studio.ico   (consumed by listing_studio.spec)
    scripts/icon_preview.png                   (visual review only)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Brand palette - sampled from listing_studio/ui/static/css/tokens.css
BG = (27, 24, 19, 255)            # --bg-shell  #1B1813
BG_PANEL = (38, 33, 26, 255)      # --bg-panel  #26211A (subtle inner gradient)
GOLD = (214, 176, 116, 255)       # --gold-bright #D6B074
GOLD_DIM = (122, 98, 56, 255)     # --gold-dim  #7A6238

# Cambria - bundled with Windows. Two variants:
#  - Bold Italic (cambriaz.ttf): brand-aligned script feel, used at 64px+
#  - Bold upright (cambriab.ttf): legible at 16/24/32 where italic muddies
FONT_LARGE = r"C:\Windows\Fonts\cambriaz.ttf"
FONT_SMALL = r"C:\Windows\Fonts\cambriab.ttf"

# Threshold below which we switch to upright bold for legibility. Cambria
# Italic's flow is beautiful at 64+ but the A's diagonal stroke loses
# definition at 32 and below, where it can read as a plain triangle.
ITALIC_MIN_SIZE = 64

# Border only renders at 64+ — at 48 it crowds the letters; at 32 and below
# it'd be a single-pixel ring that looks like noise.
BORDER_MIN_SIZE = 64

# Windows .ico convention: include all these sizes so the OS picks the right
# one for each context (taskbar, alt-tab, Explorer thumbnail, etc.).
SIZES = [256, 128, 64, 48, 32, 24, 16]


def render_monogram(size: int) -> Image.Image:
    """Render the SA monogram at the given square size."""
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    use_italic = size >= ITALIC_MIN_SIZE
    use_border = size >= BORDER_MIN_SIZE

    # Subtle inner panel tone + gold-dim border for that "coin / seal" feel.
    # Only at the large sizes where there's room.
    if use_border:
        inset = max(2, size // 32)
        draw.rectangle(
            [(inset, inset), (size - inset - 1, size - inset - 1)],
            fill=BG_PANEL,
        )
        ring_w = max(1, size // 96)
        draw.rectangle(
            [(inset, inset), (size - inset - 1, size - inset - 1)],
            outline=GOLD_DIM,
            width=ring_w,
        )

    # Letter rendering. Italic vs upright + size differ:
    #   - Italic at 64+: letters take ~58% of canvas (italic letters have
    #     more visual weight; smaller font_size keeps them from crowding the
    #     border).
    #   - Upright at 48: drop the border, give letters ~70% so they read big.
    #   - Upright at 32/24/16: max out at ~78% for max legibility.
    if use_italic:
        font_size = int(size * 0.58)
        font_path = FONT_LARGE
    elif size >= 48:
        font_size = int(size * 0.70)
        font_path = FONT_SMALL
    else:
        font_size = int(size * 0.78)
        font_path = FONT_SMALL
    font = ImageFont.truetype(font_path, font_size)

    text = "SA"
    bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Center, compensating for the bbox's top-left offset
    x = (size - text_w) / 2 - bbox[0]
    # Optical center is slightly above geometric center for capital letters;
    # nudge up by 4%
    y = (size - text_h) / 2 - bbox[1] - int(size * 0.04)

    draw.text((x, y), text, fill=GOLD, font=font)
    return img


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    assets_dir = repo_root / "listing_studio" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    ico_path = assets_dir / "listing_studio.ico"
    preview_path = Path(__file__).resolve().parent / "icon_preview.png"

    images = [render_monogram(s) for s in SIZES]

    # Multi-size .ico - Pillow embeds all the sizes from the source image's
    # `sizes` argument. Note that ICO max per-frame is 256px.
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Wrote {ico_path} ({ico_path.stat().st_size:,} bytes)")

    # Preview: arrange all sizes in one strip so a human can eyeball them.
    # Largest on the left, smallest on the right, with a label below each.
    padding = 20
    label_h = 24
    strip_w = sum(s for s in SIZES) + padding * (len(SIZES) + 1)
    strip_h = max(SIZES) + padding * 2 + label_h
    strip = Image.new("RGBA", (strip_w, strip_h), (10, 8, 6, 255))
    draw = ImageDraw.Draw(strip)
    label_font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 12)

    x = padding
    for s, img in zip(SIZES, images):
        # Vertically center each icon in the strip's image area
        y = padding + (max(SIZES) - s) // 2
        strip.paste(img, (x, y), img)
        # Label below
        label = f"{s}px"
        lbbox = draw.textbbox((0, 0), label, font=label_font)
        lw = lbbox[2] - lbbox[0]
        draw.text(
            (x + (s - lw) // 2, max(SIZES) + padding + 4),
            label,
            fill=(180, 180, 170, 255),
            font=label_font,
        )
        x += s + padding

    strip.save(preview_path, "PNG")
    print(f"Wrote {preview_path}")


if __name__ == "__main__":
    main()

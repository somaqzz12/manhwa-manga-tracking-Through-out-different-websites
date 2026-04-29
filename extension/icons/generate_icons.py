"""One-off script to generate the four extension icon PNGs from a single
indigo-gradient design that matches the Manga Watchlist web favicon palette.

Run from the repo root:

    python extension/icons/generate_icons.py

Outputs icon-16.png, icon-32.png, icon-48.png, and icon-128.png next to this
script. Re-run after tweaking the colors below if the brand evolves.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Brand palette — matches the popup logo gradient in popup.html.
TOP_COLOR = (96, 165, 250)     # #60A5FA
MID_COLOR = (37, 99, 235)      # #2563EB
BOTTOM_COLOR = (79, 70, 229)   # #4F46E5
GLYPH_COLOR = (255, 255, 255, 235)
SHADOW_COLOR = (15, 23, 42, 110)

SIZES = [16, 32, 48, 128]
OUTPUT_DIR = Path(__file__).resolve().parent


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _draw_gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), MID_COLOR)
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        # Two-stop linear gradient: TOP → MID at the midpoint, MID → BOTTOM after.
        if t <= 0.5:
            color = _lerp(TOP_COLOR, MID_COLOR, t * 2)
        else:
            color = _lerp(MID_COLOR, BOTTOM_COLOR, (t - 0.5) * 2)
        for x in range(size):
            px[x, y] = color
    return img


def _rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    radius = max(1, round(size * radius_ratio))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def _draw_bookmark_glyph(size: int) -> Image.Image:
    """Stylized bookmark + chapter-mark on a transparent layer."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Bookmark body — a vertical strip with a notched bottom.
    pad_x = round(size * 0.30)
    top = round(size * 0.20)
    bottom = round(size * 0.80)
    left = pad_x
    right = size - pad_x
    notch = round(size * 0.10)
    mid_x = (left + right) // 2

    bookmark = [
        (left, top),
        (right, top),
        (right, bottom),
        (mid_x, bottom - notch),
        (left, bottom),
    ]
    draw.polygon(bookmark, fill=GLYPH_COLOR)

    # Subtle inner "page" line at smaller sizes only when we have pixels to
    # spare; below 24px it just becomes muddy.
    if size >= 32:
        line_top = round(top + size * 0.18)
        line_left = round(left + size * 0.10)
        line_right = round(right - size * 0.10)
        draw.line(
            (line_left, line_top, line_right, line_top),
            fill=(255, 255, 255, 90),
            width=max(1, size // 32),
        )
    return layer


def render(size: int) -> Image.Image:
    base = _draw_gradient(size).convert("RGBA")
    mask = _rounded_mask(size)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(base, (0, 0), mask)

    glyph = _draw_bookmark_glyph(size)
    if size >= 48:
        shadow = glyph.copy()
        shadow_alpha = shadow.split()[-1].point(lambda v: min(120, v))
        shadow.putalpha(shadow_alpha)
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, size // 32)))
        offset = max(1, size // 32)
        canvas.alpha_composite(shadow, (0, offset))
    canvas.alpha_composite(glyph)
    return canvas


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        img = render(s)
        out = OUTPUT_DIR / f"icon-{s}.png"
        img.save(out, format="PNG", optimize=True)
        print(f"wrote {out} ({s}x{s})")


if __name__ == "__main__":
    main()

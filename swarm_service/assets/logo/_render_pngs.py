"""Render the Swarm-Forge mark to PNG at multiple sizes from the SVG geometry.

Run from repo root:  py assets/logo/_render_pngs.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent / "png"
OUT_DIR.mkdir(exist_ok=True)

# SVG geometry (viewBox -100..100). Apex closer to centre, wings flared back.
CHEVRON = [(0.0, -25.0), (-22.0, -65.0), (0.0, -50.0), (22.0, -65.0)]
DOT_RADIUS = 7.0

IRON_BLACK = (14, 14, 18, 255)
PURE_WHITE = (255, 255, 255, 255)
EMBER = (230, 96, 58, 255)
TRANSPARENT = (0, 0, 0, 0)


def _rotate(p: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    x, y = p
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)


def render_mark(size: int, chevron_color: tuple, dot_color: tuple) -> Image.Image:
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    draw = ImageDraw.Draw(img)
    scale = size / 200.0
    cx, cy = size / 2.0, size / 2.0

    for i in range(6):
        angle = i * 60.0
        pts = [_rotate(p, angle) for p in CHEVRON]
        screen_pts = [(cx + x * scale, cy + y * scale) for x, y in pts]
        draw.polygon(screen_pts, fill=chevron_color)

    r = DOT_RADIUS * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dot_color)
    return img


def main() -> None:
    sizes = [256, 512, 1024, 2048]
    variants = {
        "black": (IRON_BLACK, IRON_BLACK),
        "white": (PURE_WHITE, PURE_WHITE),
        "ember": (IRON_BLACK, EMBER),
    }
    for variant, (chev, dot) in variants.items():
        for size in sizes:
            img = render_mark(size, chev, dot)
            out = OUT_DIR / f"swarm-forge-mark-{variant}-{size}.png"
            img.save(out, format="PNG", optimize=True)
            print(f"  wrote {out.relative_to(OUT_DIR.parent.parent.parent)}  ({size}x{size})")


if __name__ == "__main__":
    main()

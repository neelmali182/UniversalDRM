"""Visible watermarking — burns text into pixel data server-side (§14.1).

Refactored from ``universal_drm.watermark`` with improvements:
- Random session-based offset per call (defeats averaging/cropping attacks)
- Separate opacity control
- Angle is now a parameter
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFont


def burn_visible(
    image: Image.Image,
    text: str,
    opacity: float = 0.20,
    angle: float = 30.0,
    session_offset_seed: int | None = None,
) -> Image.Image:
    """Return an RGB copy of *image* with *text* tiled diagonally across it.

    The watermark is burned into the pixel data server-side so it:
    - Survives screenshots
    - Cannot be removed by editing the DOM or CSS
    - Is part of every tile that leaves the server

    Args:
        image: Source PIL image.
        text: Watermark text (e.g. verified recipient email + session id).
        opacity: Alpha of the watermark layer (0.0–1.0).
        angle: Rotation angle in degrees.
        session_offset_seed: Seed for per-session random offset (defeats
            averaging multiple screenshots to cancel the watermark). If None
            the offset is non-deterministic.

    Returns:
        A new RGB :class:`~PIL.Image.Image` with the watermark burned in.
    """
    rng = random.Random(session_offset_seed)
    base = image.convert("RGBA")
    w, h = base.size
    size = max(14, w // 42)
    font = ImageFont.load_default(size=size)
    left, top, right, bottom = font.getbbox(text)
    tw, th = right - left, bottom - top
    step_x = tw + size * 4
    step_y = th + size * 5

    # Draw on a square large enough to cover the page after rotation
    side = int(math.hypot(w, h)) + step_x
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fill = (128, 128, 128, int(255 * opacity))

    # Random per-session offset so that averaging multiple copies does not
    # cancel the watermark (§14.1 "randomized offsets per session")
    rand_x = rng.randint(0, step_x)
    rand_y = rng.randint(0, step_y)

    for row, y in enumerate(range(-rand_y, side, step_y)):
        offset = (step_x // 2) * (row % 2)
        for x in range(-step_x + offset - rand_x, side, step_x):
            draw.text((x, y), text, font=font, fill=fill)

    layer = layer.rotate(angle, resample=Image.BICUBIC)
    cx, cy = (side - w) // 2, (side - h) // 2
    layer = layer.crop((cx, cy, cx + w, cy + h))
    return Image.alpha_composite(base, layer).convert("RGB")


# Backwards-compatible alias for existing code that calls burn()
burn = burn_visible

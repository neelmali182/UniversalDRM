"""Tiled, diagonal watermarks burned into the pixels of a page image."""
import math
from PIL import Image, ImageDraw, ImageFont


def burn(image, text, opacity=0.2, angle=30):
    """Return an RGB copy of ``image`` with ``text`` tiled across it.

    The text is part of the pixels, so it survives screenshots, saving the image
    and editing the page in developer tools. Mid-grey is readable on both light
    and dark content.
    """
    base = image.convert("RGBA")
    w, h = base.size
    size = max(14, w // 42)
    font = ImageFont.load_default(size=size)
    left, top, right, bottom = font.getbbox(text)
    tw, th = right - left, bottom - top
    step_x, step_y = tw + size * 4, th + size * 5

    # Draw on a square that still covers the page after rotation, then crop the middle.
    side = int(math.hypot(w, h)) + step_x
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fill = (128, 128, 128, int(255 * opacity))
    for row, y in enumerate(range(0, side, step_y)):
        offset = (step_x // 2) * (row % 2)
        for x in range(-step_x + offset, side, step_x):
            draw.text((x, y), text, font=font, fill=fill)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    cx, cy = (side - w) // 2, (side - h) // 2
    layer = layer.crop((cx, cy, cx + w, cy + h))
    return Image.alpha_composite(base, layer).convert("RGB")

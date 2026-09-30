"""Image renderer — strips metadata, limits resolution, burns watermark (§13.2)."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

from packages.watermark.visible import burn_visible

IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})

_DEFAULT_MAX_SIDE = 2000
_DEFAULT_JPEG_QUALITY = 82


class ImageRenderer:
    """Validate → strip metadata → viewport-based tile → burn watermark (§13.2).

    Full-resolution originals are never exposed. EXIF/GPS metadata is
    stripped via :meth:`PIL.ImageOps.exif_transpose`.

    Args:
        max_side: Maximum pixel dimension for any side after downscaling.
        jpeg_quality: JPEG quality (1–95).
        max_pixels: Decompression-bomb protection limit (default 100 MP).
    """

    def __init__(
        self,
        max_side: int = _DEFAULT_MAX_SIDE,
        jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
        max_pixels: int = 100_000_000,
    ) -> None:
        self.max_side = max_side
        self.jpeg_quality = jpeg_quality
        Image.MAX_IMAGE_PIXELS = max_pixels  # Pillow decompression-bomb guard

    def page_count(self, path: str, mime: str) -> int:
        """Always 1 for images (single frame returned)."""
        if mime not in IMAGE_MIMES:
            raise ValueError(f"ImageRenderer cannot handle MIME type: {mime!r}")
        return 1

    def render_page(self, path: str, mime: str, index: int, watermark: str) -> bytes:
        """Return JPEG bytes for image at *path* with watermark burned in.

        Raises:
            IndexError: If *index* != 0.
            ValueError: If *mime* is not a supported image MIME type.
        """
        if mime not in IMAGE_MIMES:
            raise ValueError(f"ImageRenderer cannot handle MIME type: {mime!r}")
        if index != 0:
            raise IndexError(index)
        img = self._load_and_prepare(path)
        watermarked = burn_visible(img, watermark)
        out = BytesIO()
        watermarked.save(out, "JPEG", quality=self.jpeg_quality, optimize=True)
        return out.getvalue()

    def _load_and_prepare(self, path: str) -> Image.Image:
        """Open image, strip EXIF, flatten alpha, and downscale."""
        with Image.open(path) as src:
            try:
                src.seek(0)  # First frame of animated GIF/WebP
            except EOFError:
                pass
            # Strip EXIF (including GPS) via orientation-aware transpose
            img = ImageOps.exif_transpose(src)
            # Flatten transparency to white background
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                flat = Image.new("RGB", img.size, "white")
                flat.paste(img, mask=img.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            img.thumbnail((self.max_side, self.max_side))
            return img

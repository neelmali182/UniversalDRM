"""PDF renderer — rasterizes PDF pages into watermarked JPEG tiles (§13.1)."""
from __future__ import annotations

import threading
from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image

from packages.watermark.visible import burn_visible

# PDFium is not thread-safe; serialize access with a module-level lock
_pdfium_lock = threading.Lock()

_DEFAULT_MAX_SIDE = 2000
_DEFAULT_PDF_SCALE = 2.0
_DEFAULT_JPEG_QUALITY = 82


class PDFRenderer:
    """Server-side PDF rasterizer (§13.1 — default tile mode).

    Pages are rasterized in memory, watermarked, and returned as JPEG bytes.
    The original PDF is never sent to the browser.

    Args:
        max_side: Maximum pixel dimension for any side of a rendered page.
        pdf_scale: Render scale factor (higher = sharper, larger).
        jpeg_quality: JPEG quality (1–95).
    """

    def __init__(
        self,
        max_side: int = _DEFAULT_MAX_SIDE,
        pdf_scale: float = _DEFAULT_PDF_SCALE,
        jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
    ) -> None:
        self.max_side = max_side
        self.pdf_scale = pdf_scale
        self.jpeg_quality = jpeg_quality

    def page_count(self, path: str, mime: str) -> int:
        """Return the number of pages in the PDF at *path*."""
        if mime != "application/pdf":
            raise ValueError(f"PDFRenderer cannot handle MIME type: {mime!r}")
        with _pdfium_lock:
            doc = pdfium.PdfDocument(path)
            try:
                return len(doc)
            finally:
                doc.close()

    def render_page(self, path: str, mime: str, index: int, watermark: str | None = None) -> bytes:
        """Return JPEG bytes for page *index* (0-based) with watermark burned in if provided.

        Raises:
            IndexError: If *index* is out of range.
            ValueError: If *mime* is not application/pdf.
        """
        if mime != "application/pdf":
            raise ValueError(f"PDFRenderer cannot handle MIME type: {mime!r}")
        page_image = self._rasterize(path, index)
        out = BytesIO()
        if watermark:
            watermarked = burn_visible(page_image, watermark)
            watermarked.save(out, "JPEG", quality=self.jpeg_quality, optimize=True)
        else:
            page_image.save(out, "JPEG", quality=self.jpeg_quality, optimize=True)
        return out.getvalue()

    def _rasterize(self, path: str, index: int) -> Image.Image:
        with _pdfium_lock:
            doc = pdfium.PdfDocument(path)
            try:
                if not 0 <= index < len(doc):
                    raise IndexError(index)
                page = doc[index]
                w, h = page.get_size()
                scale = min(self.pdf_scale, self.max_side / max(w, h))
                return page.render(scale=scale).to_pil().convert("RGB")
            finally:
                doc.close()

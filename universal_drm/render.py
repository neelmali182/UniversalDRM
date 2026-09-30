"""Turn PDFs, images and text files into watermarked page images.

The browser only ever receives these JPEGs, never the original file, so there is
no PDF to save, no image to right-click and no text to copy.
"""
import textwrap
import threading
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pypdfium2 as pdfium
from .watermark import burn

IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PAGE_MIMES = IMAGE_MIMES | {"application/pdf", "text/plain"}

# PDFium is not thread-safe, and threaded servers such as Waitress call it concurrently.
_pdfium_lock = threading.Lock()


def kind(mime):
    """'pages' for content rendered to page images, 'video' for streamed video, else None."""
    if mime in PAGE_MIMES:
        return "pages"
    if mime.startswith("video/"):
        return "video"
    return None


class Renderer:
    def __init__(self, max_side=2000, pdf_scale=2.0, jpeg_quality=82, text_lines_per_page=56, text_chars_per_line=92):
        self.max_side = max_side
        self.pdf_scale = pdf_scale
        self.jpeg_quality = jpeg_quality
        self.text_lines_per_page = text_lines_per_page
        self.text_chars_per_line = text_chars_per_line

    def page_count(self, path, mime):
        if mime == "application/pdf":
            with _pdfium_lock:
                doc = pdfium.PdfDocument(path)
                try:
                    return len(doc)
                finally:
                    doc.close()
        if mime == "text/plain":
            return max(1, -(-len(self._text_lines(path)) // self.text_lines_per_page))
        if mime in IMAGE_MIMES:
            return 1
        raise ValueError(f"Cannot render {mime} as pages")

    def render_page(self, path, mime, index, watermark):
        """JPEG bytes of page ``index`` (0-based) with ``watermark`` burned in. Raises IndexError past the last page."""
        if mime == "application/pdf":
            page = self._pdf_page(path, index)
        elif mime == "text/plain":
            page = self._text_page(path, index)
        elif mime in IMAGE_MIMES:
            if index != 0:
                raise IndexError(index)
            page = self._image(path)
        else:
            raise ValueError(f"Cannot render {mime} as pages")
        out = BytesIO()
        burn(page, watermark).save(out, "JPEG", quality=self.jpeg_quality, optimize=True)
        return out.getvalue()

    def _pdf_page(self, path, index):
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

    def _image(self, path):
        with Image.open(path) as src:
            src.seek(0)  # first frame of an animated GIF or WebP
            img = ImageOps.exif_transpose(src)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                flat = Image.new("RGB", img.size, "white")
                flat.paste(img, mask=img.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            img.thumbnail((self.max_side, self.max_side))
            return img

    def _text_lines(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read().expandtabs(4).splitlines() or [""]
        lines = []
        for line in raw:
            lines.extend(textwrap.wrap(line, self.text_chars_per_line, replace_whitespace=False, drop_whitespace=False) or [""])
        return lines

    def _text_page(self, path, index):
        lines = self._text_lines(path)
        start = index * self.text_lines_per_page
        if index < 0 or (start >= len(lines) and index != 0):
            raise IndexError(index)
        # A4 at 150 dpi
        page = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(page)
        font = ImageFont.load_default(size=22)
        y = 80
        for line in lines[start:start + self.text_lines_per_page]:
            draw.text((80, y), line, font=font, fill=(20, 20, 20))
            y += 28
        return page

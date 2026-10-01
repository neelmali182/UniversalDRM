from io import BytesIO
import pytest
from PIL import Image
import pypdfium2 as pdfium
from universal_drm import Renderer, burn, kind, static_dir
import os


@pytest.fixture
def renderer():
    return Renderer(max_side=800)


def jpeg(data):
    img = Image.open(BytesIO(data))
    assert img.format == "JPEG"
    return img


def test_kind():
    assert kind("application/pdf") == "pages"
    assert kind("image/png") == "pages"
    assert kind("text/plain") == "pages"
    assert kind("video/mp4") == "video"
    assert kind("application/zip") is None


def test_burn_changes_pixels_and_keeps_size():
    page = Image.new("RGB", (600, 400), "white")
    marked = burn(page, "alice@example.test · #1a2b3c")
    assert marked.size == page.size
    assert marked.getextrema() != page.getextrema()


def test_burn_is_visible_on_dark_content():
    page = Image.new("RGB", (600, 400), "black")
    assert burn(page, "watermark").getextrema() != page.getextrema()


def test_pdf_pages(tmp_path, renderer):
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(595, 842)
    pdf.new_page(842, 595)
    path = tmp_path / "doc.pdf"
    pdf.save(str(path))
    pdf.close()
    assert renderer.page_count(str(path), "application/pdf") == 2
    first = jpeg(renderer.render_page(str(path), "application/pdf", 0, "wm"))
    second = jpeg(renderer.render_page(str(path), "application/pdf", 1, "wm"))
    assert max(first.size) <= 800 and first.height > first.width
    assert second.width > second.height
    with pytest.raises(IndexError):
        renderer.render_page(str(path), "application/pdf", 2, "wm")


def test_image_is_downscaled_and_flattened(tmp_path, renderer):
    path = tmp_path / "pic.png"
    Image.new("RGBA", (3000, 1500), (255, 0, 0, 0)).save(path)
    assert renderer.page_count(str(path), "image/png") == 1
    img = jpeg(renderer.render_page(str(path), "image/png", 0, "wm"))
    assert img.size == (800, 400)
    with pytest.raises(IndexError):
        renderer.render_page(str(path), "image/png", 1, "wm")


def test_text_is_paginated(tmp_path):
    renderer = Renderer(text_lines_per_page=10)
    path = tmp_path / "notes.txt"
    path.write_text("\n".join(f"line {i}" for i in range(25)), encoding="utf-8")
    assert renderer.page_count(str(path), "text/plain") == 3
    jpeg(renderer.render_page(str(path), "text/plain", 2, "wm"))
    with pytest.raises(IndexError):
        renderer.render_page(str(path), "text/plain", 3, "wm")


def test_empty_text_file_has_one_page(tmp_path, renderer):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert renderer.page_count(str(path), "text/plain") == 1
    jpeg(renderer.render_page(str(path), "text/plain", 0, "wm"))


def test_unsupported_type(tmp_path, renderer):
    with pytest.raises(ValueError):
        renderer.page_count(str(tmp_path / "x.zip"), "application/zip")


def test_static_assets_ship_with_package():
    assert os.path.isfile(os.path.join(static_dir(), "universal-drm.js"))
    assert os.path.isfile(os.path.join(static_dir(), "universal-drm.css"))


def test_render_page_clean_without_watermark(tmp_path, renderer):
    path = tmp_path / "doc.txt"
    path.write_text("Hello Clean World", encoding="utf-8")
    clean_bytes = renderer.render_page(str(path), "text/plain", 0, watermark=None)
    clean_img = jpeg(clean_bytes)
    assert clean_img.size == (1240, 1754)
    # Rendering with watermark changes the pixels compared to clean
    watermarked_bytes = renderer.render_page(str(path), "text/plain", 0, watermark="Confidential")
    assert clean_bytes != watermarked_bytes


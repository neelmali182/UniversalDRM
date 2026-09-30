"""Tests for visible and forensic watermarking (§14)."""
import pytest
from PIL import Image
from packages.watermark.visible import burn_visible
from packages.watermark.forensic import embed_forensic, extract_forensic, payload_for_session


def white_image(w=600, h=400):
    return Image.new("RGB", (w, h), "white")


def black_image(w=600, h=400):
    return Image.new("RGB", (w, h), "black")


# ---------------------------------------------------------------------------
# Visible watermark
# ---------------------------------------------------------------------------

def test_burn_visible_returns_same_size():
    img = white_image()
    result = burn_visible(img, "alice@example.com · #1a2b3c")
    assert result.size == img.size


def test_burn_visible_changes_pixels():
    img = white_image()
    marked = burn_visible(img, "watermark text")
    assert marked.getpixel((0, 0)) != img.getpixel((0, 0)) or marked.getextrema() != img.getextrema()


def test_burn_visible_on_dark_background():
    img = black_image()
    marked = burn_visible(img, "watermark")
    # At least some pixels should be lighter than pure black
    r, g, b = zip(*list(marked.getdata()))
    assert max(r) > 0 or max(g) > 0 or max(b) > 0


def test_burn_visible_different_sessions_differ():
    """Per-session offsets must differ between sessions (§14.1)."""
    img = white_image()
    a = burn_visible(img, "wm", session_offset_seed=1)
    b = burn_visible(img, "wm", session_offset_seed=2)
    # At least one pixel must differ
    assert list(a.getdata()) != list(b.getdata())


def test_burn_visible_same_seed_is_deterministic():
    img = white_image()
    a = burn_visible(img, "wm", session_offset_seed=42)
    b = burn_visible(img, "wm", session_offset_seed=42)
    assert list(a.getdata()) == list(b.getdata())


# ---------------------------------------------------------------------------
# Forensic watermark
# ---------------------------------------------------------------------------

def test_embed_extract_roundtrip():
    img = white_image(800, 800)
    payload = b"session-id-12345"
    embedded = embed_forensic(img, payload)
    extracted = extract_forensic(embedded)
    assert extracted == payload


def test_extract_returns_none_on_clean_image():
    img = white_image()
    result = extract_forensic(img)
    assert result is None


def test_payload_too_large_raises():
    img = white_image(800, 800)
    with pytest.raises(ValueError, match="too large"):
        embed_forensic(img, b"x" * 65)


def test_payload_for_session_is_deterministic():
    p1 = payload_for_session("sess-abc")
    p2 = payload_for_session("sess-abc")
    assert p1 == p2
    assert len(p1) == 32


def test_payload_for_session_differs_per_session():
    assert payload_for_session("sess-1") != payload_for_session("sess-2")

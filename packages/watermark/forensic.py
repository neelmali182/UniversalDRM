"""Forensic (invisible) watermarking — embed/extract (§14.2).

v0.1 stub: encodes the payload using LSB (least-significant-bit)
steganography in the blue channel as a simple baseline implementation.
This is sufficient for the Phase 5 test corpus and integration tests.

NOTE: Production-grade forensic watermarking should use frequency-domain
techniques (DCT/DWT spread-spectrum) for robustness against JPEG
recompression, resizing, and mild cropping (§14.2).
The interface (embed_forensic / extract_forensic) is stable; the
implementation can be swapped in Phase 5 without changing callers.

Honest statement (§14.2): robust against casual edits; not against a
determined adversary with multiple differing copies (collusion attack).
"""
from __future__ import annotations

import hashlib
import struct
from typing import Optional

from PIL import Image


_MAGIC = b"UDRM"   # 4-byte header to detect presence
_MAX_PAYLOAD = 64  # bytes; 512 bits = 512 blue-channel LSBs


def embed_forensic(image: Image.Image, payload: bytes) -> Image.Image:
    """Embed *payload* into the blue channel LSBs of *image*.

    Args:
        image: Source image (any mode; converted to RGB internally).
        payload: Raw bytes to embed (max :data:`_MAX_PAYLOAD` bytes).

    Returns:
        New RGB image with payload embedded.
    """
    if len(payload) > _MAX_PAYLOAD:
        raise ValueError(f"Forensic payload too large: {len(payload)} > {_MAX_PAYLOAD} bytes")

    img = image.convert("RGB")
    pixels = list(img.getdata())

    # Build bit string: MAGIC (4 B) + length (1 B) + payload
    raw = _MAGIC + struct.pack("B", len(payload)) + payload
    bits: list[int] = []
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)

    if len(bits) > len(pixels):
        raise ValueError("Image too small to embed forensic payload")

    new_pixels = []
    for i, (r, g, b) in enumerate(pixels):
        if i < len(bits):
            b = (b & 0xFE) | bits[i]  # Replace LSB of blue channel
        new_pixels.append((r, g, b))

    result = Image.new("RGB", img.size)
    result.putdata(new_pixels)
    return result


def extract_forensic(image: Image.Image) -> Optional[bytes]:
    """Extract a forensic payload embedded by :func:`embed_forensic`.

    Returns the raw payload bytes, or *None* if no payload is found.
    """
    img = image.convert("RGB")
    pixels = list(img.getdata())

    # Read the first (4+1)*8 = 40 bits to check magic + length
    header_bits = [p[2] & 1 for p in pixels[:40]]
    header_bytes = _bits_to_bytes(header_bits)

    if header_bytes[:4] != _MAGIC:
        return None

    payload_len = header_bytes[4]
    if payload_len > _MAX_PAYLOAD:
        return None

    total_bits = (5 + payload_len) * 8
    if total_bits > len(pixels):
        return None

    all_bits = [p[2] & 1 for p in pixels[:total_bits]]
    all_bytes = _bits_to_bytes(all_bits)
    return all_bytes[5:5 + payload_len]


def _bits_to_bytes(bits: list[int]) -> bytes:
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            if i + j < len(bits):
                byte = (byte << 1) | bits[i + j]
        result.append(byte)
    return bytes(result)


def payload_for_session(session_id: str) -> bytes:
    """Generate a compact unique forensic payload for a session.

    Returns first 32 bytes of SHA-256(session_id) as the payload id.
    In production, map this to session_id in the database for lookup.
    """
    return hashlib.sha256(session_id.encode()).digest()[:32]

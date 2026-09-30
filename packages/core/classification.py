"""Content classification utilities (§8.2).

Classification uses magic bytes / MIME — never the filename extension.
"""
from __future__ import annotations

from .enums import ContentFormat, ContentType, ProtectionEngine

# Mapping from normalized MIME type to (ContentType, ContentFormat, ProtectionEngine)
_MIME_MAP: dict[str, tuple[ContentType, ContentFormat, ProtectionEngine]] = {
    "application/pdf": (ContentType.DOCUMENT, ContentFormat.PDF, ProtectionEngine.DOCUMENT),
    "application/vnd.ms-powerpoint": (ContentType.DOCUMENT, ContentFormat.PPT, ProtectionEngine.DOCUMENT),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        ContentType.DOCUMENT, ContentFormat.PPT, ProtectionEngine.DOCUMENT,
    ),
    "application/msword": (ContentType.DOCUMENT, ContentFormat.DOC, ProtectionEngine.DOCUMENT),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        ContentType.DOCUMENT, ContentFormat.DOC, ProtectionEngine.DOCUMENT,
    ),
    "image/png": (ContentType.IMAGE, ContentFormat.PNG, ProtectionEngine.DOCUMENT),
    "image/jpeg": (ContentType.IMAGE, ContentFormat.JPEG, ProtectionEngine.DOCUMENT),
    "image/gif": (ContentType.IMAGE, ContentFormat.GIF, ProtectionEngine.DOCUMENT),
    "image/webp": (ContentType.IMAGE, ContentFormat.WEBP, ProtectionEngine.DOCUMENT),
}

_VIDEO_MIMES = frozenset({
    "video/mp4", "video/webm", "video/ogg", "video/x-matroska",
    "video/quicktime", "video/x-msvideo",
})

_AUDIO_MIMES = frozenset({
    "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm", "audio/aac",
})


def classify(mime_type: str) -> tuple[ContentType, ContentFormat, ProtectionEngine]:
    """Return (ContentType, ContentFormat, ProtectionEngine) for *mime_type*.

    Uses the MIME type (derived from magic bytes, not the filename extension).
    """
    normalized = mime_type.lower().split(";")[0].strip()
    if normalized in _MIME_MAP:
        return _MIME_MAP[normalized]
    if normalized in _VIDEO_MIMES:
        return ContentType.MEDIA, ContentFormat.VIDEO, ProtectionEngine.MEDIA
    if normalized in _AUDIO_MIMES:
        return ContentType.MEDIA, ContentFormat.AUDIO, ProtectionEngine.MEDIA
    return ContentType.FILE, ContentFormat.UNKNOWN, ProtectionEngine.FILE


def is_renderable(mime_type: str) -> bool:
    """True if content can be server-rendered to page tiles (v0.1 scope)."""
    ct, _, engine = classify(mime_type)
    return engine == ProtectionEngine.DOCUMENT

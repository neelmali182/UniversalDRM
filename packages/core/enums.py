"""Core enumerations for UniversalDRM domain."""
from enum import Enum


class AssetStatus(str, Enum):
    """Lifecycle status of an asset (§8.1)."""
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROTECTED = "PROTECTED"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


class ContentType(str, Enum):
    """High-level content classification (§8.2)."""
    DOCUMENT = "document"
    MEDIA = "media"
    IMAGE = "image"
    FILE = "file"


class ContentFormat(str, Enum):
    """Specific file format (§8.2)."""
    PDF = "pdf"
    PPT = "ppt"
    DOC = "doc"
    PNG = "png"
    JPEG = "jpeg"
    GIF = "gif"
    WEBP = "webp"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


class ProtectionEngine(str, Enum):
    """Protection engine used for a content type (§1.2)."""
    DOCUMENT = "document"
    MEDIA = "media"
    FILE = "file"


class SessionStatus(str, Enum):
    """Viewer session lifecycle status (§9.4)."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class JobState(str, Enum):
    """Background job state (§21.1)."""
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    """Background job types (§21.1)."""
    RENDER_PDF = "RENDER_PDF"
    CONVERT_PPT = "CONVERT_PPT"
    CONVERT_DOC = "CONVERT_DOC"
    EXTRACT_METADATA = "EXTRACT_METADATA"
    TRANSCODE_VIDEO = "TRANSCODE_VIDEO"
    PACKAGE_MEDIA = "PACKAGE_MEDIA"
    ENCRYPT_ASSET = "ENCRYPT_ASSET"
    REKEY = "REKEY"
    DELETE_ASSET = "DELETE_ASSET"
    MALWARE_SCAN = "MALWARE_SCAN"


class EnforcementClass(str, Enum):
    """Policy field enforcement class (§2.3).

    Used to tag every policy capability so developers understand
    what is server-enforced versus best-effort deterrence.
    """
    ENFORCED = "enforced"
    BEST_EFFORT = "best_effort"
    TRACEABILITY = "traceability"


class AuditEventType(str, Enum):
    """Audit event catalog (§17.1).

    NOTE: event names use *_ATTEMPT for deterrence controls,
    never *_PREVENTED — the system does not claim prevention.
    """
    ASSET_CREATED = "ASSET_CREATED"
    ASSET_UPLOADED = "ASSET_UPLOADED"
    ASSET_PROTECTED = "ASSET_PROTECTED"
    ASSET_DELETED = "ASSET_DELETED"
    SHARE_CREATED = "SHARE_CREATED"
    SHARE_OPENED = "SHARE_OPENED"
    SHARE_REVOKED = "SHARE_REVOKED"
    RECIPIENT_VERIFIED = "RECIPIENT_VERIFIED"
    RECIPIENT_VERIFY_FAILED = "RECIPIENT_VERIFY_FAILED"
    VIEWER_STARTED = "VIEWER_STARTED"
    VIEWER_HEARTBEAT = "VIEWER_HEARTBEAT"
    VIEWER_EXPIRED = "VIEWER_EXPIRED"
    VIEWER_REVOKED = "VIEWER_REVOKED"
    # Deterrence attempts — these are detected, NOT prevented
    COPY_ATTEMPT = "COPY_ATTEMPT"
    PRINT_ATTEMPT = "PRINT_ATTEMPT"
    DOWNLOAD_ATTEMPT = "DOWNLOAD_ATTEMPT"
    FOCUS_LOST = "FOCUS_LOST"
    # Enforced denials
    POLICY_DENIED = "POLICY_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    # DRM
    DRM_LICENSE_REQUEST = "DRM_LICENSE_REQUEST"
    DRM_LICENSE_DENIED = "DRM_LICENSE_DENIED"
    # Anti-abuse
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    WATERMARK_TRACE_LOOKUP = "WATERMARK_TRACE_LOOKUP"

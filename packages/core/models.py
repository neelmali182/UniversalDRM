"""Core domain models for UniversalDRM.

These are plain dataclasses / typed dicts used across packages.
They intentionally do not depend on any ORM or external library
so they can be used in workers, SDK, and tests without pulling
in the full API stack.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .enums import (
    AssetStatus,
    ContentFormat,
    ContentType,
    JobState,
    JobType,
    ProtectionEngine,
    SessionStatus,
    AuditEventType,
)


def _now() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Organization:
    """Tenant record (§18)."""
    id: str = field(default_factory=_uuid)
    name: str = ""
    kek_ref: str = ""          # Reference/alias used by the KeyProvider
    created_at: datetime = field(default_factory=_now)


@dataclass
class Asset:
    """Uploaded content unit (§8.1, §18)."""
    id: str = field(default_factory=_uuid)
    organization_id: str = ""
    name: str = ""
    mime_type: str = ""
    size: int = 0
    content_type: ContentType = ContentType.FILE
    content_format: ContentFormat = ContentFormat.UNKNOWN
    engine: ProtectionEngine = ProtectionEngine.FILE
    status: AssetStatus = AssetStatus.UPLOADING
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class AssetVersion:
    """Immutable encrypted version of an asset (§18)."""
    id: str = field(default_factory=_uuid)
    asset_id: str = ""
    version: int = 1
    storage_key: str = ""      # Key in object storage
    wrapped_dek: bytes = b""   # DEK wrapped by tenant KEK (§12.1)
    kek_version: str = ""
    checksum: str = ""         # SHA-256 of plaintext
    page_count: int = 0
    created_at: datetime = field(default_factory=_now)


@dataclass
class ProtectionPolicy:
    """Immutable policy version (§10.3)."""
    id: str = field(default_factory=_uuid)
    asset_id: str = ""
    version: int = 1
    policy_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


@dataclass
class Share:
    """An identity-bound, expiring share link (§9, §18)."""
    id: str = field(default_factory=_uuid)
    asset_id: str = ""
    organization_id: str = ""
    token_hash: str = ""       # Hash only — token never stored in plaintext
    policy_version: int = 1
    recipients_json: list[str] = field(default_factory=list)
    identity_mode: str = "otp" # "otp" | "oidc" | "open"
    expires_at: Optional[datetime] = None
    one_time: bool = False
    consumed_at: Optional[datetime] = None
    revoked: bool = False
    created_at: datetime = field(default_factory=_now)


@dataclass
class RecipientVerification:
    """OTP verification record (§9.2, §18)."""
    id: str = field(default_factory=_uuid)
    share_id: str = ""
    email: str = ""
    otp_hash: str = ""
    attempts: int = 0
    expires_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None


@dataclass
class ViewerSession:
    """Active viewer session (§9.4, §18)."""
    id: str = field(default_factory=_uuid)
    asset_id: str = ""
    share_id: str = ""
    organization_id: str = ""
    verified_email: str = ""
    device_secret_hash: str = ""
    policy_version: int = 1
    watermark_payload: bytes = b""
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None
    last_seen: datetime = field(default_factory=_now)


@dataclass
class AuditEvent:
    """Append-only audit record (§17, §18)."""
    id: str = field(default_factory=_uuid)
    organization_id: str = ""
    asset_id: str = ""
    user_id: str = ""
    session_id: str = ""
    event_type: AuditEventType = AuditEventType.ASSET_CREATED
    metadata: dict[str, Any] = field(default_factory=dict)
    ip: str = ""
    user_agent: str = ""
    prev_hash: str = ""        # Hash chaining for tamper evidence (§17.2)
    created_at: datetime = field(default_factory=_now)


@dataclass
class Job:
    """Background processing job (§21.1)."""
    id: str = field(default_factory=_uuid)
    organization_id: str = ""
    asset_id: str = ""
    type: JobType = JobType.ENCRYPT_ASSET
    state: JobState = JobState.QUEUED
    attempts: int = 0
    error: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

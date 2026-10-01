"""Audit event models for UniversalDRM (§17)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from packages.core.enums import AuditEventType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class AuditRecord:
    """A single audit log entry (§17.1, §17.2).

    IMPORTANT: event_type names use *_ATTEMPT for deterrence controls —
    we detect the attempt, we do NOT claim we prevented it (§17.1 rule).
    """
    id: str = field(default_factory=_uuid)
    organization_id: str = ""
    asset_id: str = ""
    user_id: str = ""
    session_id: str = ""
    event_type: AuditEventType = AuditEventType.ASSET_CREATED
    metadata: dict[str, Any] = field(default_factory=dict)
    ip: str = ""
    user_agent: str = ""
    prev_hash: str = ""
    created_at: datetime = field(default_factory=_now)

    def compute_hash(self) -> str:
        """SHA-256 of deterministic record fields for hash chaining (§17.2)."""
        canonical = (
            f"{self.id}|{self.organization_id}|{self.asset_id}|{self.session_id}"
            f"|{self.event_type}|{self.created_at.isoformat()}|{self.prev_hash}"
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

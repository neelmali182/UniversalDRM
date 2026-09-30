"""Audit sink implementations for UniversalDRM (§17)."""
from __future__ import annotations

import json
import sys
from typing import Any

from .models import AuditRecord


class StdoutAuditSink:
    """Writes audit events as JSON lines to stdout (dev/debug)."""

    def emit(self, event: AuditRecord) -> None:
        record = {
            "id": event.id,
            "organization_id": event.organization_id,
            "asset_id": event.asset_id,
            "session_id": event.session_id,
            "event_type": event.event_type,
            "metadata": event.metadata,
            "ip": event.ip,
            "created_at": event.created_at.isoformat(),
        }
        print(json.dumps(record), file=sys.stdout, flush=True)


class DatabaseAuditSink:
    """Writes audit events to a database repository (stub).

    Replace the ``repository`` with a real async DB session or repository
    pattern implementation when wiring up the FastAPI app.
    """

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def emit(self, event: AuditRecord) -> None:
        self._repo.insert(event)

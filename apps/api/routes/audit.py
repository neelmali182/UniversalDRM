"""Audit routes — query audit events (§19, §17)."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from ..security import require_api_key

router = APIRouter(tags=["audit"], dependencies=[Depends(require_api_key)])


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    organization_id: str
    asset_id: str
    session_id: str
    metadata: dict[str, Any]
    ip: str
    created_at: datetime


class AuditListResponse(BaseModel):
    events: list[AuditEventOut]
    cursor: Optional[str] = None


# In-memory stub — replace with async DB query
_audit_log: list[dict] = []


def _paginate(events: list[dict[str, Any]], limit: int, cursor: str | None) -> AuditListResponse:
    offset = 0
    if cursor:
        try:
            padding = "=" * (-len(cursor) % 4)
            offset = int(base64.urlsafe_b64decode(cursor + padding).decode("ascii"))
            if offset < 0:
                raise ValueError
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise HTTPException(status_code=400, detail="Invalid audit cursor") from exc

    page = [AuditEventOut(**e) for e in events[offset:offset + limit]]
    next_offset = offset + len(page)
    next_cursor = None
    if next_offset < len(events):
        next_cursor = base64.urlsafe_b64encode(str(next_offset).encode("ascii")).decode("ascii").rstrip("=")
    return AuditListResponse(events=page, cursor=next_cursor)


@router.get(
    "/assets/{asset_id}/audit",
    response_model=AuditListResponse,
    summary="Query audit events for an asset",
)
async def get_asset_audit(
    asset_id: str,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
):
    """Return audit events for *asset_id* (cursor-paginated, §19)."""
    events = [e for e in _audit_log if e["asset_id"] == asset_id]
    return _paginate(events, limit, cursor)


@router.get(
    "/sessions/{session_id}/audit",
    response_model=AuditListResponse,
    summary="Query audit events for a session",
)
async def get_session_audit(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
):
    """Return audit events for *session_id*."""
    events = [e for e in _audit_log if e.get("session_id") == session_id]
    return _paginate(events, limit, cursor)


@router.post(
    "/forensics/trace",
    summary="Trace a leaked image to its source session (§17.1)",
)
async def forensics_trace():
    """Upload a leaked image and extract the forensic watermark payload.

    Returns the session and recipient that were watermarked into the image.
    Full implementation deferred to Phase 5 (§25).
    """
    raise HTTPException(status_code=501, detail="Forensic watermark embedding and session lookup are not configured")

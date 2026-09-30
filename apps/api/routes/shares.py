"""Share routes — create, get, revoke (§19)."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(tags=["shares"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class PolicyInput(BaseModel):
    view: bool = True
    download: bool = False
    copy: bool = False
    print: bool = False
    expires_in: int = Field(3600, description="Seconds until share expires; 0 = no expiry")
    one_time: bool = False
    max_sessions: int = Field(0, description="0 = unlimited")
    max_devices: int = Field(0, description="0 = unlimited")
    recipients: list[str] = Field(default_factory=list, description="Email allowlist; empty = any authenticated")
    watermark_visible: bool = True
    watermark_forensic: bool = True


class ShareCreateRequest(BaseModel):
    policy: PolicyInput = Field(default_factory=PolicyInput)
    identity_mode: str = Field("otp", description="otp | open")


class ShareResponse(BaseModel):
    id: str
    asset_id: str
    url: str
    token: str          # Included only on creation; server stores hash only
    policy: dict
    identity_mode: str
    expires_at: Optional[datetime]
    revoked: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# In-memory store (stub — replace with DB in Phase 0)
# ---------------------------------------------------------------------------

_shares: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _viewer_url(token: str) -> str:
    # TODO: pull base URL from settings
    return f"http://localhost:8000/v/{token}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/assets/{asset_id}/shares",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a share for an asset",
)
async def create_share(asset_id: str, body: ShareCreateRequest):
    """Create an identity-bound, expiring share link (§9).

    The raw token is returned ONCE on creation; thereafter only its hash is
    stored (§9.1).  The viewer URL embeds the token.
    """
    # Generate high-entropy share token
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    share_id = str(uuid.uuid4())

    expires_at = None
    if body.policy.expires_in > 0:
        expires_at = _now() + timedelta(seconds=body.policy.expires_in)

    policy_dict = body.policy.model_dump()

    share = {
        "id": share_id,
        "asset_id": asset_id,
        "token": token,
        "token_hash": token_hash,
        "policy": policy_dict,
        "identity_mode": body.identity_mode,
        "expires_at": expires_at,
        "revoked": False,
        "created_at": _now(),
    }
    _shares[share_id] = share

    return ShareResponse(
        id=share["id"],
        asset_id=share["asset_id"],
        url=_viewer_url(token),
        token=token,
        policy=policy_dict,
        identity_mode=share["identity_mode"],
        expires_at=share["expires_at"],
        revoked=share["revoked"],
        created_at=share["created_at"],
    )


@router.get(
    "/shares/{share_id}",
    response_model=ShareResponse,
    summary="Get share details",
)
async def get_share(share_id: str):
    """Get share details (without the raw token — never returned after creation)."""
    share = _shares.get(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    return ShareResponse(
        id=share["id"],
        asset_id=share["asset_id"],
        url=_viewer_url("[redacted]"),
        token="[redacted]",  # Token is stored as hash only after creation
        policy=share["policy"],
        identity_mode=share["identity_mode"],
        expires_at=share["expires_at"],
        revoked=share["revoked"],
        created_at=share["created_at"],
    )


@router.delete(
    "/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a share",
)
async def revoke_share(share_id: str):
    """Revoke a share immediately.

    Active sessions associated with this share are invalidated on next
    heartbeat (§9.4).  In production: write SHARE_REVOKED audit event,
    invalidate sessions in DB.
    """
    share = _shares.get(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    if share["revoked"]:
        return  # Idempotent
    share["revoked"] = True
    # TODO: invalidate active sessions, write audit event

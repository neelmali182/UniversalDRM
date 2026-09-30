"""Viewer routes — OTP verify, sessions, heartbeat, tile delivery (§19, §15)."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/viewer", tags=["viewer"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# In-memory stores (stubs)
# ---------------------------------------------------------------------------

_verifications: dict[str, dict] = {}
_sessions: dict[str, dict] = {}
_page_counts: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class VerifyStartRequest(BaseModel):
    share_token: str
    email: str


class VerifyStartResponse(BaseModel):
    verification_id: str
    message: str = "OTP sent to your email address"


class VerifyConfirmRequest(BaseModel):
    verification_id: str
    otp: str


class VerifyConfirmResponse(BaseModel):
    verified: bool
    share_token: str


class SessionCreateRequest(BaseModel):
    share_token: str
    verification_id: str


class SessionResponse(BaseModel):
    session_id: str
    asset_id: str
    expires_at: Optional[datetime]
    policy: dict
    watermark_text: str
    # enforcement_classes tells the client what is enforced vs best_effort
    enforcement_classes: dict = Field(
        default_factory=lambda: {
            "view": "enforced",
            "download": "enforced",
            "copy": "best_effort",
            "print": "best_effort",
            "selection": "best_effort",
            "watermark": "traceability",
        }
    )


class HeartbeatResponse(BaseModel):
    active: bool
    expires_at: Optional[datetime]
    revoked: bool = False


# ---------------------------------------------------------------------------
# Routes (§19 — Recipient and viewer)
# ---------------------------------------------------------------------------

@router.post(
    "/verify/start",
    response_model=VerifyStartResponse,
    summary="Send OTP to recipient",
)
async def verify_start(body: VerifyStartRequest):
    """Send an OTP to the recipient's email address (§9.2).

    The share token is validated against the recipient allowlist.
    The landing page (GET /v/{token}) NEVER consumes the link — only
    this endpoint initiates the identity challenge (§9.3).
    """
    # TODO: look up share by token hash, validate allowlist
    # TODO: send real OTP email via MailHog/SendGrid

    # Development stub: OTP is always "123456"
    otp = "123456"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    verification_id = str(uuid.uuid4())

    _verifications[verification_id] = {
        "id": verification_id,
        "email": body.email,
        "share_token": body.share_token,
        "otp_hash": otp_hash,
        "attempts": 0,
        "expires_at": _now() + timedelta(seconds=600),
        "verified": False,
    }

    return VerifyStartResponse(verification_id=verification_id)


@router.post(
    "/verify/confirm",
    response_model=VerifyConfirmResponse,
    summary="Confirm OTP and verify identity",
)
async def verify_confirm(body: VerifyConfirmRequest):
    """Verify the OTP submitted by the recipient (§9.2).

    Enforced: attempt limits, expiry.  After confirmation the caller
    must POST /viewer/sessions to create a session.
    """
    verification = _verifications.get(body.verification_id)
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")
    if verification["verified"]:
        raise HTTPException(status_code=409, detail="Already verified")
    if verification["expires_at"] < _now():
        raise HTTPException(status_code=400, detail="OTP expired")

    # Brute-force protection: max 5 attempts
    verification["attempts"] += 1
    if verification["attempts"] > 5:
        raise HTTPException(status_code=429, detail="Too many OTP attempts")

    expected = verification["otp_hash"]
    submitted = hashlib.sha256(body.otp.encode()).hexdigest()
    if submitted != expected:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    verification["verified"] = True
    return VerifyConfirmResponse(verified=True, share_token=verification["share_token"])


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create viewer session (§9.4)",
)
async def create_session(body: SessionCreateRequest, response: Response):
    """Create a viewer session after identity verification.

    This is the step that consumes a one-time link (§9.3 — never on GET).
    The device secret is set as an httpOnly cookie bound to this session.
    """
    verification = _verifications.get(body.verification_id)
    if not verification or not verification["verified"]:
        raise HTTPException(status_code=403, detail="Identity not verified")

    session_id = str(uuid.uuid4())
    device_secret = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=600)

    session = {
        "id": session_id,
        "asset_id": "stub-asset-id",  # TODO: resolve from share
        "share_token": body.share_token,
        "verified_email": verification["email"],
        "device_secret_hash": hashlib.sha256(device_secret.encode()).hexdigest(),
        "expires_at": expires_at,
        "status": "active",
        "policy": {
            "enforced": {"view": True, "download": False},
            "best_effort": {"copy": False, "print": False, "selection": False},
            "traceability": {"watermark": {"visible": True, "forensic": True}},
        },
    }
    _sessions[session_id] = session

    # Set device secret as httpOnly, SameSite=Strict cookie (§9.5)
    response.set_cookie(
        key="udrm_device",
        value=device_secret,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=600,
    )

    return SessionResponse(
        session_id=session_id,
        asset_id=session["asset_id"],
        expires_at=expires_at,
        policy=session["policy"],
        watermark_text=f"{verification['email']} · {session_id[:8]}",
    )


@router.post(
    "/sessions/{session_id}/heartbeat",
    response_model=HeartbeatResponse,
    summary="Session heartbeat",
)
async def session_heartbeat(session_id: str):
    """Heartbeat — returns session liveness (§9.4).

    The viewer calls this every 15–30 s.  On active=False, the viewer
    must tear down content immediately.
    """
    session = _sessions.get(session_id)
    if not session:
        return HeartbeatResponse(active=False, expires_at=None, revoked=True)

    now = _now()
    if session["expires_at"] < now:
        session["status"] = "expired"
        return HeartbeatResponse(active=False, expires_at=session["expires_at"])

    if session["status"] != "active":
        return HeartbeatResponse(active=False, expires_at=session["expires_at"])

    session["last_seen"] = now
    return HeartbeatResponse(active=True, expires_at=session["expires_at"])


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End viewer session",
)
async def end_session(session_id: str):
    """Explicitly end a viewer session (§9.4)."""
    session = _sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

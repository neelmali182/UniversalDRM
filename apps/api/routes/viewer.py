"""Viewer routes — OTP verify, sessions, heartbeat, tile delivery (§19, §15)."""
from __future__ import annotations

import hashlib
import hmac
import asyncio
import smtplib
import ssl
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from apps.api.config import settings
from .assets import _assets, _storage
from .shares import _shares
import universal_drm

router = APIRouter(prefix="/viewer", tags=["viewer"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _send_otp_email(email: str, otp: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your UniversalDRM verification code"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"Your verification code is {otp}. It expires in 10 minutes.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def _authorized_session(session_id: str, device_secret: str | None) -> tuple[dict, dict, dict]:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not device_secret or not hmac.compare_digest(
        session["device_secret_hash"], hashlib.sha256(device_secret.encode()).hexdigest()
    ):
        raise HTTPException(status_code=403, detail="Invalid device secret")
    now = _now()
    if session["expires_at"] <= now:
        session["status"] = "expired"
        raise HTTPException(status_code=410, detail="Session expired")
    if session["status"] != "active":
        raise HTTPException(status_code=410, detail="Session is not active")
    share = _shares.get(session["share_id"])
    if not share or share["revoked"] or (share["expires_at"] and share["expires_at"] <= now):
        session["status"] = "revoked"
        raise HTTPException(status_code=410, detail="Share was revoked or expired")
    asset = _assets.get(session["asset_id"])
    if not asset or not _storage.exists(asset["storage_key"]):
        raise HTTPException(status_code=404, detail="Asset content not found")
    return session, share, asset


# ---------------------------------------------------------------------------
# In-memory stores (stubs)
# ---------------------------------------------------------------------------

_verifications: dict[str, dict] = {}
_sessions: dict[str, dict] = {}
_page_counts: dict[str, int] = {}
_otp_start_attempts: dict[str, list[datetime]] = {}
_renderer = universal_drm.Renderer()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class VerifyStartRequest(BaseModel):
    share_token: str
    email: str


class VerifyStartResponse(BaseModel):
    verification_id: str
    message: str = "OTP sent to your email address"
    development_otp: Optional[str] = None


class VerifyConfirmRequest(BaseModel):
    verification_id: str
    otp: str


class VerifyConfirmResponse(BaseModel):
    verified: bool


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
async def verify_start(body: VerifyStartRequest, request: Request):
    """Send an OTP to the recipient's email address (§9.2).

    The share token is validated against the recipient allowlist.
    The landing page (GET /v/{token}) NEVER consumes the link — only
    this endpoint initiates the identity challenge (§9.3).
    """
    token_hash = hashlib.sha256(body.share_token.encode()).hexdigest()
    share = next(
        (item for item in _shares.values() if hmac.compare_digest(item["token_hash"], token_hash)),
        None,
    )
    if not share or share["revoked"]:
        raise HTTPException(status_code=404, detail="Share not found or revoked")
    if share["expires_at"] and share["expires_at"] <= _now():
        raise HTTPException(status_code=410, detail="Share expired")
    recipients = [email.strip().casefold() for email in share["policy"].get("recipients", [])]
    email = body.email.strip().casefold()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    if recipients and email not in recipients:
        raise HTTPException(status_code=403, detail="Email is not an allowed recipient")

    cutoff = _now() - timedelta(minutes=10)
    client_host = request.client.host if request.client else "unknown"
    throttle_key = hashlib.sha256(f"{client_host}:{email}".encode()).hexdigest()
    attempts = [when for when in _otp_start_attempts.get(throttle_key, []) if when > cutoff]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many verification codes requested")
    attempts.append(_now())
    _otp_start_attempts[throttle_key] = attempts

    otp = f"{secrets.randbelow(1_000_000):06d}"
    if not settings.is_development:
        try:
            await asyncio.to_thread(_send_otp_email, email, otp)
        except (OSError, smtplib.SMTPException) as exc:
            raise HTTPException(status_code=503, detail="OTP email delivery failed") from exc
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    verification_id = str(uuid.uuid4())

    _verifications[verification_id] = {
        "id": verification_id,
        "email": email,
        "share_id": share["id"],
        "share_token_hash": token_hash,
        "otp_hash": otp_hash,
        "attempts": 0,
        "expires_at": _now() + timedelta(seconds=settings.otp_ttl),
        "verified": False,
    }

    return VerifyStartResponse(
        verification_id=verification_id,
        message=("Development OTP generated" if settings.is_development else "OTP sent to recipient"),
        development_otp=otp if settings.is_development else None,
    )


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
    if verification["expires_at"] <= _now():
        raise HTTPException(status_code=400, detail="OTP expired")

    # Brute-force protection: max 5 attempts
    if verification["attempts"] >= 5:
        raise HTTPException(status_code=429, detail="Too many OTP attempts")
    verification["attempts"] += 1

    expected = verification["otp_hash"]
    submitted = hashlib.sha256(body.otp.encode()).hexdigest()
    if not hmac.compare_digest(submitted, expected):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    verification["verified"] = True
    return VerifyConfirmResponse(verified=True)


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
    if verification.get("session_created"):
        raise HTTPException(status_code=409, detail="Verification has already created a session")

    token_hash = hashlib.sha256(body.share_token.encode()).hexdigest()
    if not hmac.compare_digest(verification["share_token_hash"], token_hash):
        raise HTTPException(status_code=403, detail="Verification is bound to a different share")
    share = _shares.get(verification["share_id"])
    if not share or share["revoked"]:
        raise HTTPException(status_code=404, detail="Share not found or revoked")
    if not share["policy"].get("view", True):
        raise HTTPException(status_code=403, detail="Viewing is disabled for this share")
    if share["expires_at"] and share["expires_at"] <= _now():
        raise HTTPException(status_code=410, detail="Share expired")
    if share["policy"].get("one_time") and share["consumed"]:
        raise HTTPException(status_code=409, detail="One-time share has already been consumed")
    asset = _assets.get(share["asset_id"])
    if not asset:
        raise HTTPException(status_code=404, detail="Shared asset not found")

    active_sessions = [
        session for session in _sessions.values()
        if session["share_id"] == share["id"]
        and session["status"] == "active"
        and session["expires_at"] > _now()
    ]
    max_sessions = share["policy"].get("max_sessions", 0)
    max_devices = share["policy"].get("max_devices", 0)
    if max_sessions and share.get("session_count", 0) >= max_sessions:
        raise HTTPException(status_code=409, detail="Share session limit reached")
    if max_devices and len(active_sessions) >= max_devices:
        raise HTTPException(status_code=409, detail="Share device limit reached")

    session_id = str(uuid.uuid4())
    device_secret = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=settings.session_ttl)
    if share["expires_at"]:
        expires_at = min(expires_at, share["expires_at"])

    session = {
        "id": session_id,
        "asset_id": asset["id"],
        "share_id": share["id"],
        "verified_email": verification["email"],
        "device_secret_hash": hashlib.sha256(device_secret.encode()).hexdigest(),
        "expires_at": expires_at,
        "status": "active",
        "policy": share["policy"],
    }
    _sessions[session_id] = session

    # Set device secret as httpOnly, SameSite=Strict cookie (§9.5)
    response.set_cookie(
        key="udrm_device",
        value=device_secret,
        httponly=True,
        secure=not settings.is_development,
        samesite="strict",
        max_age=max(1, int((expires_at - _now()).total_seconds())),
    )
    verification["session_created"] = True
    if share["policy"].get("one_time"):
        share["consumed"] = True
    share["session_count"] = share.get("session_count", 0) + 1

    return SessionResponse(
        session_id=session_id,
        asset_id=session["asset_id"],
        expires_at=expires_at,
        policy={
            "enforced": {"view": session["policy"].get("view", True), "download": False},
            "best_effort": {
                "copy": session["policy"].get("copy", False),
                "print": session["policy"].get("print", False),
                "selection": False,
            },
            "traceability": {"watermark": {
                "visible": session["policy"].get("watermark_visible", True),
                "forensic": session["policy"].get("watermark_forensic", True),
            }},
        },
        watermark_text=f"{verification['email']} · {session_id[:8]}",
    )


@router.post(
    "/sessions/{session_id}/heartbeat",
    response_model=HeartbeatResponse,
    summary="Session heartbeat",
)
async def session_heartbeat(
    session_id: str,
    device_secret: str | None = Cookie(default=None, alias="udrm_device"),
):
    """Heartbeat — returns session liveness (§9.4).

    The viewer calls this every 15–30 s.  On active=False, the viewer
    must tear down content immediately.
    """
    session = _sessions.get(session_id)
    if not session:
        return HeartbeatResponse(active=False, expires_at=None, revoked=True)
    if not device_secret or not hmac.compare_digest(
        session["device_secret_hash"], hashlib.sha256(device_secret.encode()).hexdigest()
    ):
        return HeartbeatResponse(active=False, expires_at=None, revoked=True)

    share = _shares.get(session["share_id"])
    if not share or share["revoked"] or (share["expires_at"] and share["expires_at"] <= _now()):
        session["status"] = "revoked"
        return HeartbeatResponse(active=False, expires_at=session["expires_at"], revoked=True)

    now = _now()
    if session["expires_at"] < now:
        session["status"] = "expired"
        return HeartbeatResponse(active=False, expires_at=session["expires_at"])

    if session["status"] != "active":
        return HeartbeatResponse(active=False, expires_at=session["expires_at"])

    session["last_seen"] = now
    return HeartbeatResponse(active=True, expires_at=session["expires_at"])


@router.get(
    "/sessions/{session_id}/heartbeat",
    response_model=HeartbeatResponse,
    summary="Check viewer session liveness",
)
async def session_status(
    session_id: str,
    device_secret: str | None = Cookie(default=None, alias="udrm_device"),
):
    return await session_heartbeat(session_id, device_secret)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End viewer session",
)
async def end_session(
    session_id: str,
    device_secret: str | None = Cookie(default=None, alias="udrm_device"),
):
    """Explicitly end a viewer session (§9.4)."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not device_secret or not hmac.compare_digest(
        session["device_secret_hash"], hashlib.sha256(device_secret.encode()).hexdigest()
    ):
        raise HTTPException(status_code=403, detail="Invalid device secret")
    session["status"] = "revoked"


@router.get("/sessions/{session_id}/content", summary="Get authorized document viewer metadata")
async def session_content(
    session_id: str,
    response: Response,
    device_secret: str | None = Cookie(default=None, alias="udrm_device"),
):
    _, share, asset = _authorized_session(session_id, device_secret)
    if universal_drm.kind(asset["mime_type"]) != "pages":
        raise HTTPException(status_code=415, detail="This asset type is not rendered as pages")
    try:
        pages = _renderer.page_count(str(_storage.path_for(asset["storage_key"])), asset["mime_type"])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Stored asset could not be rendered") from exc
    response.headers["Cache-Control"] = "no-store"
    return {
        "kind": "pages",
        "pages": pages,
        "mime_type": asset["mime_type"],
        "watermark_visible": share["policy"].get("watermark_visible", True),
    }


@router.get("/sessions/{session_id}/pages/{page_index}", summary="Get an authorized rendered page")
async def session_page(
    session_id: str,
    page_index: int,
    device_secret: str | None = Cookie(default=None, alias="udrm_device"),
):
    from fastapi.responses import Response as RawResponse

    session, _, asset = _authorized_session(session_id, device_secret)
    if not session["policy"].get("view", True):
        raise HTTPException(status_code=403, detail="Viewing is disabled for this share")
    now = _now()
    page_times = [when for when in session.setdefault("page_access_times", []) if when > now - timedelta(minutes=1)]
    max_per_minute = session["policy"].get("pages_per_minute", 20)
    max_total = session["policy"].get("max_pages_total", 200)
    if max_per_minute and len(page_times) >= max_per_minute:
        raise HTTPException(status_code=429, detail="Page request rate limit reached")
    if max_total and session.get("pages_total", 0) >= max_total:
        raise HTTPException(status_code=429, detail="Page request limit reached")
    try:
        data = _renderer.render_page(
            str(_storage.path_for(asset["storage_key"])), asset["mime_type"], page_index, watermark=None
        )
    except IndexError as exc:
        raise HTTPException(status_code=404, detail="Page not found") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Stored asset could not be rendered") from exc
    page_times.append(now)
    session["page_access_times"] = page_times
    session["pages_total"] = session.get("pages_total", 0) + 1
    return RawResponse(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

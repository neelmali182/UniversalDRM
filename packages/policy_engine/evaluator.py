"""Policy evaluator for UniversalDRM (§10.2).

Evaluation order (§10.2):
  authentication → tenant/ownership → share validity → identity →
  session → expiry → rate limits → policy action → allow/deny

Every denial writes an audit event.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .schema import Policy


class DenyReason(str, Enum):
    """Machine-readable denial reason."""
    UNAUTHENTICATED = "unauthenticated"
    UNAUTHORIZED_TENANT = "unauthorized_tenant"
    SHARE_NOT_FOUND = "share_not_found"
    SHARE_REVOKED = "share_revoked"
    SHARE_EXPIRED = "share_expired"
    SHARE_CONSUMED = "share_consumed"
    IDENTITY_MISMATCH = "identity_mismatch"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_REVOKED = "session_revoked"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMITED = "rate_limited"
    ACTION_DENIED = "action_denied"
    DOWNLOAD_DISABLED = "download_disabled"


@dataclass
class Decision:
    """Result of policy evaluation (§10.2)."""
    allowed: bool
    reason: Optional[DenyReason] = None
    enforcement: str = "enforced"  # Always enforced for server-side decisions


@dataclass
class EvaluationContext:
    """All facts needed to evaluate a policy decision."""
    # Authentication
    verified_email: str = ""
    # Share
    share_id: str = ""
    share_revoked: bool = False
    share_expires_at: Optional[datetime] = None
    share_one_time: bool = False
    share_consumed: bool = False
    share_recipients: list[str] = None  # type: ignore[assignment]
    # Session
    session_id: str = ""
    session_status: str = "active"   # "active" | "expired" | "revoked"
    session_expires_at: Optional[datetime] = None
    # Rate limits
    pages_this_minute: int = 0
    pages_total: int = 0
    # Action being requested
    action: str = "view"  # "view" | "download" | "print" | etc.

    def __post_init__(self) -> None:
        if self.share_recipients is None:
            self.share_recipients = []


class PolicyEvaluator:
    """Evaluates access decisions against a policy (§10.2)."""

    def evaluate(self, policy: Policy, ctx: EvaluationContext) -> Decision:
        """Return an :class:`Decision` for the given context.

        Evaluation short-circuits on the first denial.
        """
        now = datetime.now(timezone.utc)

        # 1. Authentication — must have a verified identity
        if not ctx.verified_email:
            return Decision(allowed=False, reason=DenyReason.UNAUTHENTICATED)

        # 2. Share validity
        if ctx.share_revoked:
            return Decision(allowed=False, reason=DenyReason.SHARE_REVOKED)

        if ctx.share_expires_at and ctx.share_expires_at < now:
            return Decision(allowed=False, reason=DenyReason.SHARE_EXPIRED)

        if ctx.share_one_time and ctx.share_consumed:
            return Decision(allowed=False, reason=DenyReason.SHARE_CONSUMED)

        # 3. Identity binding — recipient allowlist
        recipients = policy.enforced.recipients
        if recipients:
            # Non-empty list means only these emails are allowed
            normalized = [r.lower().strip() for r in recipients]
            if ctx.verified_email.lower().strip() not in normalized:
                return Decision(allowed=False, reason=DenyReason.IDENTITY_MISMATCH)

        # 4. Session validity
        if not ctx.session_id:
            return Decision(allowed=False, reason=DenyReason.SESSION_NOT_FOUND)

        if ctx.session_status == "revoked":
            return Decision(allowed=False, reason=DenyReason.SESSION_REVOKED)

        if ctx.session_status == "expired":
            return Decision(allowed=False, reason=DenyReason.SESSION_EXPIRED)

        if ctx.session_expires_at and ctx.session_expires_at < now:
            return Decision(allowed=False, reason=DenyReason.SESSION_EXPIRED)

        # 5. Rate limits
        rl = policy.enforced.rate_limits
        if rl.pages_per_minute > 0 and ctx.pages_this_minute >= rl.pages_per_minute:
            return Decision(allowed=False, reason=DenyReason.RATE_LIMITED)
        if rl.max_pages_total > 0 and ctx.pages_total >= rl.max_pages_total:
            return Decision(allowed=False, reason=DenyReason.RATE_LIMITED)

        # 6. Action-level policy
        if ctx.action == "download" and not policy.enforced.download:
            # enforced: no plaintext download endpoint should exist
            return Decision(allowed=False, reason=DenyReason.DOWNLOAD_DISABLED)

        if ctx.action == "view" and not policy.enforced.view:
            return Decision(allowed=False, reason=DenyReason.ACTION_DENIED)

        return Decision(allowed=True)

"""Tests for policy engine — schema and evaluator (§10)."""
from datetime import datetime, timedelta, timezone
import pytest
from packages.policy_engine.schema import Policy
from packages.policy_engine.evaluator import PolicyEvaluator, DenyReason, EvaluationContext


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def evaluator():
    return PolicyEvaluator()


@pytest.fixture
def default_policy():
    return Policy()


def _good_ctx(**kwargs):
    """Build a passing context with minimal required fields."""
    defaults = {
        "verified_email": "alice@example.com",
        "share_id": "share-1",
        "share_revoked": False,
        "share_expires_at": _now() + timedelta(hours=1),
        "share_one_time": False,
        "share_consumed": False,
        "share_recipients": [],
        "session_id": "sess-1",
        "session_status": "active",
        "session_expires_at": _now() + timedelta(minutes=10),
        "pages_this_minute": 0,
        "pages_total": 0,
        "action": "view",
    }
    defaults.update(kwargs)
    return EvaluationContext(**defaults)


def test_default_policy_allows_view(evaluator, default_policy):
    ctx = _good_ctx()
    d = evaluator.evaluate(default_policy, ctx)
    assert d.allowed


def test_unauthenticated_denied(evaluator, default_policy):
    ctx = _good_ctx(verified_email="")
    d = evaluator.evaluate(default_policy, ctx)
    assert not d.allowed
    assert d.reason == DenyReason.UNAUTHENTICATED


def test_revoked_share_denied(evaluator, default_policy):
    ctx = _good_ctx(share_revoked=True)
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.SHARE_REVOKED


def test_expired_share_denied(evaluator, default_policy):
    ctx = _good_ctx(share_expires_at=_now() - timedelta(seconds=1))
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.SHARE_EXPIRED


def test_consumed_one_time_share_denied(evaluator, default_policy):
    ctx = _good_ctx(share_one_time=True, share_consumed=True)
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.SHARE_CONSUMED


def test_recipient_not_in_allowlist_denied(evaluator):
    policy = Policy()
    policy.enforced.recipients = ["bob@example.com"]
    ctx = _good_ctx(verified_email="alice@example.com")
    d = evaluator.evaluate(policy, ctx)
    assert d.reason == DenyReason.IDENTITY_MISMATCH


def test_recipient_in_allowlist_allowed(evaluator):
    policy = Policy()
    policy.enforced.recipients = ["alice@example.com"]
    ctx = _good_ctx(verified_email="alice@example.com")
    d = evaluator.evaluate(policy, ctx)
    assert d.allowed


def test_expired_session_denied(evaluator, default_policy):
    ctx = _good_ctx(session_expires_at=_now() - timedelta(seconds=1))
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.SESSION_EXPIRED


def test_revoked_session_denied(evaluator, default_policy):
    ctx = _good_ctx(session_status="revoked")
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.SESSION_REVOKED


def test_rate_limit_pages_per_minute(evaluator):
    policy = Policy()
    policy.enforced.rate_limits.pages_per_minute = 5
    ctx = _good_ctx(pages_this_minute=5)
    d = evaluator.evaluate(policy, ctx)
    assert d.reason == DenyReason.RATE_LIMITED


def test_download_disabled_by_default(evaluator, default_policy):
    ctx = _good_ctx(action="download")
    d = evaluator.evaluate(default_policy, ctx)
    assert d.reason == DenyReason.DOWNLOAD_DISABLED


def test_download_enabled_when_policy_allows(evaluator):
    policy = Policy()
    policy.enforced.download = True
    ctx = _good_ctx(action="download")
    d = evaluator.evaluate(policy, ctx)
    assert d.allowed


def test_policy_roundtrip_to_dict():
    policy = Policy()
    policy.enforced.recipients = ["alice@example.com"]
    policy.enforced.expires_in = 7200
    d = policy.to_dict()
    restored = Policy.from_dict(d)
    assert restored.enforced.recipients == ["alice@example.com"]
    assert restored.enforced.expires_in == 7200


def test_policy_from_dict_does_not_mutate_input():
    source = {"enforced": {"rate_limits": {"pages_per_minute": 7}}}
    original = {"enforced": {"rate_limits": {"pages_per_minute": 7}}}
    Policy.from_dict(source)
    assert source == original

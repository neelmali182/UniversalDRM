"""Integration tests for the FastAPI API (§23.1)."""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

def test_create_asset(client):
    r = client.post("/v1/assets", json={"name": "doc.pdf", "mime_type": "application/pdf"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "doc.pdf"
    assert data["content_type"] == "document"
    assert data["status"] == "UPLOADING"


def _create_asset(client) -> dict:
    """Helper that creates and returns an asset dict."""
    r = client.post("/v1/assets", json={"name": "doc.pdf", "mime_type": "application/pdf"})
    r.raise_for_status()
    return r.json()


def test_complete_upload(client):
    asset = _create_asset(client)
    r = client.post(
        f"/v1/assets/{asset['id']}/complete",
        json={"checksum": "abc123", "size": 1024},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "PROCESSING"


def test_get_asset(client):
    asset = _create_asset(client)
    r = client.get(f"/v1/assets/{asset['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == asset["id"]


def test_get_missing_asset(client):
    r = client.get("/v1/assets/nonexistent-id")
    assert r.status_code == 404


def test_delete_asset(client):
    asset = _create_asset(client)
    r = client.delete(f"/v1/assets/{asset['id']}")
    assert r.status_code == 204
    # Should be gone
    r2 = client.get(f"/v1/assets/{asset['id']}")
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------

def test_create_share(client):
    asset = _create_asset(client)
    r = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"view": True, "download": False, "expires_in": 3600}},
    )
    assert r.status_code == 201
    data = r.json()
    assert "url" in data
    assert "token" in data
    assert data["token"] != "[redacted]"  # Returned only on creation


def _create_share(client) -> dict:
    """Helper that creates and returns a share dict."""
    asset = _create_asset(client)
    r = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"view": True, "download": False, "expires_in": 3600}},
    )
    r.raise_for_status()
    return r.json()


def test_get_share_redacts_token(client):
    share = _create_share(client)
    r = client.get(f"/v1/shares/{share['id']}")
    assert r.status_code == 200
    assert r.json()["token"] == "[redacted]"


def test_revoke_share(client):
    share = _create_share(client)
    r = client.delete(f"/v1/shares/{share['id']}")
    assert r.status_code == 204


def test_revoke_idempotent(client):
    share = _create_share(client)
    client.delete(f"/v1/shares/{share['id']}")
    r = client.delete(f"/v1/shares/{share['id']}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Viewer flow
# ---------------------------------------------------------------------------

def test_verify_start(client):
    r = client.post("/v1/viewer/verify/start", json={
        "share_token": "tok-abc",
        "email": "alice@example.com",
    })
    assert r.status_code == 200
    assert "verification_id" in r.json()


def test_verify_confirm_valid_otp(client):
    r = client.post("/v1/viewer/verify/start", json={
        "share_token": "tok-abc",
        "email": "alice@example.com",
    })
    vid = r.json()["verification_id"]
    r2 = client.post("/v1/viewer/verify/confirm", json={
        "verification_id": vid,
        "otp": "123456",  # Dev stub OTP
    })
    assert r2.status_code == 200
    assert r2.json()["verified"] is True


def test_verify_confirm_wrong_otp(client):
    r = client.post("/v1/viewer/verify/start", json={
        "share_token": "tok-abc",
        "email": "alice@example.com",
    })
    vid = r.json()["verification_id"]
    r2 = client.post("/v1/viewer/verify/confirm", json={
        "verification_id": vid,
        "otp": "000000",
    })
    assert r2.status_code == 400


def test_create_session_after_verify(client):
    r = client.post("/v1/viewer/verify/start", json={
        "share_token": "tok-abc",
        "email": "alice@example.com",
    })
    vid = r.json()["verification_id"]
    client.post("/v1/viewer/verify/confirm", json={"verification_id": vid, "otp": "123456"})
    r3 = client.post("/v1/viewer/sessions", json={
        "share_token": "tok-abc",
        "verification_id": vid,
    })
    assert r3.status_code == 201
    data = r3.json()
    assert "session_id" in data
    assert "watermark_text" in data
    # Enforcement classes must be returned (§2.3)
    assert "enforcement_classes" in data
    assert data["enforcement_classes"]["download"] == "enforced"
    assert data["enforcement_classes"]["copy"] == "best_effort"
    assert data["enforcement_classes"]["watermark"] == "traceability"


def test_session_heartbeat(client):
    r = client.post("/v1/viewer/verify/start", json={
        "share_token": "tok-abc",
        "email": "alice@example.com",
    })
    vid = r.json()["verification_id"]
    client.post("/v1/viewer/verify/confirm", json={"verification_id": vid, "otp": "123456"})
    r3 = client.post("/v1/viewer/sessions", json={
        "share_token": "tok-abc",
        "verification_id": vid,
    })
    session_id = r3.json()["session_id"]
    hb = client.post(f"/v1/viewer/sessions/{session_id}/heartbeat")
    assert hb.status_code == 200
    assert hb.json()["active"] is True


def test_security_headers(client):
    """Security headers must be present on every response (§15.3)."""
    r = client.get("/v1/health")
    assert "x-content-type-options" in r.headers
    assert "x-frame-options" in r.headers
    assert "referrer-policy" in r.headers
    assert "content-security-policy" in r.headers

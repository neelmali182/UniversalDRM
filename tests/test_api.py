"""Integration tests for the FastAPI API (§23.1)."""
import hashlib
from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from apps.api.main import app
from apps.api.config import settings
from apps.api.routes.audit import _audit_log
from apps.api.routes.viewer import _otp_start_attempts
from sdk.python.assets import AssetsModule


@pytest.fixture
def client():
    _otp_start_attempts.clear()
    return TestClient(app, headers={"Authorization": "Bearer local-development-api-key"})


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_management_routes_require_api_key():
    anonymous = TestClient(app)
    response = anonymous.post("/v1/assets", json={"name": "doc.pdf", "mime_type": "application/pdf"})
    assert response.status_code == 401


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


def test_create_asset_rejects_unrenderable_mime_type(client):
    response = client.post(
        "/v1/assets",
        json={"name": "archive.zip", "mime_type": "application/zip"},
    )
    assert response.status_code == 415


def _create_asset(client) -> dict:
    """Helper that creates and returns an asset dict."""
    r = client.post("/v1/assets", json={"name": "doc.pdf", "mime_type": "application/pdf"})
    r.raise_for_status()
    return r.json()


def _upload_asset(client, asset: dict, content: bytes = b"%PDF-1.7\ncontent") -> tuple[str, int]:
    response = client.put(
        f"/v1/assets/{asset['id']}/content",
        files={"file": (asset["name"], content, asset["mime_type"])},
    )
    response.raise_for_status()
    return hashlib.sha256(content).hexdigest(), len(content)


def _complete_asset_upload(client, asset: dict) -> dict:
    checksum, size = _upload_asset(client, asset)
    response = client.post(
        f"/v1/assets/{asset['id']}/complete",
        json={"checksum": checksum, "size": size},
    )
    response.raise_for_status()
    return response.json()


def test_complete_upload(client):
    asset = _create_asset(client)
    checksum, size = _upload_asset(client, asset)
    r = client.post(
        f"/v1/assets/{asset['id']}/complete",
        json={"checksum": checksum, "size": size},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "UPLOADED"


def test_complete_upload_rejects_unverified_content(client):
    asset = _create_asset(client)
    response = client.post(
        f"/v1/assets/{asset['id']}/complete",
        json={"checksum": "a" * 64, "size": 12},
    )
    assert response.status_code == 409


def test_python_sdk_upload_transfers_and_completes_file(client, tmp_path):
    path = tmp_path / "sample.png"
    image_buffer = BytesIO()
    Image.new("RGB", (8, 6), "white").save(image_buffer, format="PNG")
    path.write_bytes(image_buffer.getvalue())
    asset = AssetsModule(client).upload(str(path))
    assert asset["status"] == "UPLOADED"
    assert asset["size"] == path.stat().st_size


def test_upload_rejects_mime_signature_mismatch(client):
    asset = _create_asset(client)
    response = client.put(
        f"/v1/assets/{asset['id']}/content",
        files={"file": (asset["name"], b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_production_upload_fails_closed_without_secure_ingestion(client, monkeypatch):
    asset = _create_asset(client)
    monkeypatch.setattr(settings, "app_env", "production")
    response = client.put(
        f"/v1/assets/{asset['id']}/content",
        files={"file": (asset["name"], b"%PDF-1.7\ncontent", asset["mime_type"])},
    )
    assert response.status_code == 501


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
    _complete_asset_upload(client, asset)
    r = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"view": True, "download": False, "expires_in": 3600}},
    )
    assert r.status_code == 201
    data = r.json()
    assert "url" in data
    assert "token" in data
    assert data["token"] != "[redacted]"  # Returned only on creation
    assert client.get(f"/v/{data['token']}").status_code == 200


def _create_share(client) -> dict:
    """Helper that creates and returns a share dict."""
    asset = _create_asset(client)
    _complete_asset_upload(client, asset)
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

def _start_verification(client) -> tuple[dict, dict]:
    share = _create_share(client)
    response = client.post("/v1/viewer/verify/start", json={
        "share_token": share["token"],
        "email": "alice@example.com",
    })
    response.raise_for_status()
    return share, response.json()


def _confirm_verification(client, verification: dict, otp: str | None = None):
    return client.post("/v1/viewer/verify/confirm", json={
        "verification_id": verification["verification_id"],
        "otp": otp or verification["development_otp"],
    })

def test_verify_start(client):
    _, verification = _start_verification(client)
    assert "verification_id" in verification
    assert len(verification["development_otp"]) == 6


def test_verify_confirm_valid_otp(client):
    _, verification = _start_verification(client)
    r2 = _confirm_verification(client, verification)
    assert r2.status_code == 200
    assert r2.json()["verified"] is True


def test_verify_confirm_wrong_otp(client):
    _, verification = _start_verification(client)
    wrong_otp = f"{(int(verification['development_otp']) + 1) % 1_000_000:06d}"
    r2 = _confirm_verification(client, verification, wrong_otp)
    assert r2.status_code == 400


def test_otp_allows_five_attempts_then_locks_verification(client):
    _, verification = _start_verification(client)
    for _ in range(5):
        response = _confirm_verification(client, verification, "000000")
        assert response.status_code == 400
    locked = _confirm_verification(client, verification, verification["development_otp"])
    assert locked.status_code == 429


def test_otp_start_is_rate_limited_per_email_and_client(client):
    share = _create_share(client)
    body = {"share_token": share["token"], "email": "alice@example.com"}
    for _ in range(5):
        assert client.post("/v1/viewer/verify/start", json=body).status_code == 200
    assert client.post("/v1/viewer/verify/start", json=body).status_code == 429


def test_create_session_after_verify(client):
    share, verification = _start_verification(client)
    _confirm_verification(client, verification)
    r3 = client.post("/v1/viewer/sessions", json={
        "share_token": share["token"],
        "verification_id": verification["verification_id"],
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
    share, verification = _start_verification(client)
    _confirm_verification(client, verification)
    r3 = client.post("/v1/viewer/sessions", json={
        "share_token": share["token"],
        "verification_id": verification["verification_id"],
    })
    session_id = r3.json()["session_id"]
    hb = client.post(f"/v1/viewer/sessions/{session_id}/heartbeat")
    assert hb.status_code == 200
    assert hb.json()["active"] is True


def test_verification_cannot_be_reused_for_another_share(client):
    _, verification = _start_verification(client)
    _confirm_verification(client, verification)
    other_share = _create_share(client)
    response = client.post("/v1/viewer/sessions", json={
        "share_token": other_share["token"],
        "verification_id": verification["verification_id"],
    })
    assert response.status_code == 403


def test_view_disabled_share_cannot_create_viewer_session(client):
    asset = _create_asset(client)
    _complete_asset_upload(client, asset)
    share_response = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"view": False}},
    )
    share_response.raise_for_status()
    share = share_response.json()
    verification_response = client.post("/v1/viewer/verify/start", json={
        "share_token": share["token"], "email": "alice@example.com",
    })
    verification_response.raise_for_status()
    verification = verification_response.json()
    _confirm_verification(client, verification).raise_for_status()
    session_response = client.post("/v1/viewer/sessions", json={
        "share_token": share["token"], "verification_id": verification["verification_id"],
    })
    assert session_response.status_code == 403


def test_share_max_sessions_is_enforced(client):
    asset = _create_asset(client)
    _complete_asset_upload(client, asset)
    share_response = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"max_sessions": 1}},
    )
    share_response.raise_for_status()
    share = share_response.json()

    def create_verified_session():
        started = client.post("/v1/viewer/verify/start", json={
            "share_token": share["token"], "email": "alice@example.com",
        })
        started.raise_for_status()
        verification = started.json()
        _confirm_verification(client, verification).raise_for_status()
        return client.post("/v1/viewer/sessions", json={
            "share_token": share["token"], "verification_id": verification["verification_id"],
        })

    assert create_verified_session().status_code == 201
    assert create_verified_session().status_code == 409


def test_share_link_delivers_pages_only_with_session_cookie(client):
    image_buffer = BytesIO()
    Image.new("RGB", (12, 8), "white").save(image_buffer, format="PNG")
    content = image_buffer.getvalue()
    asset_response = client.post("/v1/assets", json={"name": "image.png", "mime_type": "image/png"})
    asset_response.raise_for_status()
    asset = asset_response.json()
    checksum, size = _upload_asset(client, asset, content)
    client.post(
        f"/v1/assets/{asset['id']}/complete",
        json={"checksum": checksum, "size": size},
    ).raise_for_status()
    share_response = client.post(
        f"/v1/assets/{asset['id']}/shares",
        json={"policy": {"view": True, "expires_in": 3600}},
    )
    share_response.raise_for_status()
    share = share_response.json()

    start = client.post("/v1/viewer/verify/start", json={
        "share_token": share["token"], "email": "alice@example.com",
    })
    start.raise_for_status()
    verification = start.json()
    client.post("/v1/viewer/verify/confirm", json={
        "verification_id": verification["verification_id"],
        "otp": verification["development_otp"],
    }).raise_for_status()
    session_response = client.post("/v1/viewer/sessions", json={
        "share_token": share["token"], "verification_id": verification["verification_id"],
    })
    session_response.raise_for_status()
    session_id = session_response.json()["session_id"]

    anonymous = TestClient(app)
    assert anonymous.get(f"/v1/viewer/sessions/{session_id}/content").status_code == 403
    content_response = client.get(f"/v1/viewer/sessions/{session_id}/content")
    assert content_response.status_code == 200
    assert content_response.json()["pages"] == 1
    page_response = client.get(f"/v1/viewer/sessions/{session_id}/pages/0")
    assert page_response.status_code == 200
    assert page_response.headers["cache-control"] == "no-store"
    assert page_response.headers["content-type"] == "image/jpeg"


def test_security_headers(client):
    """Security headers must be present on every response (§15.3)."""
    r = client.get("/v1/health")
    assert "x-content-type-options" in r.headers
    assert "x-frame-options" in r.headers
    assert "referrer-policy" in r.headers
    assert "content-security-policy" in r.headers


def test_audit_cursor_returns_next_page(client):
    _audit_log[:] = [
        {
            "id": str(i), "event_type": "VIEW", "organization_id": "test",
            "asset_id": "asset-a", "session_id": "session-a", "metadata": {},
            "ip": "127.0.0.1", "created_at": "2026-10-01T00:00:00+00:00",
        }
        for i in range(3)
    ]
    first = client.get("/v1/assets/asset-a/audit?limit=2").json()
    second = client.get(f"/v1/assets/asset-a/audit?limit=2&cursor={first['cursor']}").json()
    assert [event["id"] for event in first["events"]] == ["0", "1"]
    assert [event["id"] for event in second["events"]] == ["2"]
    assert second["cursor"] is None
    _audit_log.clear()


def test_audit_rejects_invalid_cursor_and_oversized_limit(client):
    assert client.get("/v1/assets/a/audit?cursor=not-a-cursor").status_code == 400
    assert client.get("/v1/assets/a/audit?limit=1000").status_code == 422


def test_forensics_trace_reports_not_implemented(client):
    assert client.post("/v1/forensics/trace").status_code == 501

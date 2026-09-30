"""Provider interface protocols for UniversalDRM (§8.3).

These are typing.Protocol interfaces. Any implementation satisfies the
interface structurally — no base class required.  New providers can be
added without touching the core API (open-closed principle).
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class StorageProvider(Protocol):
    """Object storage — local filesystem, MinIO, S3, R2, etc. (§8.3)."""

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Store *data* under *key*."""
        ...

    def get(self, key: str) -> bytes:
        """Return bytes stored at *key*."""
        ...

    def delete(self, key: str) -> None:
        """Delete object at *key*."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if *key* exists."""
        ...


@runtime_checkable
class KeyProvider(Protocol):
    """Envelope key management — local dev, AWS KMS, Vault, HSM (§12.2)."""

    def create_tenant_kek(self, tenant_id: str) -> str:
        """Create a KEK for *tenant_id* and return a reference/alias."""
        ...

    def wrap_dek(self, tenant_id: str, dek: bytes, aad: bytes) -> bytes:
        """Wrap (encrypt) a DEK using the tenant's KEK.

        *aad* must include asset_id + version + tenant_id to bind ciphertext
        to its asset — swapping wrapped DEKs between assets will fail decryption.
        """
        ...

    def unwrap_dek(self, tenant_id: str, wrapped: bytes, aad: bytes) -> bytes:
        """Unwrap (decrypt) a DEK using the tenant's KEK."""
        ...

    def rotate_kek(self, tenant_id: str) -> str:
        """Rotate the tenant KEK; return the new version reference."""
        ...


@runtime_checkable
class WatermarkProvider(Protocol):
    """Visible and forensic watermarking (§14.3)."""

    def payload_for(self, session_id: str) -> bytes:
        """Generate a unique forensic payload for this session."""
        ...

    def render_visible(self, image: object, session_id: str, policy: dict) -> object:
        """Burn a visible watermark into *image* and return the result."""
        ...

    def embed_forensic(self, image: object, payload: bytes) -> object:
        """Embed an invisible forensic payload into *image*."""
        ...

    def extract_forensic(self, image: object) -> Optional[bytes]:
        """Extract a forensic payload from *image*, or None if not found."""
        ...


@runtime_checkable
class Renderer(Protocol):
    """Content renderer — PDF, image, etc. (§13, §8.3)."""

    def page_count(self, path: str, mime: str) -> int:
        """Number of pages/frames for *path*."""
        ...

    def render_page(self, path: str, mime: str, index: int, watermark: str) -> bytes:
        """JPEG bytes of page *index* (0-based) with *watermark* burned in."""
        ...


@runtime_checkable
class AuditSink(Protocol):
    """Audit event sink — PostgreSQL, stdout, SIEM, etc. (§17, §8.3)."""

    def emit(self, event: object) -> None:
        """Persist or forward an audit event."""
        ...


@runtime_checkable
class IdentityProvider(Protocol):
    """Recipient identity verification — email OTP, OIDC, SAML (§9, §8.3)."""

    def send_otp(self, email: str, share_id: str) -> str:
        """Send OTP to *email* and return the verification record id."""
        ...

    def verify_otp(self, verification_id: str, otp: str) -> bool:
        """Verify an OTP; return True on success."""
        ...

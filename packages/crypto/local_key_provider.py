"""Local (development-only) key provider for UniversalDRM (§12.2).

WARNING: This provider stores KEKs as plaintext on disk under
``~/.universaldrm/keys/``. It is suitable ONLY for local development
and tests.  Use AWSKMSKeyProvider / VaultKeyProvider in production.

The envelope design follows §12.1: each tenant has a KEK; each asset
has a DEK wrapped by that KEK.  Wrapping uses AES-256-GCM so the DEK
is also bound to its AAD.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .envelope import decrypt_blob, encrypt_blob, generate_dek

_DEFAULT_KEYS_DIR = Path.home() / ".universaldrm" / "keys"


class LocalKeyProvider:
    """DEV-ONLY key provider that stores KEKs as files on disk.

    Args:
        keys_dir: Directory to store key files.  Defaults to
            ``~/.universaldrm/keys/``.  Ensure the directory is not
            committed to version control.
    """

    def __init__(self, keys_dir: str | Path | None = None) -> None:
        self._dir = Path(keys_dir) if keys_dir else _DEFAULT_KEYS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _kek_path(self, tenant_id: str, version: str = "v1") -> Path:
        return self._dir / f"{tenant_id}_{version}.json"

    def _load_kek(self, tenant_id: str, version: str = "v1") -> bytes:
        path = self._kek_path(tenant_id, version)
        if not path.exists():
            raise KeyError(f"No KEK found for tenant {tenant_id!r} version {version!r}")
        data = json.loads(path.read_text())
        return bytes.fromhex(data["kek"])

    def _save_kek(self, tenant_id: str, kek: bytes, version: str = "v1") -> None:
        path = self._kek_path(tenant_id, version)
        path.write_text(json.dumps({"kek": kek.hex(), "version": version}))
        path.chmod(0o600)

    # ------------------------------------------------------------------
    # KeyProvider protocol (§12.2)
    # ------------------------------------------------------------------

    def create_tenant_kek(self, tenant_id: str) -> str:
        """Generate and persist a KEK for *tenant_id*. Returns version ref."""
        kek = generate_dek()  # 256-bit random key
        version = "v1"
        self._save_kek(tenant_id, kek, version)
        return f"{tenant_id}:{version}"

    def wrap_dek(self, tenant_id: str, dek: bytes, aad: bytes) -> bytes:
        """Wrap *dek* using the tenant KEK (AES-256-GCM)."""
        kek = self._load_kek(tenant_id)
        return encrypt_blob(dek, kek, aad)

    def unwrap_dek(self, tenant_id: str, wrapped: bytes, aad: bytes) -> bytes:
        """Unwrap a DEK that was wrapped by :meth:`wrap_dek`."""
        kek = self._load_kek(tenant_id)
        return decrypt_blob(wrapped, kek, aad)

    def rotate_kek(self, tenant_id: str) -> str:
        """Generate a new KEK version.

        NOTE: This implementation does NOT re-wrap existing DEKs.  Full
        re-key support (lazy or batch) is planned for Phase 7.
        """
        existing_path = self._kek_path(tenant_id, "v1")
        if existing_path.exists():
            import time
            version = f"v{int(time.time())}"
        else:
            version = "v1"
        new_kek = generate_dek()
        self._save_kek(tenant_id, new_kek, version)
        return f"{tenant_id}:{version}"

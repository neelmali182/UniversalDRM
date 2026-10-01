"""Envelope encryption for UniversalDRM (§12).

Uses AES-256-GCM via the ``cryptography`` package.  Each asset gets a
random 256-bit DEK.  The DEK is wrapped by the tenant's KEK inside the
KeyProvider.  The raw DEK is never stored — only the wrapped ciphertext.

For large files, this module handles small-blob encryption (in-memory).
Chunked/streaming encryption for files >100 MB should use Tink streaming
AEAD (planned for §12.3 / Phase 7).

AAD design: the additional authenticated data encodes
``tenant_id:asset_id:version`` so that wrapped DEKs cannot be swapped
between assets (§12.1 "AAD binding").
"""
from __future__ import annotations

import os
from packages.core.protocols import KeyProvider

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_BYTES = 32   # AES-256
_NONCE_BYTES = 12  # 96-bit nonce per NIST SP 800-38D


def _make_aad(tenant_id: str, asset_id: str, version: int) -> bytes:
    """Canonical AAD string bound to asset identity."""
    return f"{tenant_id}:{asset_id}:{version}".encode()


def generate_dek() -> bytes:
    """Generate a fresh random 256-bit data encryption key."""
    return os.urandom(_KEY_BYTES)


def encrypt_blob(plaintext: bytes, dek: bytes, aad: bytes) -> bytes:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns ``nonce || ciphertext_with_tag`` (nonce prepended for
    self-contained storage; never reuse a nonce with the same key).
    """
    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ciphertext


def decrypt_blob(ciphertext_with_nonce: bytes, dek: bytes, aad: bytes) -> bytes:
    """Decrypt a blob produced by :func:`encrypt_blob`."""
    nonce = ciphertext_with_nonce[:_NONCE_BYTES]
    ciphertext = ciphertext_with_nonce[_NONCE_BYTES:]
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext, aad)


def envelope_encrypt(
    plaintext: bytes,
    tenant_id: str,
    asset_id: str,
    version: int,
    key_provider: KeyProvider,
) -> tuple[bytes, bytes]:
    """Encrypt *plaintext* and return ``(ciphertext, wrapped_dek)``.

    Args:
        plaintext: Raw content bytes.
        tenant_id: Tenant identifier (used for AAD and KEK lookup).
        asset_id: Asset identifier (AAD binding).
        version: Asset version number (AAD binding).
        key_provider: A :class:`~packages.core.protocols.KeyProvider`.

    Returns:
        Tuple of ``(ciphertext, wrapped_dek)``.  Store both; discard the
        plaintext.  The raw DEK is never returned or stored.
    """
    aad = _make_aad(tenant_id, asset_id, version)
    dek = generate_dek()
    ciphertext = encrypt_blob(plaintext, dek, aad)
    wrapped_dek = key_provider.wrap_dek(tenant_id, dek, aad)
    # Zero out the key material from memory as best we can in Python
    dek = b"\x00" * len(dek)
    del dek
    return ciphertext, wrapped_dek


def envelope_decrypt(
    ciphertext: bytes,
    wrapped_dek: bytes,
    tenant_id: str,
    asset_id: str,
    version: int,
    key_provider: KeyProvider,
) -> bytes:
    """Decrypt *ciphertext* using the wrapped DEK and KEK from *key_provider*.

    The unwrapped DEK exists only for the duration of this call.
    """
    aad = _make_aad(tenant_id, asset_id, version)
    dek = key_provider.unwrap_dek(tenant_id, wrapped_dek, aad)
    try:
        return decrypt_blob(ciphertext, dek, aad)
    finally:
        dek = b"\x00" * len(dek)
        del dek

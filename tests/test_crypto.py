"""Tests for envelope encryption and LocalKeyProvider (§12)."""
import os
import pytest
from packages.crypto.envelope import (
    generate_dek,
    encrypt_blob,
    decrypt_blob,
    envelope_encrypt,
    envelope_decrypt,
)
from packages.crypto.local_key_provider import LocalKeyProvider


@pytest.fixture
def key_provider(tmp_path):
    provider = LocalKeyProvider(keys_dir=tmp_path / "keys")
    provider.create_tenant_kek("tenant-1")
    return provider


def test_generate_dek_is_32_bytes():
    dek = generate_dek()
    assert len(dek) == 32


def test_generate_dek_is_random():
    assert generate_dek() != generate_dek()


def test_encrypt_decrypt_blob():
    dek = generate_dek()
    aad = b"tenant-1:asset-abc:1"
    plaintext = b"hello world"
    ciphertext = encrypt_blob(plaintext, dek, aad)
    assert ciphertext != plaintext
    assert decrypt_blob(ciphertext, dek, aad) == plaintext


def test_wrong_aad_fails_decryption():
    from cryptography.exceptions import InvalidTag
    dek = generate_dek()
    aad = b"tenant-1:asset-abc:1"
    ciphertext = encrypt_blob(b"secret", dek, aad)
    with pytest.raises(InvalidTag):
        decrypt_blob(ciphertext, dek, b"tenant-1:asset-abc:2")  # wrong version


def test_local_key_provider_wrap_unwrap(key_provider):
    dek = generate_dek()
    aad = b"tenant-1:asset-xyz:1"
    wrapped = key_provider.wrap_dek("tenant-1", dek, aad)
    assert wrapped != dek
    unwrapped = key_provider.unwrap_dek("tenant-1", wrapped, aad)
    assert unwrapped == dek


def test_local_key_provider_wrong_tenant(key_provider, tmp_path):
    dek = generate_dek()
    aad = b"tenant-2:asset-xyz:1"
    # tenant-2 has no KEK yet
    with pytest.raises(KeyError):
        key_provider.wrap_dek("tenant-2", dek, aad)


def test_envelope_encrypt_decrypt_roundtrip(key_provider):
    plaintext = b"confidential document content"
    ciphertext, wrapped_dek = envelope_encrypt(
        plaintext, "tenant-1", "asset-001", 1, key_provider
    )
    assert ciphertext != plaintext
    assert len(wrapped_dek) > 0

    recovered = envelope_decrypt(
        ciphertext, wrapped_dek, "tenant-1", "asset-001", 1, key_provider
    )
    assert recovered == plaintext


def test_envelope_wrong_asset_id_fails(key_provider):
    from cryptography.exceptions import InvalidTag
    plaintext = b"secret"
    ciphertext, wrapped_dek = envelope_encrypt(
        plaintext, "tenant-1", "asset-001", 1, key_provider
    )
    with pytest.raises(InvalidTag):
        envelope_decrypt(ciphertext, wrapped_dek, "tenant-1", "asset-WRONG", 1, key_provider)

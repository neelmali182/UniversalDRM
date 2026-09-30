"""Tests for storage providers (§8.3)."""
import pytest
from packages.storage.local import LocalStorageProvider


@pytest.fixture
def store(tmp_path):
    return LocalStorageProvider(tmp_path / "objects")


def test_put_and_get(store):
    store.put("test/file.bin", b"hello")
    assert store.get("test/file.bin") == b"hello"


def test_exists_true(store):
    store.put("exists.bin", b"data")
    assert store.exists("exists.bin")


def test_exists_false(store):
    assert not store.exists("missing.bin")


def test_delete(store):
    store.put("del.bin", b"data")
    store.delete("del.bin")
    assert not store.exists("del.bin")


def test_delete_nonexistent_is_noop(store):
    store.delete("never_existed.bin")  # Should not raise


def test_get_missing_raises(store):
    with pytest.raises(FileNotFoundError):
        store.get("missing.bin")


def test_path_traversal_blocked(store):
    with pytest.raises(ValueError, match="Invalid storage key"):
        store.put("../../etc/passwd", b"bad")

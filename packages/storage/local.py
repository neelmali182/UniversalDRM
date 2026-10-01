"""Local filesystem storage provider (dev / test) (§8.3)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO


class LocalStorageProvider:
    """Stores objects as files under a base directory.

    Suitable for development and testing. Use an S3-compatible provider
    (MinIO / AWS S3 / Cloudflare R2) in production.

    Args:
        base_dir: Root directory for object storage.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """Resolve storage key to an absolute path, blocking path traversal."""
        # Block keys that contain path traversal components before resolution
        parts = Path(key).parts
        if any(part in ("..", ".") for part in parts):
            raise ValueError(f"Invalid storage key: {key!r}")
        p = (self._base / key).resolve()
        base_resolved = self._base.resolve()
        # Ensure the resolved path is inside the base directory (cross-platform)
        try:
            p.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Invalid storage key: {key!r}")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write *data* to *key*."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_stream(self, key: str, source: BinaryIO, max_bytes: int) -> tuple[int, str]:
        """Write a bounded stream atomically and return its byte count and SHA-256."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                temporary_path = temporary.name
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Upload exceeds the configured size limit")
                    digest.update(chunk)
                    temporary.write(chunk)
            os.replace(temporary_path, path)
            temporary_path = None
            return size, digest.hexdigest()
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        """Read and return bytes at *key*."""
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key!r}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        """Delete object at *key* (no-op if absent)."""
        path = self._path(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        """Return True if *key* exists."""
        return self._path(key).exists()

    def path_for(self, key: str) -> Path:
        """Return a validated local path for server-side streaming readers."""
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Object not found: {key!r}")
        return path

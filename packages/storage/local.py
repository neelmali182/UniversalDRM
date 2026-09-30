"""Local filesystem storage provider (dev / test) (§8.3)."""
from __future__ import annotations

from pathlib import Path


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
        # Prevent path traversal
        safe = key.replace("..", "").lstrip("/\\")
        p = (self._base / safe).resolve()
        if not str(p).startswith(str(self._base.resolve())):
            raise ValueError(f"Invalid storage key: {key!r}")
        return p

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Write *data* to *key*."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

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

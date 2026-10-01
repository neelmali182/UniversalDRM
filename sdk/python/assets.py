"""SDK Assets module (§20.1)."""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import httpx


class AssetsModule:
    """Manage assets — upload, protect, get, delete."""

    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def upload(self, path: str, name: str | None = None) -> dict[str, Any]:
        """Upload a file and return the asset record.

        Steps:
        1. Detect MIME type from magic bytes (via mimetypes + file sniff).
        2. POST /v1/assets to create the record.
        3. Stream-upload the file bytes.
        4. POST /v1/assets/{id}/complete with checksum.

        Args:
            path: Local path to the file.
            name: Display name (defaults to filename).

        Returns:
            Asset dict from the API.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path!r}")

        display_name = name or file_path.name
        # Detect MIME type — in production use python-magic for magic-byte detection
        mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

        # 1. Create asset record
        r = self._http.post("/v1/assets", json={"name": display_name, "mime_type": mime_type})
        r.raise_for_status()
        asset = r.json()

        # 2. Transfer the content; the server independently checks its signature and digest.
        with file_path.open("rb") as source:
            upload = self._http.put(
                f"/v1/assets/{asset['id']}/content",
                files={"file": (display_name, source, mime_type)},
            )
        upload.raise_for_status()

        # 3. Compute the completion digest without buffering the full file.
        digest = hashlib.sha256()
        size = 0
        with file_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)

        # 4. Complete upload
        r2 = self._http.post(
            f"/v1/assets/{asset['id']}/complete",
            json={"checksum": digest.hexdigest(), "size": size},
        )
        r2.raise_for_status()
        return r2.json()

    def get(self, asset_id: str) -> dict[str, Any]:
        """Get asset metadata."""
        r = self._http.get(f"/v1/assets/{asset_id}")
        r.raise_for_status()
        return r.json()

    def delete(self, asset_id: str) -> None:
        """Delete an asset."""
        r = self._http.delete(f"/v1/assets/{asset_id}")
        r.raise_for_status()

    def protect(self, asset_id: str) -> dict[str, Any]:
        """Trigger the protection pipeline for an asset."""
        r = self._http.post(f"/v1/assets/{asset_id}/protect")
        r.raise_for_status()
        return r.json()

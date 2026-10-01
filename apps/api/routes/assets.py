"""Asset routes — upload, protect, lifecycle (§19)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field

from apps.api.config import settings
from packages.core.enums import AssetStatus, ContentType, ContentFormat, ProtectionEngine
from packages.core.classification import classify
from packages.storage.local import LocalStorageProvider
from ..security import require_api_key

router = APIRouter(tags=["assets"], dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AssetCreateRequest(BaseModel):
    name: str = Field(..., description="Human-readable filename")
    mime_type: str = Field(..., description="MIME type from magic-byte detection (not filename)")


class AssetResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    content_type: ContentType
    content_format: ContentFormat
    engine: ProtectionEngine
    status: AssetStatus
    size: int
    page_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AssetUploadCompleteRequest(BaseModel):
    checksum: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 hex digest of uploaded file")
    size: int = Field(..., ge=1)


# ---------------------------------------------------------------------------
# In-memory store (stub — replace with DB + async ORM in §18)
# ---------------------------------------------------------------------------

_assets: dict[str, dict] = {}
_storage = LocalStorageProvider(settings.storage_local_dir)
_SUPPORTED_UPLOAD_MIMES = {
    "application/pdf", "text/plain", "image/png", "image/jpeg", "image/gif", "image/webp",
}


def _sniff_mime(prefix: bytes, mime_type: str) -> str | None:
    normalized = mime_type.lower().split(";")[0].strip()
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return "image/webp"
    if normalized == "text/plain" and b"\x00" not in prefix:
        return "text/plain"
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create asset and start upload",
)
async def create_asset(body: AssetCreateRequest):
    """Create an asset record and prepare for upload.

    The MIME type must come from magic-byte detection on the client side,
    not from the filename extension (§8.2).
    """
    normalized_mime = body.mime_type.lower().split(";")[0].strip()
    if normalized_mime not in _SUPPORTED_UPLOAD_MIMES:
        raise HTTPException(status_code=415, detail="This MIME type is not supported by the configured renderer")
    content_type, content_format, engine = classify(normalized_mime)
    asset_id = str(uuid.uuid4())
    now = _now()

    asset = {
        "id": asset_id,
        "name": body.name,
        "mime_type": normalized_mime,
        "content_type": content_type,
        "content_format": content_format,
        "engine": engine,
        "status": AssetStatus.UPLOADING,
        "size": 0,
        "page_count": None,
        "created_at": now,
        "updated_at": now,
        "storage_key": asset_id,
        "upload_checksum": None,
    }
    _assets[asset_id] = asset
    return AssetResponse(
        id=asset["id"],
        name=asset["name"],
        mime_type=asset["mime_type"],
        content_type=asset["content_type"],
        content_format=asset["content_format"],
        engine=asset["engine"],
        status=asset["status"],
        size=asset["size"],
        page_count=asset["page_count"],
        created_at=asset["created_at"],
        updated_at=asset["updated_at"],
    )


@router.put("/assets/{asset_id}/content", status_code=status.HTTP_204_NO_CONTENT, summary="Upload asset bytes")
async def upload_asset_content(asset_id: str, file: UploadFile = File(...)):
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset["status"] != AssetStatus.UPLOADING:
        raise HTTPException(status_code=409, detail="Asset is not accepting an upload")
    if not settings.is_development:
        raise HTTPException(
            status_code=501,
            detail="Secure ingestion is unavailable until encrypted storage and malware scanning are configured",
        )

    prefix = file.file.read(16)
    file.file.seek(0)
    detected_mime = _sniff_mime(prefix, asset["mime_type"])
    declared_mime = asset["mime_type"].lower().split(";")[0].strip()
    if detected_mime != declared_mime:
        raise HTTPException(status_code=415, detail="Uploaded content does not match the declared supported MIME type")

    try:
        size, checksum = _storage.put_stream(asset["storage_key"], file.file, settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if size == 0:
        _storage.delete(asset["storage_key"])
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    asset["size"] = size
    asset["upload_checksum"] = checksum
    asset["updated_at"] = _now()


@router.post(
    "/assets/{asset_id}/complete",
    response_model=AssetResponse,
    summary="Finish upload and enqueue processing",
)
async def complete_upload(asset_id: str, body: AssetUploadCompleteRequest):
    """Mark the upload complete after verifying the stored bytes.

    Malware scanning and encryption require the background worker, which is not wired yet.
    """
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset["status"] != AssetStatus.UPLOADING:
        raise HTTPException(status_code=409, detail="Asset is not in UPLOADING state")
    if asset["upload_checksum"] is None:
        raise HTTPException(status_code=409, detail="Upload file content before completing the upload")
    if body.size != asset["size"] or body.checksum.lower() != asset["upload_checksum"]:
        raise HTTPException(status_code=400, detail="Uploaded size or checksum does not match stored content")

    asset["status"] = AssetStatus.UPLOADED
    asset["updated_at"] = _now()

    return AssetResponse(**asset)


@router.get(
    "/assets/{asset_id}",
    response_model=AssetResponse,
    summary="Get asset metadata",
)
async def get_asset(asset_id: str):
    """Retrieve asset metadata."""
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetResponse(**asset)


@router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete asset",
)
async def delete_asset(asset_id: str):
    """Delete an asset and its storage objects.

    In production: delete object from storage, delete wrapped DEK,
    write ASSET_DELETED audit tombstone (§17.1, §12.5).
    """
    asset = _assets.pop(asset_id, None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    _storage.delete(asset["storage_key"])
    # TODO: delete from object storage, delete DEK, write audit tombstone


@router.post(
    "/assets/{asset_id}/protect",
    response_model=AssetResponse,
    summary="Trigger protection pipeline",
)
async def protect_asset(asset_id: str):
    """Report that the protection pipeline is not configured.

    The API must not report success until a real worker has processed the asset.
    """
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset["status"] not in (AssetStatus.UPLOADED, AssetStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Asset must be UPLOADED or PROCESSING")

    raise HTTPException(status_code=501, detail="Protection worker is not configured")

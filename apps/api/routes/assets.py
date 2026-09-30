"""Asset routes — upload, protect, lifecycle (§19)."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field

from packages.core.enums import AssetStatus, ContentType, ContentFormat, ProtectionEngine
from packages.core.classification import classify

router = APIRouter(tags=["assets"])


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
    checksum: str = Field(..., description="SHA-256 hex digest of uploaded file")
    size: int


# ---------------------------------------------------------------------------
# In-memory store (stub — replace with DB + async ORM in §18)
# ---------------------------------------------------------------------------

_assets: dict[str, dict] = {}


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
    content_type, content_format, engine = classify(body.mime_type)
    asset_id = str(uuid.uuid4())
    now = _now()

    asset = {
        "id": asset_id,
        "name": body.name,
        "mime_type": body.mime_type,
        "content_type": content_type,
        "content_format": content_format,
        "engine": engine,
        "status": AssetStatus.UPLOADING,
        "size": 0,
        "page_count": None,
        "created_at": now,
        "updated_at": now,
    }
    _assets[asset_id] = asset
    return AssetResponse(**asset)


@router.post(
    "/assets/{asset_id}/complete",
    response_model=AssetResponse,
    summary="Finish upload and enqueue processing",
)
async def complete_upload(asset_id: str, body: AssetUploadCompleteRequest):
    """Mark the upload complete and transition to PROCESSING.

    In production: validate checksum, enqueue ENCRYPT_ASSET job,
    run ClamAV scan, magic-byte re-validate (§11).
    """
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset["status"] != AssetStatus.UPLOADING:
        raise HTTPException(status_code=409, detail="Asset is not in UPLOADING state")

    asset["size"] = body.size
    asset["status"] = AssetStatus.PROCESSING
    asset["updated_at"] = _now()

    # TODO: enqueue ENCRYPT_ASSET + MALWARE_SCAN jobs via Celery (§21.1)
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
    # TODO: delete from object storage, delete DEK, write audit tombstone


@router.post(
    "/assets/{asset_id}/protect",
    response_model=AssetResponse,
    summary="Trigger protection pipeline",
)
async def protect_asset(asset_id: str):
    """Enqueue the protection pipeline for an uploaded asset.

    In production: enqueue RENDER_PDF / ENCRYPT_ASSET jobs (§21.1).
    """
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset["status"] not in (AssetStatus.UPLOADED, AssetStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Asset must be UPLOADED or PROCESSING")

    asset["status"] = AssetStatus.PROCESSING
    asset["updated_at"] = _now()
    # TODO: enqueue protection job
    return AssetResponse(**asset)

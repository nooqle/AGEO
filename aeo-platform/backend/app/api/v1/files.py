"""File upload/download API endpoints."""

import os
import logging

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment."""
    # Quick pre-check if size header is available (full check done in service)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    service = FileService(db)
    result = await service.save_file(file)
    return result


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download a file by ID."""
    service = FileService(db)
    file_path = await service.get_file_path(file_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
    )

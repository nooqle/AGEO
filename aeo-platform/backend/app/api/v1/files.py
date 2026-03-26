"""File upload/download API endpoints."""

import os
import logging

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.file_service import FileService, MAX_FILE_SIZE, MAX_FILE_SIZE_LABEL

router = APIRouter(prefix="/files", tags=["files"])

logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment."""
    # Quick pre-check if size header is available (full check done in service)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        filename = os.path.basename(file.filename or "表格")
        raise HTTPException(
            status_code=413,
            detail=f"文件「{filename}」超过 {MAX_FILE_SIZE_LABEL} 限制",
        )

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

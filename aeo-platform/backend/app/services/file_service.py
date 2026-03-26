"""File storage service for message attachments.

Uses SQLAlchemy for persistent metadata storage.
Falls back to in-memory if no DB session provided.
"""

import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Storage directory — configurable via env
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads"),
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Security: allowed file extensions
ALLOWED_EXTENSIONS = {
    ".csv", ".xlsx",
}

# Security: allowed MIME types
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_FILE_SIZE_LABEL = "2MB"

# In-memory fallback
_files: dict[str, dict[str, Any]] = {}


class FileService:
    """Manages file uploads and storage."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def save_file(self, file: UploadFile) -> dict[str, Any]:
        """Save uploaded file to disk and register it."""
        file_id = str(uuid4())
        ext = os.path.splitext(file.filename or "")[1].lower()

        # Security: validate extension
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="仅支持上传 CSV 或 XLSX 表格",
            )

        # Security: validate MIME type
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail="仅支持上传 CSV 或 XLSX 表格",
            )

        safe_name = f"{file_id}{ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)

        # Security: path traversal protection
        abs_upload_dir = os.path.abspath(UPLOAD_DIR)
        abs_file_path = os.path.abspath(file_path)
        if not abs_file_path.startswith(abs_upload_dir):
            raise HTTPException(status_code=400, detail="Invalid file path")

        # Read with size limit (chunked)
        chunks = []
        total_size = 0
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                filename = Path(file.filename or "表格").name
                raise HTTPException(
                    status_code=413,
                    detail=f"文件「{filename}」超过 {MAX_FILE_SIZE_LABEL} 限制",
                )
            chunks.append(chunk)
        content = b"".join(chunks)

        with open(file_path, "wb") as f:
            f.write(content)

        url = f"/api/v1/files/{file_id}"

        if self.db:
            from app.models.file_metadata import FileMetadata
            from uuid import UUID
            try:
                fm = FileMetadata(
                    id=UUID(file_id),
                    name=file.filename or "unknown",
                    size=len(content),
                    content_type=file.content_type or "application/octet-stream",
                    path=file_path,
                    url=url,
                )
                self.db.add(fm)
                await self.db.commit()
                await self.db.refresh(fm)
                logger.info("[File] Saved to DB: %s (%d bytes, id=%s)", file.filename, len(content), file_id)
            except Exception:
                await self.db.rollback()
                # Clean up the file on disk if DB save failed
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise
        else:
            file_info = {
                "id": file_id,
                "name": file.filename or "unknown",
                "size": len(content),
                "type": file.content_type or "application/octet-stream",
                "path": file_path,
                "url": url,
            }
            _files[file_id] = file_info
            logger.info(f"[File] Saved (in-memory): {file.filename} ({len(content)} bytes, id={file_id})")

        return {
            "id": file_id,
            "name": file.filename or "unknown",
            "size": len(content),
            "type": file.content_type or "application/octet-stream",
            "url": url,
        }

    async def get_file_path(self, file_id: str) -> str | None:
        """Get file path by ID."""
        if self.db:
            from app.models.file_metadata import FileMetadata
            from uuid import UUID
            try:
                fm = await self.db.get(FileMetadata, UUID(file_id))
            except ValueError:
                return None
            return fm.path if fm else None

        file_info = _files.get(file_id)
        return file_info["path"] if file_info else None

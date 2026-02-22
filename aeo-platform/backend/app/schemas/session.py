"""Session schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.session import SessionStatus


class SessionBase(BaseModel):
    """Base session schema."""

    title: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    entity_id: UUID | None = None
    context: str | None = None
    extra_metadata: str | None = None


class SessionCreate(SessionBase):
    """Schema for creating a session."""

    pass


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    title: str | None = None
    status: SessionStatus | None = None
    entity_id: UUID | None = None
    context: str | None = None
    extra_metadata: str | None = None


class SessionResponse(SessionBase):
    """Schema for session response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class SessionListItem(BaseModel):
    """会话列表单项 schema。"""

    id: UUID
    title: str | None = None
    status: SessionStatus
    entity_id: UUID | None = None
    brand_name: str | None = None
    last_message_preview: str | None = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """会话列表响应 schema。"""

    sessions: list[SessionListItem]
    total: int

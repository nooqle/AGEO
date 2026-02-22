"""Message schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.message import MessageRole, MessageType


class MessageBase(BaseModel):
    """Base message schema."""

    role: MessageRole
    type: MessageType = MessageType.TEXT
    content: str


class MessageCreate(MessageBase):
    """Schema for creating a message."""

    session_id: UUID
    task: str | None = None
    plan: str | None = None
    action: str | None = None
    observation: str | None = None
    result: str | None = None
    output_type: str | None = None
    output_data: str | None = None
    parent_id: UUID | None = None
    extra_metadata: str | None = None


class MessageUpdate(BaseModel):
    """Schema for updating a message."""

    content: str | None = None
    extra_metadata: str | None = None


class MessageResponse(MessageBase):
    """Schema for message response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    sequence: int
    task: str | None
    plan: str | None
    action: str | None
    observation: str | None
    result: str | None
    output_type: str | None
    output_data: str | None
    parent_id: UUID | None
    extra_metadata: str | None
    created_at: datetime
    updated_at: datetime


class MessageListResponse(BaseModel):
    """Schema for message list response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: MessageRole
    type: MessageType
    content: str
    sequence: int
    created_at: datetime

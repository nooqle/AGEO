from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr | None
    phone: str | None = None
    is_active: bool
    status: str | None = None
    role: str | None = None
    job_title: str | None = None
    organization_id: UUID | None = None
    organization_name: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

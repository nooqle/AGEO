"""Entity schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class EntityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    domain: str = Field(..., min_length=1, max_length=500)
    industry: str = Field(..., min_length=1, max_length=200)
    description: str = ""


class EntityCreate(EntityBase):
    pass


class EntityUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    domain: str | None = None
    industry: str | None = None
    description: str | None = None


class EntityResponse(EntityBase):
    id: str
    last_analyzed: datetime | None = None
    status: str = "pending"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

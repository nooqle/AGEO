"""Flow topology recipes (org/entity scoped production-line presets)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.snapshot import JSONText


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FlowTopologyRecipe(Base):
    """Named topology recipe: org-shared or brand/project-scoped."""

    __tablename__ = "flow_topology_recipes"
    __table_args__ = (
        Index("ix_flow_topology_recipes_org", "organization_id"),
        Index("ix_flow_topology_recipes_entity", "entity_id"),
        Index(
            "ix_flow_topology_recipes_org_name",
            "organization_id",
            "entity_id",
            "name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # null = organization-wide recipe; set = brand/project scoped
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Same shape as flow_topologies.topology
    topology: Mapped[dict] = mapped_column(JSONText, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
        server_default=func.now(),
    )

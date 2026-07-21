"""Flow topology persistence (blueprint §2.3, task 3b-1.4).

Stores the user-authored canvas topology per entity so the orchestration layer
(topology resolver) can read it server-side. Previously localStorage-only
(3a); the backend becomes the source of truth and localStorage degrades to an
offline cache.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.snapshot import JSONText


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FlowTopologyRecord(Base):
    __tablename__ = "flow_topologies"
    __table_args__ = (
        Index("ix_flow_topologies_entity", "entity_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Whole FlowTopology document (app.workflow.node_contracts.FlowTopology):
    # {version, customNodes, customEdges, removedEdgeIds}
    topology: Mapped[dict] = mapped_column(JSONText, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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

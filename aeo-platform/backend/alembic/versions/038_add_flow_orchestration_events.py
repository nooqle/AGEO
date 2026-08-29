"""add flow orchestration events table

Revision ID: 038
Revises: 037
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "038"
down_revision: str | None = "037"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "flow_orchestration_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_flow_orch_events_entity_created",
        "flow_orchestration_events",
        ["entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flow_orch_events_entity_created",
        table_name="flow_orchestration_events",
    )
    op.drop_table("flow_orchestration_events")

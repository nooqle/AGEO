"""add flow topologies table

Revision ID: 036
Revises: 035
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "036"
down_revision: str | None = "035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "flow_topologies",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("topology", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_flow_topologies_entity", "flow_topologies", ["entity_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_flow_topologies_entity", table_name="flow_topologies")
    op.drop_table("flow_topologies")

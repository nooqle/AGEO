"""add flow topology recipes table

Revision ID: 039
Revises: 038
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "039"
down_revision: str | None = "038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "flow_topology_recipes",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("topology", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", UUID, nullable=True),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_flow_topology_recipes_org",
        "flow_topology_recipes",
        ["organization_id"],
    )
    op.create_index(
        "ix_flow_topology_recipes_entity",
        "flow_topology_recipes",
        ["entity_id"],
    )
    op.create_index(
        "ix_flow_topology_recipes_org_name",
        "flow_topology_recipes",
        ["organization_id", "entity_id", "name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flow_topology_recipes_org_name", table_name="flow_topology_recipes"
    )
    op.drop_index(
        "ix_flow_topology_recipes_entity", table_name="flow_topology_recipes"
    )
    op.drop_index("ix_flow_topology_recipes_org", table_name="flow_topology_recipes")
    op.drop_table("flow_topology_recipes")

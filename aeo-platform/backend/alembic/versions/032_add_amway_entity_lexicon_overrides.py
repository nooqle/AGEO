"""add amway entity lexicon overrides

Revision ID: 032
Revises: 031
Create Date: 2026-06-22 22:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032"
down_revision: str | None = "031"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "amway_entity_lexicon_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lexicon_entity_id", sa.String(length=120), nullable=False),
        sa.Column("canonical_name", sa.String(length=160), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("related_terms", sa.Text(), nullable=True),
        sa.Column("graph_policy", sa.Text(), nullable=True),
        sa.Column("source_policy", sa.Text(), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="approved",
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "lexicon_entity_id",
            name="uq_amway_entity_lexicon_override_entity_entry",
        ),
    )
    op.create_index(
        "ix_amway_entity_lexicon_override_entity_deleted",
        "amway_entity_lexicon_overrides",
        ["entity_id", "is_deleted"],
    )
    op.create_index(
        "ix_amway_entity_lexicon_override_type",
        "amway_entity_lexicon_overrides",
        ["entity_type"],
    )
    op.create_index(
        op.f("ix_amway_entity_lexicon_overrides_created_by_user_id"),
        "amway_entity_lexicon_overrides",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_amway_entity_lexicon_overrides_entity_id"),
        "amway_entity_lexicon_overrides",
        ["entity_id"],
    )
    op.create_index(
        op.f("ix_amway_entity_lexicon_overrides_organization_id"),
        "amway_entity_lexicon_overrides",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_amway_entity_lexicon_overrides_updated_by_user_id"),
        "amway_entity_lexicon_overrides",
        ["updated_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_amway_entity_lexicon_overrides_updated_by_user_id"),
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_index(
        op.f("ix_amway_entity_lexicon_overrides_organization_id"),
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_index(
        op.f("ix_amway_entity_lexicon_overrides_entity_id"),
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_index(
        op.f("ix_amway_entity_lexicon_overrides_created_by_user_id"),
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_index(
        "ix_amway_entity_lexicon_override_type",
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_index(
        "ix_amway_entity_lexicon_override_entity_deleted",
        table_name="amway_entity_lexicon_overrides",
    )
    op.drop_table("amway_entity_lexicon_overrides")

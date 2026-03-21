"""Add skill registry tables and skill-aware llm usage field.

Revision ID: 014
Revises: 013
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "llm_usage_records",
        sa.Column("skill_key", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "ix_llm_usage_records_skill_key",
        "llm_usage_records",
        ["skill_key"],
    )

    op.create_table(
        "skill_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("skill_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("executor_kind", sa.String(length=32), nullable=False),
        sa.Column("executor_ref", sa.String(length=120), nullable=False),
        sa.Column("template_skill_key", sa.String(length=120), nullable=True),
        sa.Column("intent_signals", sa.Text(), nullable=False),
        sa.Column("prerequisites", sa.Text(), nullable=False),
        sa.Column("artifact_types", sa.Text(), nullable=False),
        sa.Column("default_params", sa.Text(), nullable=True),
        sa.Column("prompt_overlay", sa.Text(), nullable=True),
        sa.Column("cost_class", sa.String(length=16), nullable=False),
        sa.Column("latency_class", sa.String(length=16), nullable=False),
        sa.Column("confirmation_policy", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint("skill_key", name="uq_skill_definitions_skill_key"),
    )
    op.create_index(
        "ix_skill_definitions_skill_key",
        "skill_definitions",
        ["skill_key"],
    )
    op.create_index(
        "ix_skill_definitions_executor_ref",
        "skill_definitions",
        ["executor_ref"],
    )
    op.create_index(
        "ix_skill_definitions_is_builtin",
        "skill_definitions",
        ["is_builtin"],
    )

    op.create_table(
        "skill_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skill_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),
    )
    op.create_index(
        "ix_skill_versions_skill_id",
        "skill_versions",
        ["skill_id"],
    )

    op.create_table(
        "skill_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skill_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_kind", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("scope_ref", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint(
            "skill_id",
            "scope_kind",
            "scope_ref",
            name="uq_skill_assignments_scope",
        ),
    )
    op.create_index(
        "ix_skill_assignments_skill_id",
        "skill_assignments",
        ["skill_id"],
    )

    op.alter_column("skill_definitions", "description", server_default=None)
    op.alter_column("skill_definitions", "enabled", server_default=None)
    op.alter_column("skill_definitions", "is_builtin", server_default=None)
    op.alter_column("skill_definitions", "version", server_default=None)
    op.alter_column("skill_definitions", "created_at", server_default=None)
    op.alter_column("skill_definitions", "updated_at", server_default=None)
    op.alter_column("skill_versions", "created_at", server_default=None)
    op.alter_column("skill_assignments", "scope_kind", server_default=None)
    op.alter_column("skill_assignments", "enabled", server_default=None)
    op.alter_column("skill_assignments", "created_at", server_default=None)
    op.alter_column("skill_assignments", "updated_at", server_default=None)


def downgrade():
    op.drop_index("ix_skill_assignments_skill_id", table_name="skill_assignments")
    op.drop_table("skill_assignments")

    op.drop_index("ix_skill_versions_skill_id", table_name="skill_versions")
    op.drop_table("skill_versions")

    op.drop_index("ix_skill_definitions_is_builtin", table_name="skill_definitions")
    op.drop_index("ix_skill_definitions_executor_ref", table_name="skill_definitions")
    op.drop_index("ix_skill_definitions_skill_key", table_name="skill_definitions")
    op.drop_table("skill_definitions")

    op.drop_index("ix_llm_usage_records_skill_key", table_name="llm_usage_records")
    op.drop_column("llm_usage_records", "skill_key")


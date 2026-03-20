"""Add llm_usage_records table and task usage aggregates.

Revision ID: 007
Revises: 006
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("llm_estimated_cost", sa.Float(), nullable=False, server_default="0"),
    )

    op.create_table(
        "llm_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("step", sa.String(length=50), nullable=True),
        sa.Column("step_name", sa.String(length=100), nullable=True),
        sa.Column("raw_session_id", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="CNY"),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_llm_usage_records_task_id",
        "llm_usage_records",
        ["task_id"],
    )
    op.create_index(
        "ix_llm_usage_records_session_id",
        "llm_usage_records",
        ["session_id"],
    )
    op.create_index(
        "ix_llm_usage_records_provider",
        "llm_usage_records",
        ["provider"],
    )
    op.create_index(
        "ix_llm_usage_records_model_name",
        "llm_usage_records",
        ["model_name"],
    )
    op.create_index(
        "ix_llm_usage_records_step",
        "llm_usage_records",
        ["step"],
    )

    op.alter_column("analysis_tasks", "llm_call_count", server_default=None)
    op.alter_column("analysis_tasks", "llm_prompt_tokens", server_default=None)
    op.alter_column("analysis_tasks", "llm_completion_tokens", server_default=None)
    op.alter_column("analysis_tasks", "llm_total_tokens", server_default=None)
    op.alter_column("analysis_tasks", "llm_estimated_cost", server_default=None)


def downgrade():
    op.drop_index("ix_llm_usage_records_step", table_name="llm_usage_records")
    op.drop_index("ix_llm_usage_records_model_name", table_name="llm_usage_records")
    op.drop_index("ix_llm_usage_records_provider", table_name="llm_usage_records")
    op.drop_index("ix_llm_usage_records_session_id", table_name="llm_usage_records")
    op.drop_index("ix_llm_usage_records_task_id", table_name="llm_usage_records")
    op.drop_table("llm_usage_records")

    op.drop_column("analysis_tasks", "llm_estimated_cost")
    op.drop_column("analysis_tasks", "llm_total_tokens")
    op.drop_column("analysis_tasks", "llm_completion_tokens")
    op.drop_column("analysis_tasks", "llm_prompt_tokens")
    op.drop_column("analysis_tasks", "llm_call_count")

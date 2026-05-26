"""add brand intelligence run center

Revision ID: 023
Revises: 022
Create Date: 2026-05-25 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: str | None = "022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_intelligence_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_surface", sa.String(length=80), nullable=False),
        sa.Column("origin_event_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("run_goal", sa.Text(), nullable=False),
        sa.Column("analysis_mode", sa.String(length=40), nullable=False),
        sa.Column("input_scope", sa.Text(), nullable=True),
        sa.Column("sample_scope", sa.Text(), nullable=True),
        sa.Column("output_refs", sa.Text(), nullable=True),
        sa.Column("requires_user_action", sa.Boolean(), nullable=False),
        sa.Column("user_action_type", sa.String(length=80), nullable=True),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_task_id"], ["analysis_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["origin_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in [
        ("ix_brand_intelligence_runs_entity_id", ["entity_id"]),
        ("ix_brand_intelligence_runs_created_by_user_id", ["created_by_user_id"]),
        ("ix_brand_intelligence_runs_origin_session_id", ["origin_session_id"]),
        ("ix_brand_intelligence_runs_analysis_task_id", ["analysis_task_id"]),
        ("ix_brand_intelligence_runs_status", ["status"]),
        (
            "ix_brand_intelligence_runs_entity_status",
            ["entity_id", "status"],
        ),
        (
            "ix_brand_intelligence_runs_entity_updated",
            ["entity_id", "updated_at"],
        ),
        (
            "ix_brand_intelligence_runs_analysis_task",
            ["analysis_task_id"],
        ),
        (
            "ix_brand_intelligence_runs_origin_event",
            ["origin_event_id"],
        ),
        (
            "ix_brand_intelligence_runs_requires_user",
            ["requires_user_action"],
        ),
    ]:
        op.create_index(index_name, "brand_intelligence_runs", columns)


def downgrade() -> None:
    op.drop_table("brand_intelligence_runs")

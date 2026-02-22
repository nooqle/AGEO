"""Add analysis_tasks table

Revision ID: 003
Revises: 002
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    # Create TaskStatus enum type
    task_status_enum = sa.Enum(
        "pending", "running", "completed", "failed", "cancelled",
        name="taskstatus",
    )
    task_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "analysis_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("brand_name", sa.String(255), nullable=False),
        sa.Column(
            "status",
            task_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("current_stage", sa.String(10), nullable=False, server_default=""),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String(255), nullable=False, server_default=""),
        # JSON stored as Text (matches JSONText type used in the model)
        sa.Column("stage_results_cache", sa.Text, nullable=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_stage", sa.String(10), nullable=True),
        sa.Column("notify_on_complete", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes matching the SQLAlchemy model index=True columns
    op.create_index("ix_analysis_tasks_user_id", "analysis_tasks", ["user_id"])
    op.create_index("ix_analysis_tasks_session_id", "analysis_tasks", ["session_id"])
    op.create_index("ix_analysis_tasks_entity_id", "analysis_tasks", ["entity_id"])
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"])


def downgrade():
    op.drop_index("ix_analysis_tasks_status", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_entity_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_session_id", table_name="analysis_tasks")
    op.drop_index("ix_analysis_tasks_user_id", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")
    op.execute("DROP TYPE IF EXISTS taskstatus")

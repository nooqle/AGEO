"""Add durable task_runs table for unified job submission.

Revision ID: 010
Revises: 009
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    task_run_status_enum = postgresql.ENUM(
        "queued",
        "claimed",
        "running",
        "waiting_input",
        "cancelling",
        "cancelled",
        "failed",
        "completed",
        name="taskrunstatus",
        create_type=False,
    )
    task_run_status_enum.create(op.get_bind(), checkfirst=True)

    task_run_kind_enum = postgresql.ENUM(
        "initial",
        "scheduled",
        "resume_after_input",
        "retry",
        "follow_up",
        name="taskrunkind",
        create_type=False,
    )
    task_run_kind_enum.create(op.get_bind(), checkfirst=True)

    task_trigger_source_enum = postgresql.ENUM(
        "websocket",
        "scheduler",
        "messages_api",
        "system_retry",
        name="tasktriggersource",
        create_type=False,
    )
    task_trigger_source_enum.create(op.get_bind(), checkfirst=True)

    executor_kind_enum = postgresql.ENUM(
        "local_workflow",
        "sandbox_workflow",
        "celery_fetch",
        "external",
        name="executorkind",
        create_type=False,
    )
    executor_kind_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_kind",
            task_run_kind_enum,
            nullable=False,
            server_default="initial",
        ),
        sa.Column(
            "trigger_source",
            task_trigger_source_enum,
            nullable=False,
        ),
        sa.Column(
            "executor_kind",
            executor_kind_enum,
            nullable=False,
            server_default="local_workflow",
        ),
        sa.Column(
            "status",
            task_run_status_enum,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("executor_ref", sa.String(length=255), nullable=True),
        sa.Column("checkpoint_stage", sa.String(length=50), nullable=True),
        sa.Column("checkpoint_payload_ref", sa.String(length=255), nullable=True),
        sa.Column("error_kind", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_task_runs_task_id", "task_runs", ["task_id"])
    op.create_index("ix_task_runs_trigger_source", "task_runs", ["trigger_source"])
    op.create_index("ix_task_runs_executor_kind", "task_runs", ["executor_kind"])
    op.create_index("ix_task_runs_status", "task_runs", ["status"])
    op.create_index("ix_task_runs_submitted_at", "task_runs", ["submitted_at"])
    op.create_index(
        "ix_task_runs_status_submitted_at",
        "task_runs",
        ["status", "submitted_at"],
    )

    op.alter_column("task_runs", "run_kind", server_default=None)
    op.alter_column("task_runs", "executor_kind", server_default=None)
    op.alter_column("task_runs", "status", server_default=None)
    op.alter_column("task_runs", "attempt_no", server_default=None)
    op.alter_column("task_runs", "priority", server_default=None)


def downgrade():
    op.drop_index("ix_task_runs_status_submitted_at", table_name="task_runs")
    op.drop_index("ix_task_runs_submitted_at", table_name="task_runs")
    op.drop_index("ix_task_runs_status", table_name="task_runs")
    op.drop_index("ix_task_runs_executor_kind", table_name="task_runs")
    op.drop_index("ix_task_runs_trigger_source", table_name="task_runs")
    op.drop_index("ix_task_runs_task_id", table_name="task_runs")
    op.drop_table("task_runs")

    op.execute("DROP TYPE IF EXISTS executorkind")
    op.execute("DROP TYPE IF EXISTS tasktriggersource")
    op.execute("DROP TYPE IF EXISTS taskrunkind")
    op.execute("DROP TYPE IF EXISTS taskrunstatus")

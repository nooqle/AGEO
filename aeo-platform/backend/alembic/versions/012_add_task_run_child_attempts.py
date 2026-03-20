"""Add durable child attempts for task runs.

Revision ID: 012
Revises: 011
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    child_kind_enum = postgresql.ENUM(
        "a4_browser_action",
        name="taskrunchildattemptkind",
        create_type=False,
    )
    child_kind_enum.create(op.get_bind(), checkfirst=True)

    child_status_enum = postgresql.ENUM(
        "waiting_input",
        "completed",
        "skipped",
        "cancelled",
        "failed",
        "expired",
        name="taskrunchildattemptstatus",
        create_type=False,
    )
    child_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_run_child_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_kind",
            child_kind_enum,
            nullable=False,
            server_default="a4_browser_action",
        ),
        sa.Column(
            "status",
            child_status_enum,
            nullable=False,
            server_default="waiting_input",
        ),
        sa.Column("step", sa.String(length=50), nullable=False, server_default="A4"),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("action_hint", sa.String(length=255), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_task_run_child_attempts_run_id",
        "task_run_child_attempts",
        ["task_run_id"],
    )
    op.create_index(
        "ix_task_run_child_attempts_status",
        "task_run_child_attempts",
        ["status"],
    )
    op.create_index(
        "ix_task_run_child_attempts_request_id",
        "task_run_child_attempts",
        ["request_id"],
        unique=True,
    )

    op.alter_column("task_run_child_attempts", "child_kind", server_default=None)
    op.alter_column("task_run_child_attempts", "status", server_default=None)
    op.alter_column("task_run_child_attempts", "step", server_default=None)
    op.alter_column("task_run_child_attempts", "progress", server_default=None)


def downgrade():
    op.drop_index(
        "ix_task_run_child_attempts_request_id",
        table_name="task_run_child_attempts",
    )
    op.drop_index(
        "ix_task_run_child_attempts_status",
        table_name="task_run_child_attempts",
    )
    op.drop_index(
        "ix_task_run_child_attempts_run_id",
        table_name="task_run_child_attempts",
    )
    op.drop_table("task_run_child_attempts")

    op.execute("DROP TYPE IF EXISTS taskrunchildattemptstatus")
    op.execute("DROP TYPE IF EXISTS taskrunchildattemptkind")

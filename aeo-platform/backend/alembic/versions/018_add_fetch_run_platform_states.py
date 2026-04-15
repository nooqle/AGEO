"""add fetch_run_platform_states

Revision ID: 018
Revises: 017
Create Date: 2026-04-14 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | None = "017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fetch_run_platform_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("auth_state", sa.String(length=32), nullable=False),
        sa.Column("latest_packet", sa.Text(), nullable=True),
        sa.Column("latest_takeover_request_id", sa.String(length=120), nullable=True),
        sa.Column(
            "latest_blocking_fingerprint",
            sa.String(length=120),
            nullable=True,
        ),
        sa.Column("artifact_write_status", sa.String(length=32), nullable=True),
        sa.Column("error_kind", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("timing_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["analysis_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_fetch_run_platform_states_run_platform",
        "fetch_run_platform_states",
        ["task_run_id", "platform"],
        unique=True,
    )
    op.create_index(
        "ix_fetch_run_platform_states_task_id",
        "fetch_run_platform_states",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_fetch_run_platform_states_session_id",
        "fetch_run_platform_states",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_fetch_run_platform_states_status",
        "fetch_run_platform_states",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_fetch_run_platform_states_platform",
        "fetch_run_platform_states",
        ["platform"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fetch_run_platform_states_platform",
        table_name="fetch_run_platform_states",
    )
    op.drop_index(
        "ix_fetch_run_platform_states_status",
        table_name="fetch_run_platform_states",
    )
    op.drop_index(
        "ix_fetch_run_platform_states_session_id",
        table_name="fetch_run_platform_states",
    )
    op.drop_index(
        "ix_fetch_run_platform_states_task_id",
        table_name="fetch_run_platform_states",
    )
    op.drop_index(
        "uq_fetch_run_platform_states_run_platform",
        table_name="fetch_run_platform_states",
    )
    op.drop_table("fetch_run_platform_states")

"""Enforce single live runtime attempt per analysis task.

Revision ID: 011
Revises: 010
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        WITH ranked_live_runs AS (
            SELECT
                id,
                status,
                ROW_NUMBER() OVER (
                    PARTITION BY task_id
                    ORDER BY submitted_at DESC, id DESC
                ) AS row_num
            FROM task_runs
            WHERE status IN ('queued', 'claimed', 'running', 'waiting_input', 'cancelling')
        )
        UPDATE task_runs
        SET
            status = CASE
                WHEN ranked_live_runs.status = 'waiting_input'
                    THEN 'completed'::taskrunstatus
                ELSE 'cancelled'::taskrunstatus
            END,
            cancel_requested_at = CASE
                WHEN ranked_live_runs.status = 'waiting_input'
                    THEN task_runs.cancel_requested_at
                ELSE COALESCE(task_runs.cancel_requested_at, NOW())
            END,
            finished_at = COALESCE(task_runs.finished_at, NOW()),
            heartbeat_at = COALESCE(task_runs.heartbeat_at, NOW())
        FROM ranked_live_runs
        WHERE task_runs.id = ranked_live_runs.id
          AND ranked_live_runs.row_num > 1
        """
    )

    op.create_index(
        "uq_task_runs_live_per_task",
        "task_runs",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'claimed', 'running', 'waiting_input', 'cancelling')"
        ),
    )


def downgrade():
    op.drop_index("uq_task_runs_live_per_task", table_name="task_runs")

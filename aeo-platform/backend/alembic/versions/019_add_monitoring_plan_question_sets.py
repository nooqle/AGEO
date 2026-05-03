"""add monitoring plan question sets

Revision ID: 019
Revises: 018
Create Date: 2026-04-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: str | None = "018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_question_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("questions", sa.Text(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_task_id"], ["analysis_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_question_sets_user_id",
        "monitoring_question_sets",
        ["user_id"],
    )
    op.create_index(
        "ix_monitoring_question_sets_entity_id",
        "monitoring_question_sets",
        ["entity_id"],
    )
    op.create_index(
        "ix_monitoring_question_sets_monitor_mode",
        "monitoring_question_sets",
        ["monitor_mode"],
    )
    op.create_index(
        "ix_monitoring_question_sets_status",
        "monitoring_question_sets",
        ["status"],
    )
    op.create_index(
        "ix_monitoring_question_sets_source_session_id",
        "monitoring_question_sets",
        ["source_session_id"],
    )
    op.create_index(
        "ix_monitoring_question_sets_source_task_id",
        "monitoring_question_sets",
        ["source_task_id"],
    )

    op.create_table(
        "monitoring_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("question_set_ids", sa.Text(), nullable=True),
        sa.Column("endpoint_ids", sa.Text(), nullable=True),
        sa.Column("run_policy", sa.String(length=32), nullable=False),
        sa.Column("frequency", sa.String(length=32), nullable=False),
        sa.Column("preferred_hour", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_plans_user_id", "monitoring_plans", ["user_id"])
    op.create_index("ix_monitoring_plans_entity_id", "monitoring_plans", ["entity_id"])
    op.create_index(
        "ix_monitoring_plans_monitor_mode", "monitoring_plans", ["monitor_mode"]
    )
    op.create_index("ix_monitoring_plans_status", "monitoring_plans", ["status"])

    op.add_column(
        "monitoring_schedules",
        sa.Column("monitoring_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "monitoring_schedules",
        sa.Column("monitor_mode", sa.String(length=32), nullable=False, server_default="panorama"),
    )
    op.add_column(
        "monitoring_schedules",
        sa.Column("question_set_ids", sa.Text(), nullable=True),
    )
    op.add_column(
        "monitoring_schedules",
        sa.Column("endpoint_ids", sa.Text(), nullable=True),
    )
    op.add_column(
        "monitoring_schedules",
        sa.Column("run_policy", sa.String(length=32), nullable=False, server_default="quick"),
    )
    op.create_foreign_key(
        "fk_monitoring_schedules_monitoring_plan_id",
        "monitoring_schedules",
        "monitoring_plans",
        ["monitoring_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_monitoring_schedules_monitoring_plan_id",
        "monitoring_schedules",
        ["monitoring_plan_id"],
    )
    op.create_index(
        "ix_monitoring_schedules_monitor_mode",
        "monitoring_schedules",
        ["monitor_mode"],
    )

    op.create_table(
        "monitoring_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_policy", sa.String(length=32), nullable=False),
        sa.Column("monitor_mode", sa.String(length=32), nullable=False),
        sa.Column("endpoint_ids", sa.Text(), nullable=True),
        sa.Column("question_set_ids", sa.Text(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_stage", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["monitoring_plans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["monitoring_schedules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["analysis_snapshots.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, column_name in [
        ("ix_monitoring_runs_user_id", "user_id"),
        ("ix_monitoring_runs_entity_id", "entity_id"),
        ("ix_monitoring_runs_plan_id", "plan_id"),
        ("ix_monitoring_runs_schedule_id", "schedule_id"),
        ("ix_monitoring_runs_task_id", "task_id"),
        ("ix_monitoring_runs_task_run_id", "task_run_id"),
        ("ix_monitoring_runs_snapshot_id", "snapshot_id"),
        ("ix_monitoring_runs_status", "status"),
        ("ix_monitoring_runs_monitor_mode", "monitor_mode"),
    ]:
        op.create_index(index_name, "monitoring_runs", [column_name])

    op.create_table(
        "monitoring_evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitoring_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", sa.String(length=120), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("endpoint_id", sa.String(length=64), nullable=False),
        sa.Column("endpoint_label", sa.String(length=80), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("fetch_method", sa.String(length=32), nullable=False),
        sa.Column("answer_status", sa.String(length=32), nullable=False),
        sa.Column("cited_domains", sa.Text(), nullable=True),
        sa.Column("raw_evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["monitoring_run_id"], ["monitoring_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["monitoring_plans.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_evidence_records_monitoring_run_id",
        "monitoring_evidence_records",
        ["monitoring_run_id"],
    )
    op.create_index(
        "ix_monitoring_evidence_records_plan_id",
        "monitoring_evidence_records",
        ["plan_id"],
    )
    op.create_index(
        "ix_monitoring_evidence_records_entity_id",
        "monitoring_evidence_records",
        ["entity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitoring_evidence_records_entity_id",
        table_name="monitoring_evidence_records",
    )
    op.drop_index(
        "ix_monitoring_evidence_records_plan_id",
        table_name="monitoring_evidence_records",
    )
    op.drop_index(
        "ix_monitoring_evidence_records_monitoring_run_id",
        table_name="monitoring_evidence_records",
    )
    op.drop_table("monitoring_evidence_records")

    for index_name in [
        "ix_monitoring_runs_monitor_mode",
        "ix_monitoring_runs_status",
        "ix_monitoring_runs_snapshot_id",
        "ix_monitoring_runs_task_run_id",
        "ix_monitoring_runs_task_id",
        "ix_monitoring_runs_schedule_id",
        "ix_monitoring_runs_plan_id",
        "ix_monitoring_runs_entity_id",
        "ix_monitoring_runs_user_id",
    ]:
        op.drop_index(index_name, table_name="monitoring_runs")
    op.drop_table("monitoring_runs")

    op.drop_index(
        "ix_monitoring_schedules_monitor_mode", table_name="monitoring_schedules"
    )
    op.drop_index(
        "ix_monitoring_schedules_monitoring_plan_id",
        table_name="monitoring_schedules",
    )
    op.drop_constraint(
        "fk_monitoring_schedules_monitoring_plan_id",
        "monitoring_schedules",
        type_="foreignkey",
    )
    op.drop_column("monitoring_schedules", "run_policy")
    op.drop_column("monitoring_schedules", "endpoint_ids")
    op.drop_column("monitoring_schedules", "question_set_ids")
    op.drop_column("monitoring_schedules", "monitor_mode")
    op.drop_column("monitoring_schedules", "monitoring_plan_id")

    op.drop_index("ix_monitoring_plans_status", table_name="monitoring_plans")
    op.drop_index("ix_monitoring_plans_monitor_mode", table_name="monitoring_plans")
    op.drop_index("ix_monitoring_plans_entity_id", table_name="monitoring_plans")
    op.drop_index("ix_monitoring_plans_user_id", table_name="monitoring_plans")
    op.drop_table("monitoring_plans")

    op.drop_index(
        "ix_monitoring_question_sets_source_task_id",
        table_name="monitoring_question_sets",
    )
    op.drop_index(
        "ix_monitoring_question_sets_source_session_id",
        table_name="monitoring_question_sets",
    )
    op.drop_index(
        "ix_monitoring_question_sets_status",
        table_name="monitoring_question_sets",
    )
    op.drop_index(
        "ix_monitoring_question_sets_monitor_mode",
        table_name="monitoring_question_sets",
    )
    op.drop_index(
        "ix_monitoring_question_sets_entity_id",
        table_name="monitoring_question_sets",
    )
    op.drop_index(
        "ix_monitoring_question_sets_user_id",
        table_name="monitoring_question_sets",
    )
    op.drop_table("monitoring_question_sets")

"""Add monitoring_schedules, monitoring_alerts tables and alter analysis_tasks

Revision ID: 004
Revises: 003
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # --- 1. Create ScheduleFrequency and ScheduleStatus enum types ---
    schedule_frequency_enum = sa.Enum(
        "daily", "weekly", "biweekly", "monthly",
        name="schedulefrequency",
    )
    schedule_frequency_enum.create(op.get_bind(), checkfirst=True)

    schedule_status_enum = sa.Enum(
        "active", "paused", "completed", "error",
        name="schedulestatus",
    )
    schedule_status_enum.create(op.get_bind(), checkfirst=True)

    # --- 2. Create monitoring_schedules table ---
    op.create_table(
        "monitoring_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "frequency", schedule_frequency_enum,
            nullable=False, server_default="weekly",
        ),
        sa.Column(
            "status", schedule_status_enum,
            nullable=False, server_default="active",
        ),
        sa.Column("preferred_hour", sa.Integer, nullable=False, server_default="3"),
        sa.Column(
            "timezone", sa.String(50),
            nullable=False, server_default="Asia/Shanghai",
        ),
        sa.Column("platforms", sa.Text, nullable=True),
        sa.Column(
            "alert_on_significant_change", sa.Boolean,
            nullable=False, server_default="true",
        ),
        sa.Column(
            "alert_threshold_bwvs", sa.Float,
            nullable=False, server_default="10.0",
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("total_runs", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "consecutive_failures", sa.Integer,
            nullable=False, server_default="0",
        ),
        sa.Column("max_failures", sa.Integer, nullable=False, server_default="3"),
        sa.Column("max_runs", sa.Integer, nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
    )
    op.create_index(
        "ix_monitoring_schedules_user_id",
        "monitoring_schedules", ["user_id"],
    )
    op.create_index(
        "ix_monitoring_schedules_entity_id",
        "monitoring_schedules", ["entity_id"],
    )
    op.create_index(
        "ix_monitoring_schedules_status",
        "monitoring_schedules", ["status"],
    )
    op.create_index(
        "ix_monitoring_schedules_next_run_at",
        "monitoring_schedules", ["next_run_at"],
    )

    # --- 3. Create AlertSeverity and AlertStatus enum types ---
    alert_severity_enum = sa.Enum(
        "low", "medium", "high", "critical",
        name="alertseverity",
    )
    alert_severity_enum.create(op.get_bind(), checkfirst=True)

    alert_status_enum = sa.Enum(
        "unread", "read", "dismissed", "actioned",
        name="alertstatus",
    )
    alert_status_enum.create(op.get_bind(), checkfirst=True)

    # --- 4. Create monitoring_alerts table ---
    op.create_table(
        "monitoring_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", alert_severity_enum, nullable=False),
        sa.Column(
            "status", alert_status_enum,
            nullable=False, server_default="unread",
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("previous_value", sa.Float, nullable=True),
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("change_absolute", sa.Float, nullable=False),
        sa.Column("change_percentage", sa.Float, nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_monitoring_alerts_user_id",
        "monitoring_alerts", ["user_id"],
    )
    op.create_index(
        "ix_monitoring_alerts_entity_id",
        "monitoring_alerts", ["entity_id"],
    )
    op.create_index(
        "ix_monitoring_alerts_severity",
        "monitoring_alerts", ["severity"],
    )
    op.create_index(
        "ix_monitoring_alerts_status",
        "monitoring_alerts", ["status"],
    )

    # --- 5. Alter analysis_tasks: session_id nullable + add monitoring_schedule_id ---
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.alter_column("session_id", nullable=True)
        batch_op.add_column(
            sa.Column(
                "monitoring_schedule_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        batch_op.create_foreign_key(
            "fk_analysis_tasks_monitoring_schedule_id",
            "monitoring_schedules",
            ["monitoring_schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_analysis_tasks_monitoring_schedule_id",
            ["monitoring_schedule_id"],
        )


def downgrade():
    # --- Reverse analysis_tasks changes ---
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.drop_index("ix_analysis_tasks_monitoring_schedule_id")
        batch_op.drop_constraint(
            "fk_analysis_tasks_monitoring_schedule_id", type_="foreignkey"
        )
        batch_op.drop_column("monitoring_schedule_id")
        batch_op.alter_column("session_id", nullable=False)

    # --- Drop monitoring_alerts ---
    op.drop_index("ix_monitoring_alerts_status", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_severity", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_entity_id", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_user_id", table_name="monitoring_alerts")
    op.drop_table("monitoring_alerts")

    # --- Drop monitoring_schedules ---
    op.drop_index(
        "ix_monitoring_schedules_next_run_at",
        table_name="monitoring_schedules",
    )
    op.drop_index(
        "ix_monitoring_schedules_status",
        table_name="monitoring_schedules",
    )
    op.drop_index(
        "ix_monitoring_schedules_entity_id",
        table_name="monitoring_schedules",
    )
    op.drop_index(
        "ix_monitoring_schedules_user_id",
        table_name="monitoring_schedules",
    )
    op.drop_table("monitoring_schedules")

    # --- Drop enum types ---
    op.execute("DROP TYPE IF EXISTS alertstatus")
    op.execute("DROP TYPE IF EXISTS alertseverity")
    op.execute("DROP TYPE IF EXISTS schedulestatus")
    op.execute("DROP TYPE IF EXISTS schedulefrequency")

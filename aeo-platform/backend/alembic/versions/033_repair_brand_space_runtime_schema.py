"""repair brand space runtime schema drift

Revision ID: 033
Revises: 032
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "033"
down_revision: str | None = "032"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(bind: sa.engine.Connection, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind: sa.engine.Connection, table_name: str, column_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def _has_index(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    return any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def _create_index_if_missing(
    bind: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    if not _has_index(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _create_board_runs(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "board_runs"):
        if not _has_column(bind, "board_runs", "last_synced_at"):
            op.add_column(
                "board_runs",
                sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            )
        return

    op.create_table(
        "board_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "brand_intelligence_run_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("analysis_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("board_id", sa.String(length=120), nullable=False),
        sa.Column("template_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("is_scaffold", sa.Boolean(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("input_scope", sa.Text(), nullable=True),
        sa.Column("active_node_ids", sa.Text(), nullable=True),
        sa.Column("output_refs", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_task_id"], ["analysis_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["brand_intelligence_run_id"],
            ["brand_intelligence_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_board_node_runs(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "board_node_runs"):
        return
    op.create_table(
        "board_node_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("board_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=False),
        sa.Column("node_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("output_artifact_ids", sa.Text(), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_run_id"], ["board_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "board_run_id", "node_id", name="uq_board_node_runs_run_node"
        ),
    )


def _create_board_artifacts(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "board_artifacts"):
        return
    op.create_table(
        "board_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_key", sa.String(length=120), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("board_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_run_id"], ["board_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["node_run_id"], ["board_node_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "board_run_id", "artifact_key", name="uq_board_artifacts_run_key"
        ),
    )


def _create_board_runtime_events(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "board_runtime_events"):
        return
    op.create_table(
        "board_runtime_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("board_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_run_id"], ["board_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_graph_updates(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "graph_updates"):
        return
    op.create_table(
        "graph_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("board_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_graph_version", sa.String(length=80), nullable=False),
        sa.Column("after_graph_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("graph_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_run_id"], ["board_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_graph_patches(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "graph_patches"):
        return
    op.create_table(
        "graph_patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_update_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patch_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_object_type", sa.String(length=80), nullable=False),
        sa.Column("affected_object_id", sa.String(length=255), nullable=False),
        sa.Column("relation_type", sa.String(length=120), nullable=False),
        sa.Column("connection_strength", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("sentiment_or_risk_score", sa.Float(), nullable=True),
        sa.Column("before_payload", sa.Text(), nullable=True),
        sa.Column("after_payload", sa.Text(), nullable=True),
        sa.Column("score_breakdown", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["graph_update_id"], ["graph_updates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_report_guardrails(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "report_guardrail_results"):
        return
    op.create_table(
        "report_guardrail_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_update_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("guardrail_key", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_update_id"], ["graph_updates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id"], ["brand_report_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_missing_indexes(bind: sa.engine.Connection) -> None:
    if _has_table(bind, "board_runs"):
        _create_index_if_missing(
            bind, "ix_board_runs_analysis_task_id", "board_runs", ["analysis_task_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_board_runs_brand_intelligence_run_id",
            "board_runs",
            ["brand_intelligence_run_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_board_runs_created_by_user_id",
            "board_runs",
            ["created_by_user_id"],
        )
        _create_index_if_missing(
            bind, "ix_board_runs_entity_id", "board_runs", ["entity_id"]
        )
        _create_index_if_missing(
            bind, "ix_board_runs_entity_status", "board_runs", ["entity_id", "status"]
        )
        _create_index_if_missing(
            bind,
            "ix_board_runs_entity_updated",
            "board_runs",
            ["entity_id", "updated_at"],
        )
        _create_index_if_missing(bind, "ix_board_runs_status", "board_runs", ["status"])
    if _has_table(bind, "board_node_runs"):
        _create_index_if_missing(
            bind, "ix_board_node_runs_board_run_id", "board_node_runs", ["board_run_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_board_node_runs_board_status",
            "board_node_runs",
            ["board_run_id", "status"],
        )
    if _has_table(bind, "board_artifacts"):
        _create_index_if_missing(
            bind,
            "ix_board_artifacts_artifact_type",
            "board_artifacts",
            ["artifact_type"],
        )
        _create_index_if_missing(
            bind, "ix_board_artifacts_board_run_id", "board_artifacts", ["board_run_id"]
        )
        _create_index_if_missing(
            bind, "ix_board_artifacts_entity_id", "board_artifacts", ["entity_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_board_artifacts_entity_type",
            "board_artifacts",
            ["entity_id", "artifact_type"],
        )
        _create_index_if_missing(
            bind, "ix_board_artifacts_node_run_id", "board_artifacts", ["node_run_id"]
        )
    if _has_table(bind, "board_runtime_events"):
        _create_index_if_missing(
            bind,
            "ix_board_runtime_events_board_run_id",
            "board_runtime_events",
            ["board_run_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_board_runtime_events_entity_created",
            "board_runtime_events",
            ["entity_id", "created_at"],
        )
        _create_index_if_missing(
            bind,
            "ix_board_runtime_events_entity_id",
            "board_runtime_events",
            ["entity_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_board_runtime_events_run_sequence",
            "board_runtime_events",
            ["board_run_id", "sequence"],
        )
    if _has_table(bind, "graph_updates"):
        _create_index_if_missing(
            bind, "ix_graph_updates_board_run_id", "graph_updates", ["board_run_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_graph_updates_created_by_user_id",
            "graph_updates",
            ["created_by_user_id"],
        )
        _create_index_if_missing(
            bind, "ix_graph_updates_entity_id", "graph_updates", ["entity_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_graph_updates_entity_status",
            "graph_updates",
            ["entity_id", "status"],
        )
    if _has_table(bind, "graph_patches"):
        _create_index_if_missing(
            bind, "ix_graph_patches_entity_id", "graph_patches", ["entity_id"]
        )
        _create_index_if_missing(
            bind,
            "ix_graph_patches_entity_type",
            "graph_patches",
            ["entity_id", "patch_type"],
        )
        _create_index_if_missing(
            bind,
            "ix_graph_patches_graph_update_id",
            "graph_patches",
            ["graph_update_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_graph_patches_reviewed_by_user_id",
            "graph_patches",
            ["reviewed_by_user_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_graph_patches_update_status",
            "graph_patches",
            ["graph_update_id", "status"],
        )
    if _has_table(bind, "report_guardrail_results"):
        _create_index_if_missing(
            bind,
            "ix_report_guardrails_graph_update_id",
            "report_guardrail_results",
            ["graph_update_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_report_guardrails_report_version_id",
            "report_guardrail_results",
            ["report_version_id"],
        )
        _create_index_if_missing(
            bind,
            "ix_report_guardrails_update_severity",
            "report_guardrail_results",
            ["graph_update_id", "severity"],
        )


def upgrade() -> None:
    bind = op.get_bind()
    _create_board_runs(bind)
    _create_board_node_runs(bind)
    _create_board_artifacts(bind)
    _create_board_runtime_events(bind)
    _create_graph_updates(bind)
    _create_graph_patches(bind)
    _create_report_guardrails(bind)
    _create_missing_indexes(bind)


def downgrade() -> None:
    pass

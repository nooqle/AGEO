"""add amway circle tracking tables

Revision ID: 035
Revises: 034
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "035"
down_revision: str | None = "034"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "amway_circle_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column("brand_intelligence_run_id", UUID, nullable=True),
        sa.Column("analysis_task_id", UUID, nullable=True),
        sa.Column("question_set_id", UUID, nullable=True),
        sa.Column("run_sequence", sa.Integer(), nullable=False),
        sa.Column(
            "run_label", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "center_term", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("center_terms", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "platforms_requested", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "platforms_completed", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "expected_answer_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "valid_answer_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "failed_answer_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("answer_scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "question_signature",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "lexicon_version", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "lexicon_hash", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "extraction_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "calibration_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "projection_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "include_in_cumulative",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("excluded_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["question_set_id"], ["monitoring_question_sets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "run_sequence",
            name="uq_amway_circle_runs_entity_sequence",
        ),
        sa.UniqueConstraint(
            "brand_intelligence_run_id",
            name="uq_amway_circle_runs_bi_run",
        ),
        sa.UniqueConstraint("id", "entity_id", name="uq_amway_circle_runs_id_entity"),
    )
    op.create_index(
        "ix_amway_circle_runs_entity_created",
        "amway_circle_runs",
        ["entity_id", "created_at"],
    )
    op.create_index(
        "ix_amway_circle_runs_entity_sequence",
        "amway_circle_runs",
        ["entity_id", "run_sequence"],
    )
    op.create_index("ix_amway_circle_runs_status", "amway_circle_runs", ["status"])
    op.create_index(
        "ix_amway_circle_runs_question_set",
        "amway_circle_runs",
        ["question_set_id"],
    )

    op.create_table(
        "amway_circle_answers",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("question_set_id", UUID, nullable=True),
        sa.Column(
            "question_id", sa.String(length=120), nullable=False, server_default=""
        ),
        sa.Column(
            "question_hash", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("question_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("question_metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("platform", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("platform_model", sa.String(length=120), nullable=True),
        sa.Column(
            "fetch_agent_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "fetch_status",
            sa.String(length=32),
            nullable=False,
            server_default="success",
        ),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_excerpt", sa.Text(), nullable=True),
        sa.Column("answer_hash", sa.String(length=80), nullable=True),
        sa.Column(
            "mentions_center", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "center_context_type",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "answer_quality",
            sa.String(length=32),
            nullable=False,
            server_default="valid",
        ),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_set_id"], ["monitoring_question_sets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "question_id",
            "platform",
            name="uq_amway_circle_answers_run_question_platform",
        ),
        sa.UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_circle_answers_id_run",
        ),
    )
    op.create_index(
        "ix_amway_circle_answers_run_platform",
        "amway_circle_answers",
        ["circle_run_id", "platform"],
    )
    op.create_index(
        "ix_amway_circle_answers_run_question",
        "amway_circle_answers",
        ["circle_run_id", "question_id"],
    )
    op.create_index(
        "ix_amway_circle_answers_run_question_hash",
        "amway_circle_answers",
        ["circle_run_id", "question_hash"],
    )
    op.create_index(
        "ix_amway_circle_answers_entity_platform",
        "amway_circle_answers",
        ["entity_id", "platform"],
    )

    op.create_table(
        "amway_circle_entity_mentions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("answer_id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("lexicon_entity_id", sa.String(length=120), nullable=True),
        sa.Column(
            "canonical_name", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "entity_type", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="lexicon",
        ),
        sa.Column(
            "matched_text", sa.String(length=240), nullable=False, server_default=""
        ),
        sa.Column("matched_alias", sa.String(length=240), nullable=True),
        sa.Column("context_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "relation_type", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "amway_anchor", sa.String(length=32), nullable=False, server_default="none"
        ),
        sa.Column(
            "sentiment_context",
            sa.String(length=32),
            nullable=False,
            server_default="neutral",
        ),
        sa.Column("risk_context", sa.String(length=32), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "extractor_version", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "dedupe_key", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id", "circle_run_id"],
            ["amway_circle_answers.id", "amway_circle_answers.circle_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "answer_id",
            "dedupe_key",
            name="uq_amway_mentions_dedupe",
        ),
        sa.UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_mentions_id_run",
        ),
    )
    op.create_index(
        "ix_amway_mentions_run_entity",
        "amway_circle_entity_mentions",
        ["circle_run_id", "canonical_name"],
    )
    op.create_index(
        "ix_amway_mentions_answer", "amway_circle_entity_mentions", ["answer_id"]
    )
    op.create_index(
        "ix_amway_mentions_entity_type",
        "amway_circle_entity_mentions",
        ["entity_type"],
    )
    op.create_index(
        "ix_amway_mentions_risk_context",
        "amway_circle_entity_mentions",
        ["risk_context"],
    )

    op.create_table(
        "amway_circle_evidence",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("answer_id", UUID, nullable=False),
        sa.Column("mention_id", UUID, nullable=True),
        sa.Column(
            "evidence_ref", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("platform", sa.String(length=40), nullable=False, server_default=""),
        sa.Column(
            "question_id", sa.String(length=120), nullable=False, server_default=""
        ),
        sa.Column("question_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("quote_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "quote_type", sa.String(length=40), nullable=False, server_default=""
        ),
        sa.Column("entity_names", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("strategy_terms", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("scenario_tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id", "circle_run_id"],
            ["amway_circle_answers.id", "amway_circle_answers.circle_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["mention_id", "circle_run_id"],
            [
                "amway_circle_entity_mentions.id",
                "amway_circle_entity_mentions.circle_run_id",
            ],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "evidence_ref",
            name="uq_amway_evidence_run_ref",
        ),
    )
    op.create_index(
        "ix_amway_evidence_run_ref",
        "amway_circle_evidence",
        ["circle_run_id", "evidence_ref"],
    )
    op.create_index("ix_amway_evidence_answer", "amway_circle_evidence", ["answer_id"])
    op.create_index("ix_amway_evidence_platform", "amway_circle_evidence", ["platform"])
    op.create_index(
        "ix_amway_evidence_quote_type", "amway_circle_evidence", ["quote_type"]
    )

    op.create_table(
        "amway_circle_node_snapshots",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("node_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("lexicon_entity_id", sa.String(length=120), nullable=True),
        sa.Column(
            "canonical_name", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "entity_type", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "source_type", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.Column(
            "track", sa.String(length=32), nullable=False, server_default="watch"
        ),
        sa.Column("track_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "mention_answer_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "center_anchor_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("amway_anchor_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gravity_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("distance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stability_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("node_size", sa.Float(), nullable=False, server_default="1"),
        sa.Column("display_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("question_summary", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("evidence_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "calibration_payload", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "node_id",
            name="uq_amway_nodes_run_node",
        ),
        sa.UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_nodes_id_run",
        ),
    )
    op.create_index(
        "ix_amway_nodes_run_track",
        "amway_circle_node_snapshots",
        ["circle_run_id", "track"],
    )
    op.create_index(
        "ix_amway_nodes_run_type",
        "amway_circle_node_snapshots",
        ["circle_run_id", "entity_type"],
    )
    op.create_index(
        "ix_amway_nodes_run_lexicon",
        "amway_circle_node_snapshots",
        ["circle_run_id", "lexicon_entity_id"],
    )
    op.create_index(
        "ix_amway_nodes_run_priority",
        "amway_circle_node_snapshots",
        ["circle_run_id", "display_priority"],
    )

    op.create_table(
        "amway_circle_edge_snapshots",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("edge_id", sa.String(length=180), nullable=False, server_default=""),
        sa.Column(
            "source_node_id", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "target_node_id", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column(
            "relation_type", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "relation_label", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column("strength_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_context", sa.String(length=32), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("edge_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "source_node_id"],
            [
                "amway_circle_node_snapshots.circle_run_id",
                "amway_circle_node_snapshots.node_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "target_node_id"],
            [
                "amway_circle_node_snapshots.circle_run_id",
                "amway_circle_node_snapshots.node_id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "edge_id",
            name="uq_amway_edges_run_edge",
        ),
    )
    op.create_index(
        "ix_amway_edges_run_source",
        "amway_circle_edge_snapshots",
        ["circle_run_id", "source_node_id"],
    )
    op.create_index(
        "ix_amway_edges_run_target",
        "amway_circle_edge_snapshots",
        ["circle_run_id", "target_node_id"],
    )
    op.create_index(
        "ix_amway_edges_relation", "amway_circle_edge_snapshots", ["relation_type"]
    )

    op.create_table(
        "amway_circle_projections",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=True),
        sa.Column("base_run_id", UUID, nullable=True),
        sa.Column("target_run_id", UUID, nullable=True),
        sa.Column("as_of_run_id", UUID, nullable=True),
        sa.Column(
            "projection_scope",
            sa.String(length=32),
            nullable=False,
            server_default="run",
        ),
        sa.Column(
            "projection_version",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="ready"
        ),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_run_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "source_run_hash", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("sample_scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "association_circle_projection",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("report_input", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("compare_summary", sa.Text(), nullable=True),
        sa.Column("data_quality", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["base_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        sa.ForeignKeyConstraint(
            ["as_of_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "entity_id",
            name="uq_amway_projections_id_entity",
        ),
        sa.UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_projections_id_run",
        ),
    )
    op.create_index(
        "ix_amway_projections_entity_scope",
        "amway_circle_projections",
        ["entity_id", "projection_scope", "is_latest"],
    )
    op.create_index(
        "uq_amway_latest_projection_scope",
        "amway_circle_projections",
        ["entity_id", "projection_scope"],
        unique=True,
        postgresql_where=sa.text("is_latest = true"),
    )
    op.create_index(
        "uq_amway_projection_source_hash",
        "amway_circle_projections",
        ["entity_id", "projection_scope", "projection_version", "source_run_hash"],
        unique=True,
        postgresql_where=sa.text("source_run_hash <> ''"),
    )
    op.create_index(
        "ix_amway_projections_as_of", "amway_circle_projections", ["as_of_run_id"]
    )
    op.create_index(
        "ix_amway_projections_run", "amway_circle_projections", ["circle_run_id"]
    )
    op.create_index(
        "ix_amway_projections_compare",
        "amway_circle_projections",
        ["base_run_id", "target_run_id"],
    )

    op.create_table(
        "amway_circle_reports",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("projection_id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=True),
        sa.Column(
            "report_scope", sa.String(length=32), nullable=False, server_default="run"
        ),
        sa.Column(
            "report_version", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("title", sa.String(length=240), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="draft"
        ),
        sa.Column("markdown_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("structured_body", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "source_report_input", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "source_projection_hash",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["projection_id"], ["amway_circle_projections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["projection_id", "entity_id"],
            ["amway_circle_projections.id", "amway_circle_projections.entity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["projection_id", "circle_run_id"],
            ["amway_circle_projections.id", "amway_circle_projections.circle_run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_amway_reports_entity_scope",
        "amway_circle_reports",
        ["entity_id", "report_scope"],
    )
    op.create_index(
        "ix_amway_reports_projection", "amway_circle_reports", ["projection_id"]
    )
    op.create_index("ix_amway_reports_run", "amway_circle_reports", ["circle_run_id"])

    op.create_table(
        "amway_circle_exports",
        sa.Column("id", UUID, nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("projection_id", UUID, nullable=False),
        sa.Column("report_id", UUID, nullable=True),
        sa.Column("circle_run_id", UUID, nullable=True),
        sa.Column(
            "export_type", sa.String(length=32), nullable=False, server_default="html"
        ),
        sa.Column(
            "export_scope", sa.String(length=32), nullable=False, server_default="run"
        ),
        sa.Column(
            "file_name", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("storage_path", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "content_hash", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "include_graph", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "include_answer_appendix",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["projection_id"], ["amway_circle_projections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["amway_circle_reports.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_amway_exports_entity_created",
        "amway_circle_exports",
        ["entity_id", "created_at"],
    )
    op.create_index(
        "ix_amway_exports_projection", "amway_circle_exports", ["projection_id"]
    )

    op.create_table(
        "amway_circle_runtime_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("circle_run_id", UUID, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "event_type", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["circle_run_id"], ["amway_circle_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circle_run_id",
            "sequence",
            name="uq_amway_events_run_sequence",
        ),
    )
    op.create_index(
        "ix_amway_events_run_sequence",
        "amway_circle_runtime_events",
        ["circle_run_id", "sequence"],
    )
    op.create_index(
        "ix_amway_events_type", "amway_circle_runtime_events", ["event_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_amway_events_type", table_name="amway_circle_runtime_events")
    op.drop_index(
        "ix_amway_events_run_sequence", table_name="amway_circle_runtime_events"
    )
    op.drop_table("amway_circle_runtime_events")

    op.drop_index("ix_amway_exports_projection", table_name="amway_circle_exports")
    op.drop_index("ix_amway_exports_entity_created", table_name="amway_circle_exports")
    op.drop_table("amway_circle_exports")

    op.drop_index("ix_amway_reports_run", table_name="amway_circle_reports")
    op.drop_index("ix_amway_reports_projection", table_name="amway_circle_reports")
    op.drop_index("ix_amway_reports_entity_scope", table_name="amway_circle_reports")
    op.drop_table("amway_circle_reports")

    op.drop_index("ix_amway_projections_compare", table_name="amway_circle_projections")
    op.drop_index("ix_amway_projections_run", table_name="amway_circle_projections")
    op.drop_index("ix_amway_projections_as_of", table_name="amway_circle_projections")
    op.drop_index(
        "uq_amway_projection_source_hash", table_name="amway_circle_projections"
    )
    op.drop_index(
        "uq_amway_latest_projection_scope", table_name="amway_circle_projections"
    )
    op.drop_index(
        "ix_amway_projections_entity_scope", table_name="amway_circle_projections"
    )
    op.drop_table("amway_circle_projections")

    op.drop_index("ix_amway_edges_relation", table_name="amway_circle_edge_snapshots")
    op.drop_index("ix_amway_edges_run_target", table_name="amway_circle_edge_snapshots")
    op.drop_index("ix_amway_edges_run_source", table_name="amway_circle_edge_snapshots")
    op.drop_table("amway_circle_edge_snapshots")

    op.drop_index(
        "ix_amway_nodes_run_priority", table_name="amway_circle_node_snapshots"
    )
    op.drop_index(
        "ix_amway_nodes_run_lexicon", table_name="amway_circle_node_snapshots"
    )
    op.drop_index("ix_amway_nodes_run_type", table_name="amway_circle_node_snapshots")
    op.drop_index("ix_amway_nodes_run_track", table_name="amway_circle_node_snapshots")
    op.drop_table("amway_circle_node_snapshots")

    op.drop_index("ix_amway_evidence_quote_type", table_name="amway_circle_evidence")
    op.drop_index("ix_amway_evidence_platform", table_name="amway_circle_evidence")
    op.drop_index("ix_amway_evidence_answer", table_name="amway_circle_evidence")
    op.drop_index("ix_amway_evidence_run_ref", table_name="amway_circle_evidence")
    op.drop_table("amway_circle_evidence")

    op.drop_index(
        "ix_amway_mentions_risk_context",
        table_name="amway_circle_entity_mentions",
    )
    op.drop_index(
        "ix_amway_mentions_entity_type",
        table_name="amway_circle_entity_mentions",
    )
    op.drop_index("ix_amway_mentions_answer", table_name="amway_circle_entity_mentions")
    op.drop_index(
        "ix_amway_mentions_run_entity",
        table_name="amway_circle_entity_mentions",
    )
    op.drop_table("amway_circle_entity_mentions")

    op.drop_index(
        "ix_amway_circle_answers_entity_platform",
        table_name="amway_circle_answers",
    )
    op.drop_index(
        "ix_amway_circle_answers_run_question",
        table_name="amway_circle_answers",
    )
    op.drop_index(
        "ix_amway_circle_answers_run_question_hash",
        table_name="amway_circle_answers",
    )
    op.drop_index(
        "ix_amway_circle_answers_run_platform",
        table_name="amway_circle_answers",
    )
    op.drop_table("amway_circle_answers")

    op.drop_index("ix_amway_circle_runs_question_set", table_name="amway_circle_runs")
    op.drop_index("ix_amway_circle_runs_status", table_name="amway_circle_runs")
    op.drop_index(
        "ix_amway_circle_runs_entity_sequence", table_name="amway_circle_runs"
    )
    op.drop_index("ix_amway_circle_runs_entity_created", table_name="amway_circle_runs")
    op.drop_table("amway_circle_runs")

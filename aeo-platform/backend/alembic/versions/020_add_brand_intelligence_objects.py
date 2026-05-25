"""add brand intelligence object tables

Revision ID: 020
Revises: 019
Create Date: 2026-05-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: str | None = "019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_competitor_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("competitor_key", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=False),
        sa.Column("competition_type", sa.String(length=80), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "session_id",
            "competitor_key",
            name="uq_brand_competitor_entity_session_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_competitor_entities_entity_id", ["entity_id"]),
        ("ix_brand_competitor_entities_session_id", ["session_id"]),
        ("ix_brand_competitor_entities_status", ["status"]),
        ("ix_brand_competitors_entity_status", ["entity_id", "status"]),
        ("ix_brand_competitors_name", ["normalized_name"]),
    ]:
        op.create_index(index_name, "brand_competitor_entities", columns)

    op.create_table(
        "brand_audience_personas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("persona_id", sa.String(length=120), nullable=False),
        sa.Column("persona_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("segment", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "session_id",
            "persona_id",
            name="uq_brand_audience_persona_session_id",
        ),
    )
    for index_name, columns in [
        ("ix_brand_audience_personas_entity_id", ["entity_id"]),
        ("ix_brand_audience_personas_session_id", ["session_id"]),
        ("ix_brand_audience_personas_status", ["status"]),
        ("ix_brand_personas_entity_status", ["entity_id", "status"]),
    ]:
        op.create_index(index_name, "brand_audience_personas", columns)

    op.create_table(
        "brand_usage_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("persona_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scenario_key", sa.String(length=120), nullable=False),
        sa.Column("scenario_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("decision_stage", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["persona_object_id"],
            ["brand_audience_personas.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "session_id",
            "scenario_key",
            name="uq_brand_usage_scenario_session_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_usage_scenarios_entity_id", ["entity_id"]),
        ("ix_brand_usage_scenarios_session_id", ["session_id"]),
        ("ix_brand_usage_scenarios_status", ["status"]),
        ("ix_brand_scenarios_entity_status", ["entity_id", "status"]),
        ("ix_brand_scenarios_persona", ["persona_object_id"]),
    ]:
        op.create_index(index_name, "brand_usage_scenarios", columns)

    op.create_table(
        "brand_intelligence_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", sa.String(length=120), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("subcategory", sa.String(length=120), nullable=False),
        sa.Column("user_intent", sa.String(length=255), nullable=False),
        sa.Column("decision_stage", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "session_id",
            "question_id",
            name="uq_brand_intel_question_entity_session_question",
        ),
    )
    op.create_index(
        "ix_brand_intel_questions_category",
        "brand_intelligence_questions",
        ["category"],
    )
    op.create_index(
        "ix_brand_intel_questions_entity_status",
        "brand_intelligence_questions",
        ["entity_id", "status"],
    )
    op.create_index(
        "ix_brand_intelligence_questions_entity_id",
        "brand_intelligence_questions",
        ["entity_id"],
    )
    op.create_index(
        "ix_brand_intelligence_questions_session_id",
        "brand_intelligence_questions",
        ["session_id"],
    )
    op.create_index(
        "ix_brand_intelligence_questions_status",
        "brand_intelligence_questions",
        ["status"],
    )

    op.create_table(
        "brand_platform_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", sa.String(length=120), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("fetch_method", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("brand_mentioned", sa.Boolean(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("answer_payload", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("run_id", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_object_id"],
            ["brand_intelligence_questions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dedupe_key",
            name="uq_brand_platform_answers_dedupe_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_platform_answers_entity_id", ["entity_id"]),
        ("ix_brand_platform_answers_session_id", ["session_id"]),
        ("ix_brand_platform_answers_question_object_id", ["question_object_id"]),
        ("ix_brand_platform_answers_question_id", ["question_id"]),
        ("ix_brand_platform_answers_platform", ["platform"]),
        ("ix_brand_platform_answers_run_id", ["run_id"]),
        ("ix_brand_platform_answers_status", ["status"]),
        ("ix_brand_platform_answers_captured_at", ["captured_at"]),
        ("ix_brand_platform_answers_entity_platform", ["entity_id", "platform"]),
    ]:
        op.create_index(index_name, "brand_platform_answers", columns)

    op.create_table(
        "brand_citation_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("citation_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["answer_id"], ["brand_platform_answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dedupe_key",
            name="uq_brand_citation_sources_dedupe_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_citation_sources_entity_id", ["entity_id"]),
        ("ix_brand_citation_sources_session_id", ["session_id"]),
        ("ix_brand_citation_sources_answer_id", ["answer_id"]),
        ("ix_brand_citation_sources_entity_domain", ["entity_id", "domain"]),
    ]:
        op.create_index(index_name, "brand_citation_sources", columns)

    op.create_table(
        "brand_evidence_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_set_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("question_ids", sa.Text(), nullable=True),
        sa.Column("answer_ids", sa.Text(), nullable=True),
        sa.Column("citation_ids", sa.Text(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("answer_count", sa.Integer(), nullable=False),
        sa.Column("citation_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in [
        ("ix_brand_evidence_sets_entity_id", ["entity_id"]),
        ("ix_brand_evidence_sets_session_id", ["session_id"]),
        ("ix_brand_evidence_sets_entity_type", ["entity_id", "evidence_set_type"]),
    ]:
        op.create_index(index_name, "brand_evidence_sets", columns)

    op.create_table(
        "brand_report_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_set_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report_id", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_kind", sa.String(length=50), nullable=False),
        sa.Column("artifact_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"], ["brand_evidence_sets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "report_id",
            "version",
            name="uq_brand_report_versions_entity_report_version",
        ),
    )
    for index_name, columns in [
        ("ix_brand_report_versions_entity_id", ["entity_id"]),
        ("ix_brand_report_versions_session_id", ["session_id"]),
        ("ix_brand_report_versions_evidence_set_id", ["evidence_set_id"]),
        ("ix_brand_report_versions_message_id", ["message_id"]),
        ("ix_brand_report_versions_artifact_id", ["artifact_id"]),
        ("ix_brand_report_versions_entity_kind", ["entity_id", "report_kind"]),
    ]:
        op.create_index(index_name, "brand_report_versions", columns)

    op.create_table(
        "brand_intelligence_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_set_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("finding_key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("finding_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("supporting_question_count", sa.Integer(), nullable=False),
        sa.Column("supporting_answer_count", sa.Integer(), nullable=False),
        sa.Column("supporting_citation_count", sa.Integer(), nullable=False),
        sa.Column("suggested_action_type", sa.String(length=120), nullable=False),
        sa.Column("suggested_action_payload", sa.Text(), nullable=True),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"],
            ["brand_evidence_sets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_version_id"],
            ["brand_report_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "session_id",
            "finding_key",
            name="uq_brand_intelligence_findings_session_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_intelligence_findings_entity_id", ["entity_id"]),
        ("ix_brand_intelligence_findings_session_id", ["session_id"]),
        ("ix_brand_intelligence_findings_report_version_id", ["report_version_id"]),
        ("ix_brand_intelligence_findings_evidence_set_id", ["evidence_set_id"]),
        ("ix_brand_intelligence_findings_finding_type", ["finding_type"]),
        ("ix_brand_intelligence_findings_status", ["status"]),
        ("ix_brand_intel_findings_entity_status", ["entity_id", "status"]),
        ("ix_brand_intel_findings_entity_type", ["entity_id", "finding_type"]),
        ("ix_brand_intel_findings_report", ["report_version_id"]),
    ]:
        op.create_index(index_name, "brand_intelligence_findings", columns)

    op.create_table(
        "brand_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_key", sa.String(length=120), nullable=False),
        sa.Column("metric_kind", sa.String(length=80), nullable=False),
        sa.Column("bwvs_index", sa.Float(), nullable=True),
        sa.Column("mention_rate", sa.Float(), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=True),
        sa.Column("metric_payload", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["report_version_id"],
            ["brand_report_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "snapshot_key",
            name="uq_brand_metric_snapshots_entity_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_metric_snapshots_entity_id", ["entity_id"]),
        ("ix_brand_metric_snapshots_session_id", ["session_id"]),
        ("ix_brand_metric_snapshots_report_version_id", ["report_version_id"]),
        ("ix_brand_metric_snapshots_captured_at", ["captured_at"]),
        ("ix_brand_metric_snapshots_entity_kind", ["entity_id", "metric_kind"]),
        ("ix_brand_metric_snapshots_report", ["report_version_id"]),
    ]:
        op.create_index(index_name, "brand_metric_snapshots", columns)

    op.create_table(
        "brand_action_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_action_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("origin_surface", sa.String(length=80), nullable=True),
        sa.Column("origin_event_id", sa.String(length=120), nullable=True),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("permission_scope", sa.String(length=80), nullable=False),
        sa.Column("input_payload", sa.Text(), nullable=True),
        sa.Column("output_payload", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_action_record_id"],
            ["brand_action_records.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in [
        ("ix_brand_action_records_entity_id", ["entity_id"]),
        ("ix_brand_action_records_session_id", ["session_id"]),
        ("ix_brand_action_records_user_id", ["user_id"]),
        ("ix_brand_action_records_action_type", ["action_type"]),
        ("ix_brand_action_records_status", ["status"]),
        ("ix_brand_action_records_entity_action", ["entity_id", "action_type"]),
        ("ix_brand_action_records_actor_surface", ["actor_type", "origin_surface"]),
        ("ix_brand_action_records_parent", ["parent_action_record_id"]),
    ]:
        op.create_index(index_name, "brand_action_records", columns)

    op.create_table(
        "brand_user_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_type", sa.String(length=80), nullable=False),
        sa.Column("decision_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("origin_surface", sa.String(length=80), nullable=True),
        sa.Column("origin_event_id", sa.String(length=120), nullable=True),
        sa.Column("target_object_type", sa.String(length=120), nullable=True),
        sa.Column("target_object_id", sa.String(length=255), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("input_payload", sa.Text(), nullable=True),
        sa.Column("output_payload", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_record_id"], ["brand_action_records.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_record_id",
            name="uq_brand_user_decisions_action_record",
        ),
    )
    for index_name, columns in [
        ("ix_brand_user_decisions_entity_id", ["entity_id"]),
        ("ix_brand_user_decisions_action_record_id", ["action_record_id"]),
        ("ix_brand_user_decisions_session_id", ["session_id"]),
        ("ix_brand_user_decisions_user_id", ["user_id"]),
        ("ix_brand_user_decisions_decision_type", ["decision_type"]),
        ("ix_brand_user_decisions_entity_status", ["entity_id", "status"]),
        ("ix_brand_user_decisions_user_status", ["user_id", "status"]),
        (
            "ix_brand_user_decisions_target",
            ["target_object_type", "target_object_id"],
        ),
    ]:
        op.create_index(index_name, "brand_user_decisions", columns)

    op.create_table(
        "brand_object_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=120), nullable=False),
        sa.Column("from_object_type", sa.String(length=120), nullable=False),
        sa.Column("from_object_id", sa.String(length=255), nullable=False),
        sa.Column("to_object_type", sa.String(length=120), nullable=False),
        sa.Column("to_object_id", sa.String(length=255), nullable=False),
        sa.Column("source_action_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_action_record_id"],
            ["brand_action_records.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "link_type",
            "from_object_type",
            "from_object_id",
            "to_object_type",
            "to_object_id",
            name="uq_brand_object_links_edge",
        ),
    )
    for index_name, columns in [
        ("ix_brand_object_links_entity_id", ["entity_id"]),
        ("ix_brand_object_links_source_action_record_id", ["source_action_record_id"]),
        (
            "ix_brand_object_links_from",
            ["from_object_type", "from_object_id", "link_type"],
        ),
        (
            "ix_brand_object_links_to",
            ["to_object_type", "to_object_id", "link_type"],
        ),
        ("ix_brand_object_links_entity_link", ["entity_id", "link_type"]),
    ]:
        op.create_index(index_name, "brand_object_links", columns)


def downgrade() -> None:
    op.drop_table("brand_object_links")
    op.drop_table("brand_user_decisions")
    op.drop_table("brand_action_records")
    op.drop_table("brand_metric_snapshots")
    op.drop_table("brand_intelligence_findings")
    op.drop_table("brand_report_versions")
    op.drop_table("brand_evidence_sets")
    op.drop_table("brand_citation_sources")
    op.drop_table("brand_platform_answers")
    op.drop_table("brand_intelligence_questions")
    op.drop_table("brand_usage_scenarios")
    op.drop_table("brand_audience_personas")
    op.drop_table("brand_competitor_entities")

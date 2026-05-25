"""repair missing brand intelligence findings table

Revision ID: 021
Revises: 020
Create Date: 2026-05-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: str | None = "020"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "brand_intelligence_findings" in inspector.get_table_names():
        return

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


def downgrade() -> None:
    # This repair migration may be a no-op on databases where 020 already created
    # the table. Dropping it here would destroy 020-owned schema, so downgrade is
    # intentionally no-op.
    return

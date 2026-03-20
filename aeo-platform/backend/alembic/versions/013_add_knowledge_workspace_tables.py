"""Add Knowledge Workspace tables.

Revision ID: 013
Revises: 012
Create Date: 2026-03-20
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=True),
        sa.Column("question_id", sa.String(length=120), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("competitor_name", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("dedupe_key", name="uq_knowledge_records_dedupe_key"),
    )

    op.create_index(
        "ix_knowledge_records_entity_id",
        "knowledge_records",
        ["entity_id"],
    )
    op.create_index(
        "ix_knowledge_records_session_id",
        "knowledge_records",
        ["session_id"],
    )
    op.create_index(
        "ix_knowledge_records_task_id",
        "knowledge_records",
        ["task_id"],
    )
    op.create_index(
        "ix_knowledge_records_run_id",
        "knowledge_records",
        ["run_id"],
    )
    op.create_index(
        "ix_knowledge_records_source_type",
        "knowledge_records",
        ["source_type"],
    )
    op.create_index(
        "ix_knowledge_records_brand_name",
        "knowledge_records",
        ["brand_name"],
    )
    op.create_index(
        "ix_knowledge_records_platform",
        "knowledge_records",
        ["platform"],
    )
    op.create_index(
        "ix_knowledge_records_question_id",
        "knowledge_records",
        ["question_id"],
    )
    op.create_index(
        "ix_knowledge_records_competitor_name",
        "knowledge_records",
        ["competitor_name"],
    )
    op.create_index(
        "ix_knowledge_records_domain",
        "knowledge_records",
        ["domain"],
    )
    op.create_index(
        "ix_knowledge_records_occurred_at",
        "knowledge_records",
        ["occurred_at"],
    )
    op.create_index(
        "ix_knowledge_records_entity_occurred_at",
        "knowledge_records",
        ["entity_id", "occurred_at"],
    )
    op.create_index(
        "ix_knowledge_records_brand_occurred_at",
        "knowledge_records",
        ["brand_name", "occurred_at"],
    )
    op.create_index(
        "ix_knowledge_records_entity_source_occurred_at",
        "knowledge_records",
        ["entity_id", "source_type", "occurred_at"],
    )

    op.create_table(
        "knowledge_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "record_id",
            sa.String(length=36),
            sa.ForeignKey("knowledge_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "record_id",
            "segment_index",
            name="uq_knowledge_segment_order",
        ),
    )

    op.create_index(
        "ix_knowledge_segments_record_id",
        "knowledge_segments",
        ["record_id"],
    )

    op.alter_column("knowledge_records", "occurred_at", server_default=None)
    op.alter_column("knowledge_records", "search_text", server_default=None)
    op.alter_column("knowledge_records", "created_at", server_default=None)
    op.alter_column("knowledge_records", "updated_at", server_default=None)
    op.alter_column("knowledge_segments", "content", server_default=None)
    op.alter_column("knowledge_segments", "search_text", server_default=None)
    op.alter_column("knowledge_segments", "created_at", server_default=None)


def downgrade():
    op.drop_index("ix_knowledge_segments_record_id", table_name="knowledge_segments")
    op.drop_table("knowledge_segments")

    op.drop_index("ix_knowledge_records_occurred_at", table_name="knowledge_records")
    op.drop_index(
        "ix_knowledge_records_entity_source_occurred_at",
        table_name="knowledge_records",
    )
    op.drop_index(
        "ix_knowledge_records_brand_occurred_at",
        table_name="knowledge_records",
    )
    op.drop_index(
        "ix_knowledge_records_entity_occurred_at",
        table_name="knowledge_records",
    )
    op.drop_index("ix_knowledge_records_domain", table_name="knowledge_records")
    op.drop_index(
        "ix_knowledge_records_competitor_name", table_name="knowledge_records"
    )
    op.drop_index("ix_knowledge_records_question_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_platform", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_brand_name", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_source_type", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_run_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_task_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_session_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_entity_id", table_name="knowledge_records")
    op.drop_table("knowledge_records")

"""add brand mention facts

Revision ID: 022
Revises: 021
Create Date: 2026-05-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | None = "021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("mentioned_brand_key", sa.String(length=160), nullable=False),
        sa.Column("mentioned_brand_name", sa.String(length=255), nullable=False),
        sa.Column("mentioned_object_type", sa.String(length=120), nullable=False),
        sa.Column("mentioned_object_id", sa.String(length=255), nullable=False),
        sa.Column("mention_role", sa.String(length=40), nullable=False),
        sa.Column("sentiment", sa.String(length=32), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["brand_platform_answers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_object_id"],
            ["brand_intelligence_questions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id"],
            ["brand_report_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "dedupe_key",
            name="uq_brand_mentions_entity_dedupe_key",
        ),
    )
    for index_name, columns in [
        ("ix_brand_mentions_entity_id", ["entity_id"]),
        ("ix_brand_mentions_session_id", ["session_id"]),
        ("ix_brand_mentions_report_version_id", ["report_version_id"]),
        ("ix_brand_mentions_captured_at", ["captured_at"]),
        ("ix_brand_mentions_entity_role", ["entity_id", "mention_role"]),
        ("ix_brand_mentions_answer_id", ["answer_id"]),
        ("ix_brand_mentions_question_object_id", ["question_object_id"]),
        ("ix_brand_mentions_sentiment", ["sentiment"]),
        (
            "ix_brand_mentions_target_object",
            ["mentioned_object_type", "mentioned_object_id"],
        ),
    ]:
        op.create_index(index_name, "brand_mentions", columns)


def downgrade() -> None:
    op.drop_table("brand_mentions")

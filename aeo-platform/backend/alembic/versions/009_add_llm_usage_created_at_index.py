"""Add created_at index for llm observability time-window queries.

Revision ID: 009
Revises: 008
Create Date: 2026-03-19
"""

from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_llm_usage_records_created_at",
        "llm_usage_records",
        ["created_at"],
    )


def downgrade():
    op.drop_index("ix_llm_usage_records_created_at", table_name="llm_usage_records")

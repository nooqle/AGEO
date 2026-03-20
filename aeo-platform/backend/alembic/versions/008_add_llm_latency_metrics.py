"""Add latency metrics to llm observability tables.

Revision ID: 008
Revises: 007
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "llm_total_latency_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "llm_usage_records",
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.alter_column("analysis_tasks", "llm_total_latency_ms", server_default=None)
    op.alter_column("llm_usage_records", "latency_ms", server_default=None)


def downgrade():
    op.drop_column("llm_usage_records", "latency_ms")
    op.drop_column("analysis_tasks", "llm_total_latency_ms")

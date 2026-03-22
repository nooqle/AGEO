"""Add cache-aware LLM observability fields.

Revision ID: 016
Revises: 015
Create Date: 2026-03-22
"""

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "llm_cached_prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "llm_billable_prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "llm_estimated_cost_cache_aware",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "llm_usage_records",
        sa.Column(
            "cached_prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "llm_usage_records",
        sa.Column(
            "billable_prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "llm_usage_records",
        sa.Column(
            "estimated_cost_cache_aware",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.alter_column("analysis_tasks", "llm_cached_prompt_tokens", server_default=None)
    op.alter_column(
        "analysis_tasks",
        "llm_billable_prompt_tokens",
        server_default=None,
    )
    op.alter_column(
        "analysis_tasks",
        "llm_estimated_cost_cache_aware",
        server_default=None,
    )
    op.alter_column(
        "llm_usage_records",
        "cached_prompt_tokens",
        server_default=None,
    )
    op.alter_column(
        "llm_usage_records",
        "billable_prompt_tokens",
        server_default=None,
    )
    op.alter_column(
        "llm_usage_records",
        "estimated_cost_cache_aware",
        server_default=None,
    )


def downgrade():
    op.drop_column("llm_usage_records", "estimated_cost_cache_aware")
    op.drop_column("llm_usage_records", "billable_prompt_tokens")
    op.drop_column("llm_usage_records", "cached_prompt_tokens")

    op.drop_column("analysis_tasks", "llm_estimated_cost_cache_aware")
    op.drop_column("analysis_tasks", "llm_billable_prompt_tokens")
    op.drop_column("analysis_tasks", "llm_cached_prompt_tokens")

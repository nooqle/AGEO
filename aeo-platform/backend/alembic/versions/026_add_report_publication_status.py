"""add report publication status column

Revision ID: 026
Revises: 025
Create Date: 2026-06-20 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "026"
down_revision: str | None = "025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "brand_report_versions",
        sa.Column(
            "publication_status",
            sa.String(length=40),
            nullable=False,
            server_default="draft",
        ),
    )
    op.create_index(
        "ix_brand_report_versions_entity_publication",
        "brand_report_versions",
        ["entity_id", "publication_status"],
    )
    op.execute(
        """
        UPDATE brand_report_versions
        SET publication_status = 'pre_graph_update'
        WHERE payload IS NULL OR payload NOT LIKE '%"graph_update_id"%'
        """
    )
    for status in ("needs_review", "publishable", "published", "draft"):
        op.execute(
            f"""
            UPDATE brand_report_versions
            SET publication_status = '{status}'
            WHERE payload LIKE '%"graph_update_id"%'
              AND payload LIKE '%"publication_status"%'
              AND payload LIKE '%"{status}"%'
            """
        )


def downgrade() -> None:
    op.drop_index(
        "ix_brand_report_versions_entity_publication",
        table_name="brand_report_versions",
    )
    op.drop_column("brand_report_versions", "publication_status")

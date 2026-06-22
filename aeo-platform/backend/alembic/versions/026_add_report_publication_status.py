"""add report publication status column

Revision ID: 026
Revises: 025
Create Date: 2026-06-20 00:00:00.000000
"""

import json
from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "026"
down_revision: str | None = "025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


GRAPH_REPORT_PUBLICATION_STATUSES = {
    "draft",
    "needs_review",
    "publishable",
    "published",
}


def _decode_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _publication_status_from_payload(value: Any) -> str:
    payload = _decode_payload(value)
    if not payload.get("graph_update_id"):
        return "pre_graph_update"
    status = str(payload.get("publication_status") or "draft")
    return status if status in GRAPH_REPORT_PUBLICATION_STATUSES else "draft"


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
    bind = op.get_bind()
    report_versions = sa.table(
        "brand_report_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("payload", sa.Text()),
        sa.column("publication_status", sa.String(length=40)),
    )
    rows = bind.execute(
        sa.select(report_versions.c.id, report_versions.c.payload)
    ).mappings()
    for row in rows:
        bind.execute(
            report_versions.update()
            .where(report_versions.c.id == row["id"])
            .values(publication_status=_publication_status_from_payload(row["payload"]))
        )


def downgrade() -> None:
    op.drop_index(
        "ix_brand_report_versions_entity_publication",
        table_name="brand_report_versions",
    )
    op.drop_column("brand_report_versions", "publication_status")

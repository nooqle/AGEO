"""add account feature flags

Revision ID: 030
Revises: 029
Create Date: 2026-06-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "030"
down_revision: str | None = "029"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "feature_flags"):
        op.add_column("users", sa.Column("feature_flags", sa.Text(), nullable=True))
    if not _has_column("registration_applications", "feature_flags"):
        op.add_column(
            "registration_applications",
            sa.Column("feature_flags", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("registration_applications", "feature_flags"):
        op.drop_column("registration_applications", "feature_flags")
    if _has_column("users", "feature_flags"):
        op.drop_column("users", "feature_flags")

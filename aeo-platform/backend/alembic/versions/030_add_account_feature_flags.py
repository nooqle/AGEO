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


def upgrade() -> None:
    op.add_column("users", sa.Column("feature_flags", sa.Text(), nullable=True))
    op.add_column(
        "registration_applications",
        sa.Column("feature_flags", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("registration_applications", "feature_flags")
    op.drop_column("users", "feature_flags")

"""add organization feature flags

Revision ID: 029
Revises: 028
Create Date: 2026-06-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "029"
down_revision: str | None = "028"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("feature_flags", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "feature_flags")

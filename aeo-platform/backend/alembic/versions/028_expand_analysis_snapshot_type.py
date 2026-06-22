"""expand analysis snapshot type length

Revision ID: 028
Revises: 027
Create Date: 2026-06-11 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "028"
down_revision: str | None = "027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "analysis_snapshots",
        "snapshot_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
        existing_server_default="legacy",
    )


def downgrade() -> None:
    op.alter_column(
        "analysis_snapshots",
        "snapshot_type",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="legacy",
    )

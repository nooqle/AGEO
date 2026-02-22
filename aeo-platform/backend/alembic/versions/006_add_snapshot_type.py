"""Add snapshot_type column to analysis_snapshots

Revision ID: 006
Revises: 005
Create Date: 2026-02-22

Adds snapshot_type to distinguish between baseline and persona snapshots.
Values: 'baseline' / 'persona' / 'legacy' (default for existing rows).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_snapshots",
        sa.Column(
            "snapshot_type",
            sa.String(20),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.create_index(
        "ix_analysis_snapshots_snapshot_type",
        "analysis_snapshots",
        ["snapshot_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_snapshots_snapshot_type", table_name="analysis_snapshots")
    op.drop_column("analysis_snapshots", "snapshot_type")

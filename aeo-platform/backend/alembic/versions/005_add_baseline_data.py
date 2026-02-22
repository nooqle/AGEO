"""Add baseline_data column to monitoring_schedules

Revision ID: 005
Revises: 004
Create Date: 2026-02-21

Stores A1+A3 baseline output so subsequent scheduled runs can skip
A1-A3 and only re-run A4 (fetch) + A5 (analytics) with identical questions.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitoring_schedules",
        sa.Column("baseline_data", sa.Text, nullable=True),
    )


def downgrade():
    op.drop_column("monitoring_schedules", "baseline_data")

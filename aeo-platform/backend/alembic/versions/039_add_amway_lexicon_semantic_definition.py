"""Add sourced semantic identity to Amway lexicon overlays.

Revision ID: 039
Revises: 038
"""
from alembic import op
import sqlalchemy as sa

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "amway_entity_lexicon_overrides",
        sa.Column("semantic_definition", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("amway_entity_lexicon_overrides", "semantic_definition")

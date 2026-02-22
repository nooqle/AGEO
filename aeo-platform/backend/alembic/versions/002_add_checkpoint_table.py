"""Add LangGraph checkpoint tables

Revision ID: 002
Revises: 001
Create Date: 2025-02-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # LangGraph checkpoint table
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("checkpoint_ns", sa.String(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.String(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )

    # Checkpoint blobs table (for large data)
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("checkpoint_ns", sa.String(), nullable=False),
        sa.Column("checkpoint_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "checkpoint_id", "channel"
        ),
    )

    # Create indexes for better query performance
    op.create_index("idx_checkpoints_thread", "checkpoints", ["thread_id"])
    op.create_index("idx_checkpoints_parent", "checkpoints", ["parent_checkpoint_id"])


def downgrade():
    op.drop_index("idx_checkpoints_parent", table_name="checkpoints")
    op.drop_index("idx_checkpoints_thread", table_name="checkpoints")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoints")

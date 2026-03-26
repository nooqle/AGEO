"""Add invite access onboarding fields.

Revision ID: 017
Revises: 016
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE verificationpurpose ADD VALUE IF NOT EXISTS 'invite_access'"
        )

    op.add_column(
        "registration_applications",
        sa.Column("company_size", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "registration_applications",
        sa.Column(
            "is_agency",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "registration_applications",
        sa.Column(
            "assigned_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "registration_applications",
        sa.Column(
            "invite_code_issued_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "registration_applications",
        sa.Column("invite_code_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "registration_applications",
        sa.Column("invite_redeemed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_registration_applications_assigned_organization_id",
        "registration_applications",
        ["assigned_organization_id"],
    )
    op.alter_column(
        "registration_applications",
        "is_agency",
        server_default=None,
    )


def downgrade():
    op.drop_index(
        "ix_registration_applications_assigned_organization_id",
        table_name="registration_applications",
    )
    op.drop_column("registration_applications", "invite_redeemed_at")
    op.drop_column("registration_applications", "invite_code_sent_at")
    op.drop_column("registration_applications", "invite_code_issued_by_user_id")
    op.drop_column("registration_applications", "assigned_organization_id")
    op.drop_column("registration_applications", "is_agency")
    op.drop_column("registration_applications", "company_size")

"""Add account domain foundation models.

Revision ID: 015
Revises: 014
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


organization_status_enum = postgresql.ENUM(
    "active",
    "disabled",
    name="organizationstatus",
    create_type=False,
)
user_status_enum = postgresql.ENUM(
    "pending_review",
    "active",
    "disabled",
    "rejected",
    name="userstatus",
    create_type=False,
)
user_role_enum = postgresql.ENUM(
    "internal_admin",
    "customer_user",
    name="userrole",
    create_type=False,
)
registration_status_enum = postgresql.ENUM(
    "pending_review",
    "approved",
    "rejected",
    name="registrationapplicationstatus",
    create_type=False,
)
verification_channel_enum = postgresql.ENUM(
    "email",
    "phone",
    name="verificationchannel",
    create_type=False,
)
verification_purpose_enum = postgresql.ENUM(
    "registration",
    "login",
    "bind_email",
    "bind_phone",
    name="verificationpurpose",
    create_type=False,
)
entity_visibility_enum = postgresql.ENUM(
    "personal",
    "organization",
    name="entityvisibilityscope",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    organization_status_enum.create(bind, checkfirst=True)
    user_status_enum.create(bind, checkfirst=True)
    user_role_enum.create(bind, checkfirst=True)
    registration_status_enum.create(bind, checkfirst=True)
    verification_channel_enum.create(bind, checkfirst=True)
    verification_purpose_enum.create(bind, checkfirst=True)
    entity_visibility_enum.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", organization_status_enum, nullable=False, server_default="active"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_organizations_legal_name",
        "organizations",
        ["legal_name"],
    )

    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "status",
            user_status_enum,
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="customer_user",
        ),
    )
    op.add_column("users", sa.Column("job_title", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=True
    )
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(length=255), nullable=True
    )
    op.alter_column("users", "status", server_default=None)
    op.alter_column("users", "role", server_default=None)

    op.create_table(
        "registration_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("organization_name", sa.String(length=255), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("applicant_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            registration_status_enum,
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_registration_applications_email",
        "registration_applications",
        ["email"],
    )
    op.create_index(
        "ix_registration_applications_phone",
        "registration_applications",
        ["phone"],
    )
    op.alter_column("registration_applications", "status", server_default=None)

    op.create_table(
        "verification_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel", verification_channel_enum, nullable=False),
        sa.Column("purpose", verification_purpose_enum, nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_verification_challenges_target",
        "verification_challenges",
        ["target"],
    )
    op.alter_column("verification_challenges", "attempts", server_default=None)

    op.add_column(
        "entities",
        sa.Column(
            "visibility_scope",
            entity_visibility_enum,
            nullable=False,
            server_default="personal",
        ),
    )
    op.add_column(
        "entities",
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "entities",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_entities_owner_user_id", "entities", ["owner_user_id"])
    op.create_index("ix_entities_organization_id", "entities", ["organization_id"])
    op.alter_column("entities", "visibility_scope", server_default=None)


def downgrade():
    op.drop_index("ix_entities_organization_id", table_name="entities")
    op.drop_index("ix_entities_owner_user_id", table_name="entities")
    op.drop_column("entities", "organization_id")
    op.drop_column("entities", "owner_user_id")
    op.drop_column("entities", "visibility_scope")

    op.drop_index(
        "ix_verification_challenges_target", table_name="verification_challenges"
    )
    op.drop_table("verification_challenges")

    op.drop_index(
        "ix_registration_applications_phone",
        table_name="registration_applications",
    )
    op.drop_index(
        "ix_registration_applications_email",
        table_name="registration_applications",
    )
    op.drop_table("registration_applications")

    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(length=255), nullable=False
    )
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=False
    )
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "organization_id")
    op.drop_column("users", "job_title")
    op.drop_column("users", "role")
    op.drop_column("users", "status")
    op.drop_column("users", "phone")

    op.drop_index("ix_organizations_legal_name", table_name="organizations")
    op.drop_table("organizations")

    bind = op.get_bind()
    entity_visibility_enum.drop(bind, checkfirst=True)
    verification_purpose_enum.drop(bind, checkfirst=True)
    verification_channel_enum.drop(bind, checkfirst=True)
    registration_status_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
    user_status_enum.drop(bind, checkfirst=True)
    organization_status_enum.drop(bind, checkfirst=True)

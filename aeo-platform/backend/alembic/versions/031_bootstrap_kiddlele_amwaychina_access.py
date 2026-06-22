"""bootstrap kiddlele amwaychina access

Revision ID: 031
Revises: 030
Create Date: 2026-06-22 20:10:00.000000
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "031"
down_revision: str | None = "030"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


ADMIN_EMAIL = "kiddlele@qq.com"
ADMIN_ORGANIZATION_NAME = "Specta AI Admin"
FEATURE_FLAGS = {"amwaychina_console": True}


def _decode_flags(value: Any) -> dict[str, bool]:
    if isinstance(value, dict):
        return {str(key): bool(enabled) for key, enabled in value.items()}
    if not value:
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {str(key): bool(enabled) for key, enabled in decoded.items()}


def _merge_flags(value: Any) -> str:
    flags = _decode_flags(value)
    flags.update(FEATURE_FLAGS)
    return json.dumps(flags, ensure_ascii=False)


def _scalar(bind: sa.engine.Connection, sql: str, **params: Any) -> Any:
    return bind.execute(sa.text(sql), params).scalar_one_or_none()


def upgrade() -> None:
    bind = op.get_bind()
    user_row = bind.execute(
        sa.text(
            """
            SELECT id, organization_id, feature_flags
            FROM users
            WHERE lower(email) = :email
            LIMIT 1
            """
        ),
        {"email": ADMIN_EMAIL},
    ).mappings().first()
    if user_row is None:
        return

    organization_id = user_row["organization_id"]
    if organization_id is None:
        organization_id = _scalar(
            bind,
            "SELECT id FROM organizations WHERE legal_name = :legal_name LIMIT 1",
            legal_name=ADMIN_ORGANIZATION_NAME,
        )
        if organization_id is None:
            organization_id = uuid.uuid4()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO organizations (
                        id,
                        legal_name,
                        status,
                        feature_flags,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        :legal_name,
                        'active',
                        :feature_flags,
                        now(),
                        now()
                    )
                    """
                ),
                {
                    "id": str(organization_id),
                    "legal_name": ADMIN_ORGANIZATION_NAME,
                    "feature_flags": json.dumps(FEATURE_FLAGS),
                },
            )

    organization_flags = _scalar(
        bind,
        """
        SELECT feature_flags
        FROM organizations
        WHERE id = CAST(:organization_id AS uuid)
        LIMIT 1
        """,
        organization_id=str(organization_id),
    )
    bind.execute(
        sa.text(
            """
            UPDATE organizations
            SET
                status = 'active',
                feature_flags = :feature_flags,
                updated_at = now()
            WHERE id = CAST(:organization_id AS uuid)
            """
        ),
        {
            "organization_id": str(organization_id),
            "feature_flags": _merge_flags(organization_flags),
        },
    )

    bind.execute(
        sa.text(
            """
            UPDATE users
            SET
                organization_id = CAST(:organization_id AS uuid),
                role = 'internal_admin',
                status = 'active',
                is_active = true,
                feature_flags = :feature_flags,
                updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
            """
        ),
        {
            "organization_id": str(organization_id),
            "user_id": str(user_row["id"]),
            "feature_flags": _merge_flags(user_row["feature_flags"]),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    user_row = bind.execute(
        sa.text(
            """
            SELECT id, feature_flags
            FROM users
            WHERE lower(email) = :email
            LIMIT 1
            """
        ),
        {"email": ADMIN_EMAIL},
    ).mappings().first()
    if user_row is None:
        return
    flags = _decode_flags(user_row["feature_flags"])
    flags.pop("amwaychina_console", None)
    bind.execute(
        sa.text(
            """
            UPDATE users
            SET feature_flags = :feature_flags, updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
            """
        ),
        {
            "user_id": str(user_row["id"]),
            "feature_flags": json.dumps(flags, ensure_ascii=False),
        },
    )

"""add board run origin event id

Revision ID: 034
Revises: 033
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "034"
down_revision: str | None = "033"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(bind: sa.engine.Connection, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind: sa.engine.Connection, table_name: str, column_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(bind).get_columns(table_name)
    )


def _has_index(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(bind).get_indexes(table_name)
    )


def _has_unique_constraint(
    bind: sa.engine.Connection,
    table_name: str,
    constraint_name: str,
) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(bind).get_unique_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "board_runs"):
        return
    if not _has_column(bind, "board_runs", "origin_event_id"):
        op.add_column(
            "board_runs",
            sa.Column("origin_event_id", sa.String(length=180), nullable=True),
        )
    if not _has_index(bind, "board_runs", "ix_board_runs_origin_event_id"):
        op.create_index(
            "ix_board_runs_origin_event_id",
            "board_runs",
            ["origin_event_id"],
        )
    if not _has_unique_constraint(
        bind,
        "board_runs",
        "uq_board_runs_entity_user_origin_event",
    ):
        op.create_unique_constraint(
            "uq_board_runs_entity_user_origin_event",
            "board_runs",
            ["entity_id", "created_by_user_id", "origin_event_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "board_runs"):
        return
    if _has_unique_constraint(
        bind,
        "board_runs",
        "uq_board_runs_entity_user_origin_event",
    ):
        op.drop_constraint(
            "uq_board_runs_entity_user_origin_event",
            "board_runs",
            type_="unique",
        )
    if _has_index(bind, "board_runs", "ix_board_runs_origin_event_id"):
        op.drop_index("ix_board_runs_origin_event_id", table_name="board_runs")
    if _has_column(bind, "board_runs", "origin_event_id"):
        op.drop_column("board_runs", "origin_event_id")

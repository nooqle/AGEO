"""Database configuration."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_MIGRATIONS_DIR = _BACKEND_DIR / "alembic" / "versions"

# Check database type
is_sqlite = settings.is_sqlite

# Create engine with appropriate connect args
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)

# Create session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for models
Base = declarative_base()


def _extract_revision_metadata(path: Path) -> tuple[str | None, list[str]]:
    """Read revision/down_revision metadata from a migration file."""
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision: str | None = None
    down_revisions: list[str] = []

    def _read_literal(value: ast.AST) -> Any:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None

    for node in module.body:
        targets: list[ast.Name] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = [target for target in node.targets if isinstance(target, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value

        if value is None:
            continue

        for target in targets:
            if target.id == "revision":
                literal = _read_literal(value)
                if isinstance(literal, str):
                    revision = literal
            elif target.id == "down_revision":
                literal = _read_literal(value)
                if isinstance(literal, str):
                    down_revisions = [literal]
                elif isinstance(literal, (tuple, list, set)):
                    down_revisions = [
                        item for item in literal if isinstance(item, str)
                    ]

    return revision, down_revisions


def _get_current_alembic_head() -> str | None:
    """Resolve the current alembic head revision from local migration files."""
    revisions: set[str] = set()
    referenced_revisions: set[str] = set()

    for path in sorted(_MIGRATIONS_DIR.glob("*.py")):
        revision, down_revisions = _extract_revision_metadata(path)
        if revision is None:
            continue
        revisions.add(revision)
        referenced_revisions.update(down_revisions)

    heads = revisions - referenced_revisions
    if len(heads) != 1:
        logger.warning(
            "[DB] Unable to determine a single Alembic head. heads=%s",
            sorted(heads),
        )
        return None

    return next(iter(heads))


def _list_user_tables(sync_connection) -> set[str]:
    """List non-system tables for the current database."""
    inspector = inspect(sync_connection)
    return {
        table_name
        for table_name in inspector.get_table_names()
        if not table_name.startswith("sqlite_")
    }


def _stamp_alembic_head(sync_connection, revision: str) -> None:
    """Write the current Alembic head into alembic_version."""
    sync_connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    )
    sync_connection.execute(text("DELETE FROM alembic_version"))
    sync_connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": revision},
    )


async def get_db():
    """Get database session.

    Yields:
        Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables for local/dev startup.

    The historical Alembic chain in this repo predates the current ORM schema.
    For a brand-new local PostgreSQL database we bootstrap from ORM metadata and
    stamp the database to the current migration head so subsequent
    ``alembic upgrade head`` runs are no-ops instead of replaying the old chain
    against an already-created schema.
    """
    async with engine.begin() as conn:
        existing_tables = await conn.run_sync(_list_user_tables)
        if settings.is_postgres and "alembic_version" in existing_tables:
            logger.info(
                "[DB] Existing PostgreSQL schema has alembic_version; "
                "skipping ORM create_all bootstrap. Run Alembic migrations "
                "for schema changes."
            )
            return

        await conn.run_sync(Base.metadata.create_all)
        if settings.is_postgres and not existing_tables:
            head_revision = _get_current_alembic_head()
            if head_revision:
                await conn.run_sync(_stamp_alembic_head, head_revision)
                logger.info(
                    "[DB] Fresh PostgreSQL schema bootstrapped and stamped at Alembic head %s",
                    head_revision,
                )
        elif settings.is_postgres and "alembic_version" not in existing_tables:
            logger.warning(
                "[DB] PostgreSQL schema exists without alembic_version; startup kept ORM bootstrap "
                "but did not auto-stamp because the database is not empty."
            )

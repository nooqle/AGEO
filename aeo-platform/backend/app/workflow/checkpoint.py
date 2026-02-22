"""Checkpoint configuration for LangGraph state persistence.

This module configures Postgres-based checkpointing for workflow state.
"""

import importlib

from app.config import get_settings


def get_checkpointer():
    """Get Postgres checkpointer instance.

    Returns:
        Configured PostgresSaver for state persistence
    """
    settings = get_settings()

    # Convert asyncpg URL to psycopg URL for LangGraph
    # LangGraph uses psycopg (sync) for checkpointing
    connection_string = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    postgres_module = importlib.import_module("langgraph.checkpoint.postgres")
    PostgresSaver = postgres_module.PostgresSaver
    return PostgresSaver(conn_string=connection_string)


async def setup_checkpoint_tables():
    """Setup checkpoint tables in database.

    This should be called during application startup.
    Runs Alembic migrations asynchronously to avoid blocking.
    """
    import asyncio
    import logging
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    logger = logging.getLogger(__name__)

    try:
        # Get alembic.ini path
        backend_dir = Path(__file__).parent.parent.parent
        alembic_ini = backend_dir / "alembic.ini"

        if not alembic_ini.exists():
            logger.warning(
                f"alembic.ini not found at {alembic_ini}, skipping checkpoint setup"
            )
            return

        logger.info("Setting up checkpoint tables via Alembic...")

        alembic_cfg = Config(str(alembic_ini))

        # Run in thread pool to avoid blocking
        await asyncio.to_thread(
            command.upgrade,
            alembic_cfg,
            "head",  # Use "head" instead of hardcoded version
        )

        logger.info("Checkpoint tables setup completed")

    except Exception as e:
        logger.error(f"Failed to setup checkpoint tables: {e}", exc_info=True)
        logger.warning("Application will continue without checkpoint setup")

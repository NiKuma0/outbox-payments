"""Postgres plumbing shared by contract and integration tests.

Tests run against a dedicated ``payments_test`` database on the compose Postgres, so
they never wipe the data of a running demo stack.
"""

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://payments:payments@localhost:5432/payments_test",
)


async def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(
        target.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await admin.dispose()


async def prepare_database(url: str = TEST_DATABASE_URL) -> str:
    """Create the test database and migrate it to head. Returns the URL."""
    await _create_database_if_missing(url)
    config = Config(REPO_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False

    await asyncio.to_thread(command.upgrade, config, "head")
    return url


async def truncate_all(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE payments, outbox"))

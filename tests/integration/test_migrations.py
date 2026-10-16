"""The hand-written migration must produce exactly the schema the models describe."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from outbox_payments.adapters.db.models import Base

pytestmark = pytest.mark.anyio


def _diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, Base.metadata))


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        diff = await connection.run_sync(_diff)

    assert diff == []

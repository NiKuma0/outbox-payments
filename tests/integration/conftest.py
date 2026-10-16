from collections.abc import AsyncIterator

import pytest
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from outbox_payments.adapters.db.session import create_engine, create_session_factory
from tests.support.postgres import prepare_database, truncate_all
from tests.support.rabbit import confirming_broker, reset_topology


@pytest.fixture(scope="session")
async def database_url() -> str:
    return await prepare_database()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    await truncate_all(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
async def broker() -> AsyncIterator[RabbitBroker]:
    broker = confirming_broker()
    await broker.connect()
    await reset_topology(broker)
    try:
        yield broker
    finally:
        await broker.stop()

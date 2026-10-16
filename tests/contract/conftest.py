"""The SQL backend for the repository contract suites.

Unit tests mock the repositories; these suites pin down what the mocks take for
granted (the unique idempotency key, rollback, isolation, row locks) on real Postgres.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from outbox_payments.adapters.db.repositories import (
    SqlOutboxRepository,
    SqlPaymentRepository,
)
from outbox_payments.adapters.db.session import create_engine, create_session_factory
from outbox_payments.application.ports import (
    OutboxRepository,
    PaymentRepository,
    Transaction,
)
from tests.support.postgres import prepare_database, truncate_all


@dataclass(frozen=True)
class UnitOfWork:
    payments: PaymentRepository
    outbox: OutboxRepository
    transaction: Transaction


class Backend(Protocol):
    def session(self) -> AbstractAsyncContextManager[UnitOfWork]:
        """A fresh transaction; anything not committed is rolled back on exit."""
        ...


class SqlBackend:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[UnitOfWork]:
        async with self._sessions() as session:
            yield UnitOfWork(
                SqlPaymentRepository(session), SqlOutboxRepository(session), session
            )


@pytest.fixture(scope="session")
async def database_url() -> str:
    return await prepare_database()


@pytest.fixture
async def backend(database_url: str) -> AsyncIterator[Backend]:
    engine = create_engine(database_url)
    await truncate_all(engine)
    try:
        yield SqlBackend(create_session_factory(engine))
    finally:
        await engine.dispose()

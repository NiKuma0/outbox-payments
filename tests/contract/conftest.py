"""Backends for the port contract suites.

Every contract test runs twice: against the in-memory fake (marked ``unit``) and
against the SQL adapter on real Postgres (marked ``integration``). If the fake ever
drifts from Postgres semantics, the ``unit`` and ``integration`` runs disagree.
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
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
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


class MemoryBackend:
    def __init__(self) -> None:
        self.store = InMemoryStore()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[UnitOfWork]:
        tx = self.store.begin()
        try:
            yield UnitOfWork(
                InMemoryPaymentRepository(tx), InMemoryOutboxRepository(tx), tx
            )
        finally:
            await tx.rollback()


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


@pytest.fixture(
    params=[
        pytest.param("memory", marks=pytest.mark.unit),
        pytest.param("sql", marks=pytest.mark.integration),
    ]
)
async def backend(
    request: pytest.FixtureRequest, database_url: str
) -> AsyncIterator[Backend]:
    if request.param == "memory":
        yield MemoryBackend()
        return
    # url: str = request.getfixturevalue("database_url")
    engine = create_engine(database_url)
    await truncate_all(engine)
    try:
        yield SqlBackend(create_session_factory(engine))
    finally:
        await engine.dispose()

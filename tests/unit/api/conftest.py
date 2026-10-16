"""An API wired to in-memory fakes through FastAPI's own dependency overrides."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from outbox_payments.application.use_cases.create_payment import CreatePayment
from outbox_payments.application.use_cases.get_payment import GetPayment
from outbox_payments.config import Settings
from outbox_payments.entrypoints.api import deps
from outbox_payments.entrypoints.api.app import create_app
from tests.cases.api.auth import API_KEY
from tests.fakes.clock import FrozenClock
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
)


class ProbeSwitch:
    def __init__(self) -> None:
        self.database_up = True
        self.broker_up = True

    async def database(self) -> bool:
        return self.database_up

    async def broker(self) -> bool:
        return self.broker_up


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def probes() -> ProbeSwitch:
    return ProbeSwitch()


@pytest.fixture
async def client(
    store: InMemoryStore, probes: ProbeSwitch
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(api_key=SecretStr(API_KEY)))
    clock = FrozenClock()

    def create_payment() -> CreatePayment:
        tx = store.begin()
        return CreatePayment(
            payments=InMemoryPaymentRepository(tx),
            outbox=InMemoryOutboxRepository(tx),
            transaction=tx,
            clock=clock,
        )

    def get_payment() -> GetPayment:
        return GetPayment(payments=InMemoryPaymentRepository(store.begin()))

    app.dependency_overrides[deps.get_create_payment] = create_payment
    app.dependency_overrides[deps.get_get_payment] = get_payment
    app.dependency_overrides[deps.get_readiness_probes] = lambda: {
        "database": probes.database,
        "broker": probes.broker,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://api.test", headers={"X-API-Key": API_KEY}
    ) as client:
        yield client

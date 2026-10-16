"""An API wired to mocked repositories through FastAPI's own dependency overrides."""

from collections.abc import AsyncIterator
from unittest.mock import Mock

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
from tests.support.mocks import mock_outbox, mock_payments, mock_transaction


class ProbeSwitch:
    def __init__(self) -> None:
        self.database_up = True
        self.broker_up = True

    async def database(self) -> bool:
        return self.database_up

    async def broker(self) -> bool:
        return self.broker_up


@pytest.fixture
def payments() -> Mock:
    return mock_payments()


@pytest.fixture
def outbox() -> Mock:
    return mock_outbox()


@pytest.fixture
def transaction() -> Mock:
    return mock_transaction()


@pytest.fixture
def probes() -> ProbeSwitch:
    return ProbeSwitch()


@pytest.fixture
async def client(
    payments: Mock, outbox: Mock, transaction: Mock, probes: ProbeSwitch
) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(api_key=SecretStr(API_KEY)))
    clock = FrozenClock()

    def create_payment() -> CreatePayment:
        return CreatePayment(
            payments=payments,
            outbox=outbox,
            transaction=transaction,
            clock=clock,
        )

    def get_payment() -> GetPayment:
        return GetPayment(payments=payments)

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

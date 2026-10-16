from uuid import uuid7

import pytest

from outbox_payments.application.errors import PaymentNotFoundError
from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.get_payment import GetPayment
from tests.cases.application.create_payment import BASE_REQUEST
from tests.fakes.clock import FrozenClock
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
)

pytestmark = pytest.mark.anyio


async def test_returns_a_stored_payment() -> None:
    store = InMemoryStore()
    tx = store.begin()
    created = await CreatePayment(
        payments=InMemoryPaymentRepository(tx),
        outbox=InMemoryOutboxRepository(tx),
        transaction=tx,
        clock=FrozenClock(),
    ).execute(CreatePaymentCommand(**BASE_REQUEST))

    found = await GetPayment(payments=InMemoryPaymentRepository(store.begin())).execute(created.id)

    assert found == created


async def test_unknown_payment_is_reported() -> None:
    get_payment = GetPayment(payments=InMemoryPaymentRepository(InMemoryStore().begin()))

    with pytest.raises(PaymentNotFoundError):
        await get_payment.execute(uuid7())

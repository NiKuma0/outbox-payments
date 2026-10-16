import pytest

from outbox_payments.application.errors import IdempotencyKeyConflictError
from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.domain import PaymentStatus
from tests.cases._helpers import as_params
from tests.cases.application.create_payment import (
    BASE_REQUEST,
    IDEMPOTENCY_CASES,
    CreatePaymentRequest,
    IdempotencyCase,
)
from tests.fakes.clock import FrozenClock
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
    InMemoryTransaction,
)

pytestmark = pytest.mark.anyio


def use_case(tx: InMemoryTransaction, clock: FrozenClock) -> CreatePayment:
    return CreatePayment(
        payments=InMemoryPaymentRepository(tx),
        outbox=InMemoryOutboxRepository(tx),
        transaction=tx,
        clock=clock,
    )


def command(request: CreatePaymentRequest) -> CreatePaymentCommand:
    return CreatePaymentCommand(**request)


async def test_payment_and_its_event_are_committed_together() -> None:
    store, clock = InMemoryStore(), FrozenClock()

    payment = await use_case(store.begin(), clock).execute(command(BASE_REQUEST))

    assert payment.status is PaymentStatus.PENDING
    assert payment.created_at == clock.now()
    assert list(store.payments) == [payment.id]
    [message] = store.outbox.values()
    assert message.aggregate_id == payment.id
    assert message.event_type == "payment.created"
    assert message.payload["payment_id"] == str(payment.id)
    assert message.published_at is None
    assert store.commits == 1


async def test_nothing_is_persisted_when_commit_fails() -> None:
    store = InMemoryStore()
    tx = store.begin()
    tx.fail_next_commit = ConnectionError("db went away")

    with pytest.raises(ConnectionError):
        await use_case(tx, FrozenClock()).execute(command(BASE_REQUEST))

    assert store.payments == {}
    assert store.outbox == {}


@pytest.mark.parametrize("case", as_params(IDEMPOTENCY_CASES))
async def test_idempotency(case: IdempotencyCase) -> None:
    store, clock = InMemoryStore(), FrozenClock()
    first = await use_case(store.begin(), clock).execute(command(BASE_REQUEST))
    second_request: CreatePaymentRequest = {**BASE_REQUEST, **case["second_request"]}

    if case["expected"] == "conflict":
        with pytest.raises(IdempotencyKeyConflictError):
            await use_case(store.begin(), clock).execute(command(second_request))
    else:
        second = await use_case(store.begin(), clock).execute(command(second_request))
        assert (second.id == first.id) is (case["expected"] == "same-payment")

    assert len(store.payments) == case["expected_payments"]
    assert len(store.outbox) == case["expected_outbox_records"]

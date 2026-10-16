from unittest.mock import Mock, call

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
from tests.support.mocks import mock_outbox, mock_payments, mock_transaction

pytestmark = pytest.mark.anyio


class Ports:
    def __init__(self) -> None:
        # One parent mock, so the order of calls across the ports can be asserted.
        self.calls = Mock()
        self.calls.attach_mock(mock_payments(), "payments")
        self.calls.attach_mock(mock_outbox(), "outbox")
        self.calls.attach_mock(mock_transaction(), "transaction")
        self.payments: Mock = self.calls.payments
        self.outbox: Mock = self.calls.outbox
        self.transaction: Mock = self.calls.transaction
        self.clock = FrozenClock()

    def use_case(self) -> CreatePayment:
        return CreatePayment(
            payments=self.payments,
            outbox=self.outbox,
            transaction=self.transaction,
            clock=self.clock,
        )


def command(request: CreatePaymentRequest) -> CreatePaymentCommand:
    return CreatePaymentCommand(**request)


async def test_payment_and_its_event_are_committed_together() -> None:
    ports = Ports()

    payment = await ports.use_case().execute(command(BASE_REQUEST))

    assert payment.status is PaymentStatus.PENDING
    assert payment.created_at == ports.clock.now()
    message = ports.outbox.add.await_args.args[0]
    assert message.aggregate_id == payment.id
    assert message.event_type == "payment.created"
    assert message.payload["payment_id"] == str(payment.id)
    assert message.published_at is None
    assert ports.calls.mock_calls == [
        call.payments.add_if_absent(payment),
        call.outbox.add(message),
        call.transaction.commit(),
    ]


async def test_failed_commit_is_not_reported_as_accepted() -> None:
    """The API answers 202 only after the commit; rolling back is the session's job."""
    ports = Ports()
    ports.transaction.commit.side_effect = ConnectionError("db went away")

    with pytest.raises(ConnectionError):
        await ports.use_case().execute(command(BASE_REQUEST))


@pytest.mark.parametrize("case", as_params(IDEMPOTENCY_CASES))
async def test_idempotency(case: IdempotencyCase) -> None:
    ports = Ports()
    first = await ports.use_case().execute(command(BASE_REQUEST))
    second_request: CreatePaymentRequest = {**BASE_REQUEST, **case["second_request"]}
    # The unique index on the key decides; answer the way Postgres would.
    key_taken = second_request["idempotency_key"] == BASE_REQUEST["idempotency_key"]
    ports.payments.add_if_absent.return_value = not key_taken
    ports.payments.get_by_idempotency_key.return_value = first

    if case["expected"] == "conflict":
        with pytest.raises(IdempotencyKeyConflictError):
            await ports.use_case().execute(command(second_request))
    else:
        second = await ports.use_case().execute(command(second_request))
        assert (second.id == first.id) is (case["expected"] == "same-payment")

    # Every stored payment is committed exactly once, together with its event.
    assert ports.transaction.commit.await_count == case["expected_payments"]
    assert ports.outbox.add.await_count == case["expected_outbox_records"]

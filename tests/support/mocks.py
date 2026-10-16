"""Autospec'd mocks of the persistence ports, for unit tests.

``create_autospec`` keeps them honest: calling a method the Protocol does not declare,
or with the wrong signature, fails the test. What only a database guarantees (the
unique idempotency key, rollback, row locks) is not emulated here: the contract suites
in ``tests/contract`` check it against real Postgres.
"""

from copy import deepcopy
from unittest.mock import Mock, create_autospec
from uuid import UUID

from outbox_payments.application.ports import (
    EventPublisher,
    OutboxRepository,
    PaymentRepository,
    Transaction,
)
from outbox_payments.domain import Payment


def mock_payments(stored: Payment | None = None) -> Mock:
    """A PaymentRepository on which every insert wins and every completion applies."""
    payments: Mock = create_autospec(PaymentRepository, instance=True)
    payments.add_if_absent.return_value = True
    payments.complete_if_pending.return_value = True
    serve(payments, stored)
    return payments


def serve(payments: Mock, *stored: Payment | None) -> None:
    """Make ``payments.get`` return fresh copies of ``stored``, one per call, in order.

    A copy per call is what a new SELECT returns: a use case mutating the payment it
    loaded must not change what the next load sees. The last one is repeated; ids that
    do not match get ``None``.
    """
    answers = list(stored)

    def get(payment_id: UUID) -> Payment | None:
        payment = answers.pop(0) if len(answers) > 1 else answers[0]
        return deepcopy(payment) if payment and payment.id == payment_id else None

    payments.get.side_effect = get


def mock_outbox() -> Mock:
    outbox: Mock = create_autospec(OutboxRepository, instance=True)
    outbox.claim_batch.return_value = []
    return outbox


def mock_transaction() -> Mock:
    return create_autospec(Transaction, instance=True)


def mock_publisher() -> Mock:
    return create_autospec(EventPublisher, instance=True)

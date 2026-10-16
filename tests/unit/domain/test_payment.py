from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from outbox_payments.domain import (
    ChargeOutcome,
    Currency,
    InvalidStatusTransitionError,
    Money,
    Payment,
    PaymentCreated,
    PaymentStatus,
)
from tests.cases._helpers import as_params
from tests.cases.domain.payment import (
    CHARGE_OUTCOME_CASES,
    STATUS_TRANSITION_CASES,
    ChargeOutcomeCase,
    StatusTransitionCase,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def new_payment() -> tuple[Payment, PaymentCreated]:
    return Payment.create(
        money=Money(Decimal("100.00"), Currency.RUB),
        description="Order #42",
        metadata={"order_id": 42},
        webhook_url="http://example.test/hook",
        idempotency_key="key-1",
        request_hash="hash",
        now=NOW,
    )


@pytest.mark.parametrize("case", as_params(STATUS_TRANSITION_CASES))
def test_status_transitions(case: StatusTransitionCase) -> None:
    assert case["current"].can_transition_to(case["target"]) is case["allowed"]


def test_new_payment_is_pending_and_emits_created_event() -> None:
    payment, event = new_payment()

    assert payment.status is PaymentStatus.PENDING
    assert payment.created_at == NOW
    assert payment.processed_at is None
    assert payment.webhook_delivered_at is None
    assert payment.id.version == 7
    assert event.payment_id == payment.id
    assert event.event_id.version == 7
    assert event.event_id != payment.id
    assert event.occurred_at == NOW


@pytest.mark.parametrize("case", as_params(CHARGE_OUTCOME_CASES))
def test_charge_outcome_completes_payment(case: ChargeOutcomeCase) -> None:
    payment, _ = new_payment()
    later = NOW + timedelta(seconds=3)

    payment.complete(case["outcome"], now=later)

    assert payment.status is case["expected_status"]
    assert payment.processed_at == later


@pytest.mark.parametrize("outcome", list(ChargeOutcome))
def test_completed_payment_cannot_be_completed_again(outcome: ChargeOutcome) -> None:
    payment, _ = new_payment()
    payment.complete(ChargeOutcome.APPROVED, now=NOW)

    with pytest.raises(InvalidStatusTransitionError):
        payment.complete(outcome, now=NOW)


def test_webhook_delivery_is_recorded_once_payment_is_final() -> None:
    payment, _ = new_payment()
    payment.complete(ChargeOutcome.DECLINED, now=NOW)

    payment.mark_webhook_delivered(now=NOW)

    assert payment.webhook_delivered_at == NOW


def test_webhook_cannot_be_delivered_for_pending_payment() -> None:
    payment, _ = new_payment()

    with pytest.raises(InvalidStatusTransitionError):
        payment.mark_webhook_delivered(now=NOW)

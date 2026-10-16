"""Plain builder functions for test objects (no factory library needed)."""

from datetime import UTC, datetime
from decimal import Decimal

from outbox_payments.application.outbox import OutboxMessage, outbox_message_for
from outbox_payments.domain import Currency, Money, Payment

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_payment(
    *, idempotency_key: str = "key-1", now: datetime = T0, request_hash: str = "hash"
) -> tuple[Payment, OutboxMessage]:
    payment, event = Payment.create(
        money=Money(Decimal("100.00"), Currency.RUB),
        description="Order #42",
        metadata={"order_id": 42, "nested": {"tags": ["a", "b"]}},
        webhook_url="http://webhook-sink:8080/hook",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        now=now,
    )
    return payment, outbox_message_for(event)

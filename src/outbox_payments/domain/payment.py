"""The Payment aggregate."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid7

from outbox_payments.domain.errors import InvalidStatusTransitionError
from outbox_payments.domain.events import PaymentCreated
from outbox_payments.domain.money import Money
from outbox_payments.domain.status import ChargeOutcome, PaymentStatus
from outbox_payments.domain.types import JsonObject


@dataclass(slots=True, kw_only=True)
class Payment:
    """A request to charge money, plus everything that happened to it since.

    ``webhook_delivered_at`` is not part of the public API: it is the consumer's
    checkpoint that lets a redelivered message skip a webhook that already went out.
    """

    id: UUID = field(default_factory=uuid7)
    money: Money
    description: str
    metadata: JsonObject
    webhook_url: str
    idempotency_key: str
    request_hash: str
    status: PaymentStatus = PaymentStatus.PENDING
    created_at: datetime
    processed_at: datetime | None = None
    webhook_delivered_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        money: Money,
        description: str,
        metadata: JsonObject,
        webhook_url: str,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> tuple[Payment, PaymentCreated]:
        payment = cls(
            money=money,
            description=description,
            metadata=metadata,
            webhook_url=webhook_url,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            created_at=now,
        )
        return payment, PaymentCreated(payment_id=payment.id, occurred_at=now)

    def complete(self, outcome: ChargeOutcome, *, now: datetime) -> None:
        target = outcome.final_status
        if not self.status.can_transition_to(target):
            raise InvalidStatusTransitionError(
                f"payment {self.id}: {self.status} -> {target} is not allowed"
            )
        self.status = target
        self.processed_at = now

    def mark_webhook_delivered(self, *, now: datetime) -> None:
        if not self.status.is_final:
            raise InvalidStatusTransitionError(
                f"payment {self.id}: webhook can only be delivered for a final status"
            )
        self.webhook_delivered_at = now

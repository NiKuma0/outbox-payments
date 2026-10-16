"""CreatePayment: accept a payment request exactly once per idempotency key."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from outbox_payments.application.errors import IdempotencyKeyConflictError
from outbox_payments.application.outbox import outbox_message_for
from outbox_payments.application.ports import (
    Clock,
    OutboxRepository,
    PaymentRepository,
    Transaction,
)
from outbox_payments.domain import (
    Currency,
    JsonObject,
    Money,
    Payment,
    request_fingerprint,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatePaymentCommand:
    idempotency_key: str
    amount: Decimal
    currency: Currency
    description: str
    metadata: JsonObject
    webhook_url: str


class CreatePayment:
    """Insert the payment and its outbox record in one transaction.

    Idempotency relies on the unique index, not on a prior lookup: the insert either
    wins (``ON CONFLICT DO NOTHING`` returned a row) or we load the winner and compare
    request fingerprints. A SELECT-then-INSERT would race between concurrent retries.
    """

    def __init__(
        self,
        *,
        payments: PaymentRepository,
        outbox: OutboxRepository,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._payments = payments
        self._outbox = outbox
        self._transaction = transaction
        self._clock = clock

    async def execute(self, command: CreatePaymentCommand) -> Payment:
        money = Money(command.amount, command.currency)
        request_hash = request_fingerprint(
            money=money,
            description=command.description,
            metadata=command.metadata,
            webhook_url=command.webhook_url,
        )
        payment, event = Payment.create(
            money=money,
            description=command.description,
            metadata=command.metadata,
            webhook_url=command.webhook_url,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            now=self._clock.now(),
        )

        if await self._payments.add_if_absent(payment):
            await self._outbox.add(outbox_message_for(event))
            # Commit before returning: the API must never answer 202 for a payment
            # that is not durable yet.
            await self._transaction.commit()
            logger.info(
                "payment accepted",
                extra={"payment_id": str(payment.id), "event_id": str(event.event_id)},
            )
            return payment

        existing = await self._payments.get_by_idempotency_key(command.idempotency_key)
        if existing is None:  # pragma: no cover - the conflicting row cannot vanish
            raise RuntimeError("idempotency key conflict without a stored payment")
        if existing.request_hash != request_hash:
            raise IdempotencyKeyConflictError(command.idempotency_key)
        logger.info("idempotent replay", extra={"payment_id": str(existing.id)})
        return existing

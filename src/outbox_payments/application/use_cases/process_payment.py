"""ProcessPayment: charge, persist the outcome, notify the client.

The use case is a resumable state machine keyed on what is already durable:

1. ``pending``                 -> charge (gateway idempotency key = payment id),
                                  conditional UPDATE, commit.
2. ``webhook_delivered_at`` NULL -> send the webhook, record delivery, commit.
3. otherwise                   -> nothing left to do; the caller acks.

A crash between any two steps leaves the message unacknowledged; redelivery re-enters
at the first step whose effect is not yet committed. The only step that can run twice
is an external call, and both are idempotent on the other side: the gateway by key,
the webhook receiver by ``X-Webhook-Id``.
"""

import logging
from uuid import UUID

from outbox_payments.application.errors import PaymentNotFoundError
from outbox_payments.application.ports import (
    Clock,
    PaymentProvider,
    PaymentRepository,
    Transaction,
    WebhookSender,
)
from outbox_payments.application.webhooks import notification_for
from outbox_payments.domain import Payment, PaymentStatus

logger = logging.getLogger(__name__)


class ProcessPayment:
    def __init__(
        self,
        *,
        payments: PaymentRepository,
        provider: PaymentProvider,
        webhooks: WebhookSender,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._payments = payments
        self._provider = provider
        self._webhooks = webhooks
        self._transaction = transaction
        self._clock = clock

    async def execute(self, *, payment_id: UUID, event_id: UUID) -> None:
        payment = await self._load(payment_id)

        if payment.status is PaymentStatus.PENDING:
            payment = await self._charge(payment)

        if payment.webhook_delivered_at is None:
            await self._notify(payment, event_id)
        else:
            logger.info(
                "already processed, nothing to do",
                extra={"payment_id": str(payment.id), "event_id": str(event_id)},
            )

    async def _load(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

    async def _charge(self, payment: Payment) -> Payment:
        # A decline is a business outcome, not an exception: it is persisted and
        # reported to the client like a success, and never retried.
        outcome = await self._provider.charge(payment.id, payment.money)
        payment.complete(outcome, now=self._clock.now())
        updated = await self._payments.complete_if_pending(payment)
        await self._transaction.commit()
        if not updated:
            # Someone else finished it first; their outcome wins.
            return await self._load(payment.id)
        logger.info(
            "payment completed",
            extra={"payment_id": str(payment.id), "status": payment.status.value},
        )
        return payment

    async def _notify(self, payment: Payment, event_id: UUID) -> None:
        await self._webhooks.send(notification_for(payment, webhook_id=event_id))
        payment.mark_webhook_delivered(now=self._clock.now())
        await self._payments.mark_webhook_delivered(payment)
        await self._transaction.commit()
        logger.info(
            "webhook delivered",
            extra={"payment_id": str(payment.id), "event_id": str(event_id)},
        )

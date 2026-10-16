"""Ports: what the application needs from the outside world, as Protocols.

Adapters implement them structurally; nothing here knows about SQL, AMQP or HTTP.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from outbox_payments.application.outbox import OutboxMessage
from outbox_payments.application.webhooks import WebhookNotification
from outbox_payments.domain import ChargeOutcome, Money, Payment


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware (UTC)."""
        ...


class Transaction(Protocol):
    """The only piece of the unit of work the application sees.

    Repositories in one use case share a transaction; nothing is durable until
    ``commit()``. Rolling back is the default when a use case raises.
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None:
        """End the current transaction without writing; the next statement opens a new
        one. Use cases call it after a pure read, so no pooled connection sits in an
        open transaction while they wait on the gateway or a webhook receiver."""
        ...


class PaymentRepository(Protocol):
    async def add_if_absent(self, payment: Payment) -> bool:
        """Insert unless the idempotency key is taken. Returns whether it was inserted."""
        ...

    async def get(self, payment_id: UUID) -> Payment | None: ...

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None: ...

    async def complete_if_pending(self, payment: Payment) -> bool:
        """Persist the final status only if the stored row is still ``pending``."""
        ...

    async def mark_webhook_delivered(self, payment: Payment) -> None: ...


class OutboxRepository(Protocol):
    async def add(self, message: OutboxMessage) -> None: ...

    async def claim_batch(self, limit: int) -> Sequence[OutboxMessage]:
        """Lock up to ``limit`` unpublished records, oldest first, skipping locked ones."""
        ...

    async def mark_published(
        self, message_ids: Sequence[UUID], *, at: datetime
    ) -> None: ...

    async def record_failure(self, message_id: UUID, error: str) -> None: ...

    async def delete_published_before(self, cutoff: datetime) -> int: ...


class EventPublisher(Protocol):
    async def publish(self, message: OutboxMessage) -> None:
        """Return only once the broker confirmed the message; raise ``PublishError`` else."""
        ...


class PaymentProvider(Protocol):
    async def charge(self, payment_id: UUID, money: Money) -> ChargeOutcome:
        """Charge once per ``payment_id``.

        ``payment_id`` is the gateway idempotency key: repeating the call returns the
        original outcome instead of charging again.
        """
        ...


class WebhookSender(Protocol):
    async def send(self, notification: WebhookNotification) -> None:
        """Raise ``WebhookTemporarilyUnavailableError`` or ``WebhookRejectedError``."""
        ...

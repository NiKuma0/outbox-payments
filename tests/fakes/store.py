"""In-memory implementations of the persistence ports, with real transaction semantics.

``InMemoryStore`` is the "database": committed state shared across transactions.
``InMemoryTransaction`` reads a snapshot, buffers its writes and applies only the rows
it touched on ``commit()``. A transaction that is dropped without committing leaves no
trace, exactly like a rolled-back ``AsyncSession``, which is what lets unit tests
simulate crashes. Row locks taken by ``claim_batch`` emulate ``FOR UPDATE SKIP LOCKED``
so the same contract suite runs against this fake and against Postgres.
"""

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from outbox_payments.application.outbox import OutboxMessage
from outbox_payments.domain import Payment, PaymentStatus


@dataclass
class InMemoryStore:
    payments: dict[UUID, Payment] = field(default_factory=dict[UUID, Payment])
    outbox: dict[UUID, OutboxMessage] = field(default_factory=dict[UUID, OutboxMessage])
    locks: dict[UUID, InMemoryTransaction] = field(
        default_factory=dict[UUID, "InMemoryTransaction"]
    )
    commits: int = 0

    def begin(self) -> InMemoryTransaction:
        return InMemoryTransaction(self)


class InMemoryTransaction:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store
        self.payments = copy.deepcopy(store.payments)
        self.outbox = dict(store.outbox)
        self.dirty_payments: set[UUID] = set()
        self.dirty_outbox: set[UUID] = set()
        self.fail_next_commit: Exception | None = None

    async def commit(self) -> None:
        if self.fail_next_commit is not None:
            error, self.fail_next_commit = self.fail_next_commit, None
            raise error
        for payment_id in self.dirty_payments:
            self.store.payments[payment_id] = copy.deepcopy(self.payments[payment_id])
        for message_id in self.dirty_outbox:
            if message_id in self.outbox:
                self.store.outbox[message_id] = self.outbox[message_id]
            else:
                self.store.outbox.pop(message_id, None)
        self.dirty_payments.clear()
        self.dirty_outbox.clear()
        self.store.commits += 1
        self.release_locks()

    async def rollback(self) -> None:
        self.payments = copy.deepcopy(self.store.payments)
        self.outbox = dict(self.store.outbox)
        self.dirty_payments.clear()
        self.dirty_outbox.clear()
        self.release_locks()

    def release_locks(self) -> None:
        for message_id in [m for m, owner in self.store.locks.items() if owner is self]:
            del self.store.locks[message_id]


class InMemoryPaymentRepository:
    def __init__(self, tx: InMemoryTransaction) -> None:
        self._tx = tx

    async def add_if_absent(self, payment: Payment) -> bool:
        visible = [*self._tx.payments.values(), *self._tx.store.payments.values()]
        if any(p.idempotency_key == payment.idempotency_key for p in visible):
            return False
        self._tx.payments[payment.id] = copy.deepcopy(payment)
        self._tx.dirty_payments.add(payment.id)
        return True

    async def get(self, payment_id: UUID) -> Payment | None:
        return copy.deepcopy(self._tx.payments.get(payment_id))

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        visible = {**self._tx.store.payments, **self._tx.payments}
        for payment in visible.values():
            if payment.idempotency_key == idempotency_key:
                return copy.deepcopy(payment)
        return None

    async def complete_if_pending(self, payment: Payment) -> bool:
        stored = self._tx.payments.get(payment.id)
        if stored is None or stored.status is not PaymentStatus.PENDING:
            return False
        stored.status = payment.status
        stored.processed_at = payment.processed_at
        self._tx.dirty_payments.add(payment.id)
        return True

    async def mark_webhook_delivered(self, payment: Payment) -> None:
        stored = self._tx.payments.get(payment.id)
        if stored is not None and stored.webhook_delivered_at is None:
            stored.webhook_delivered_at = payment.webhook_delivered_at
            self._tx.dirty_payments.add(payment.id)


class InMemoryOutboxRepository:
    def __init__(self, tx: InMemoryTransaction) -> None:
        self._tx = tx

    def _put(self, message: OutboxMessage) -> None:
        self._tx.outbox[message.id] = message
        self._tx.dirty_outbox.add(message.id)

    async def add(self, message: OutboxMessage) -> None:
        self._put(message)

    async def claim_batch(self, limit: int) -> Sequence[OutboxMessage]:
        locks = self._tx.store.locks
        claimable = sorted(
            (
                m
                for m in self._tx.outbox.values()
                if m.published_at is None and locks.get(m.id, self._tx) is self._tx
            ),
            key=lambda m: (m.created_at, m.id),
        )[:limit]
        for message in claimable:
            locks[message.id] = self._tx
        return claimable

    async def mark_published(self, message_ids: Sequence[UUID], *, at: datetime) -> None:
        for message_id in message_ids:
            self._put(replace(self._tx.outbox[message_id], published_at=at))

    async def record_failure(self, message_id: UUID, error: str) -> None:
        message = self._tx.outbox[message_id]
        self._put(replace(message, attempts=message.attempts + 1, last_error=error))

    async def delete_published_before(self, cutoff: datetime) -> int:
        doomed = [
            m.id
            for m in self._tx.outbox.values()
            if m.published_at is not None and m.published_at < cutoff
        ]
        for message_id in doomed:
            del self._tx.outbox[message_id]
            self._tx.dirty_outbox.add(message_id)
        return len(doomed)

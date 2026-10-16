"""SQL implementations of the persistence ports.

Every write is a single explicit statement whose WHERE clause carries the invariant
(``ON CONFLICT DO NOTHING``, ``status = 'pending'``, ``webhook_delivered_at IS NULL``),
so correctness never depends on what this process read a moment earlier.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from outbox_payments.adapters.db.models import OutboxRow, PaymentRow
from outbox_payments.application.outbox import OutboxMessage
from outbox_payments.domain import Currency, Money, Payment, PaymentStatus


def _to_domain(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        money=Money(row.amount, Currency(row.currency)),
        description=row.description,
        metadata=row.metadata_,
        webhook_url=row.webhook_url,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        status=PaymentStatus(row.status),
        created_at=row.created_at,
        processed_at=row.processed_at,
        webhook_delivered_at=row.webhook_delivered_at,
    )


def _to_message(row: OutboxRow) -> OutboxMessage:
    return OutboxMessage(
        id=row.id,
        event_type=row.event_type,
        aggregate_id=row.aggregate_id,
        payload=row.payload,
        created_at=row.created_at,
        published_at=row.published_at,
        attempts=row.attempts,
        last_error=row.last_error,
    )


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_if_absent(self, payment: Payment) -> bool:
        statement = (
            insert(PaymentRow)
            .values(
                id=payment.id,
                amount=payment.money.amount,
                currency=payment.money.currency.value,
                description=payment.description,
                metadata=payment.metadata,
                status=payment.status.value,
                idempotency_key=payment.idempotency_key,
                request_hash=payment.request_hash,
                webhook_url=payment.webhook_url,
                created_at=payment.created_at,
            )
            # Only the idempotency key may conflict silently; a PK clash is a bug.
            .on_conflict_do_nothing(index_elements=[PaymentRow.idempotency_key])
            .returning(PaymentRow.id)
        )
        inserted = await self._session.scalar(statement)
        return inserted is not None

    async def get(self, payment_id: UUID) -> Payment | None:
        row = await self._session.scalar(
            select(PaymentRow)
            .where(PaymentRow.id == payment_id)
            .execution_options(populate_existing=True)
        )
        return _to_domain(row) if row is not None else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        row = await self._session.scalar(
            select(PaymentRow)
            .where(PaymentRow.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        return _to_domain(row) if row is not None else None

    async def complete_if_pending(self, payment: Payment) -> bool:
        updated = await self._session.scalar(
            update(PaymentRow)
            .where(PaymentRow.id == payment.id, PaymentRow.status == PaymentStatus.PENDING.value)
            .values(status=payment.status.value, processed_at=payment.processed_at)
            .returning(PaymentRow.id)
            .execution_options(synchronize_session=False)
        )
        return updated is not None

    async def mark_webhook_delivered(self, payment: Payment) -> None:
        await self._session.execute(
            update(PaymentRow)
            .where(PaymentRow.id == payment.id, PaymentRow.webhook_delivered_at.is_(None))
            .values(webhook_delivered_at=payment.webhook_delivered_at)
            .execution_options(synchronize_session=False)
        )


class SqlOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> None:
        await self._session.execute(
            insert(OutboxRow).values(
                id=message.id,
                event_type=message.event_type,
                aggregate_id=message.aggregate_id,
                payload=message.payload,
                created_at=message.created_at,
                attempts=message.attempts,
            )
        )

    async def claim_batch(self, limit: int) -> Sequence[OutboxMessage]:
        rows = await self._session.scalars(
            select(OutboxRow)
            .where(OutboxRow.published_at.is_(None))
            .order_by(OutboxRow.created_at, OutboxRow.id)
            .limit(limit)
            # Rows locked by another relay replica are skipped, not waited for.
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return [_to_message(row) for row in rows]

    async def mark_published(self, message_ids: Sequence[UUID], *, at: datetime) -> None:
        await self._session.execute(
            update(OutboxRow)
            .where(OutboxRow.id.in_(message_ids))
            .values(published_at=at)
            .execution_options(synchronize_session=False)
        )

    async def record_failure(self, message_id: UUID, error: str) -> None:
        await self._session.execute(
            update(OutboxRow)
            .where(OutboxRow.id == message_id)
            .values(attempts=OutboxRow.attempts + 1, last_error=error[:2000])
            .execution_options(synchronize_session=False)
        )

    async def delete_published_before(self, cutoff: datetime) -> int:
        deleted = await self._session.scalars(
            delete(OutboxRow)
            .where(OutboxRow.published_at < cutoff)
            .returning(OutboxRow.id)
            .execution_options(synchronize_session=False)
        )
        return len(deleted.all())

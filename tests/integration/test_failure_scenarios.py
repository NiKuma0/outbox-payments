"""Required failure scenarios for ProcessPayment against real Postgres.

The gateway and the webhook receiver are fakes (they are external systems); the
database, transactions and conditional updates are real.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.db.repositories import (
    SqlOutboxRepository,
    SqlPaymentRepository,
)
from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.get_payment import GetPayment
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.domain import ChargeOutcome, Payment, PaymentStatus
from tests.cases.application.create_payment import BASE_REQUEST
from tests.fakes.provider import FakePaymentProvider
from tests.fakes.webhooks import RecordingWebhookSender

pytestmark = pytest.mark.anyio


class ProcessKilledError(BaseException):
    """Stands in for SIGKILL: not an Exception, so nothing in the app swallows it."""


class CrashBeforeCommit:
    """A transaction whose first commit "kills the process" instead of committing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.crashed = False

    async def commit(self) -> None:
        if not self.crashed:
            self.crashed = True
            raise ProcessKilledError
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    provider: FakePaymentProvider
    webhooks: RecordingWebhookSender

    async def accept(self, key: str = "k-1") -> tuple[Payment, UUID]:
        async with self.sessions() as session:
            payment = await CreatePayment(
                payments=SqlPaymentRepository(session),
                outbox=SqlOutboxRepository(session),
                transaction=session,
                clock=SystemClock(),
            ).execute(
                replace(CreatePaymentCommand(**BASE_REQUEST), idempotency_key=key)
            )
            [message] = await SqlOutboxRepository(session).claim_batch(1)
        return payment, message.id

    async def deliver(
        self,
        payment: Payment,
        event_id: UUID,
        transaction: Callable[[AsyncSession], object] | None = None,
    ) -> None:
        async with self.sessions() as session:
            tx = transaction(session) if transaction else session
            await ProcessPayment(
                payments=SqlPaymentRepository(session),
                provider=self.provider,
                webhooks=self.webhooks,
                transaction=tx,  # pyright: ignore[reportArgumentType]
                clock=SystemClock(),
            ).execute(payment_id=payment.id, event_id=event_id)

    async def stored(self, payment: Payment) -> Payment:
        async with self.sessions() as session:
            return await GetPayment(payments=SqlPaymentRepository(session)).execute(
                payment.id
            )


@pytest.fixture
def world(sessions: async_sessionmaker[AsyncSession]) -> World:
    return World(sessions, FakePaymentProvider(), RecordingWebhookSender())


async def test_duplicate_event_charges_exactly_once(world: World) -> None:
    payment, event_id = await world.accept()

    for _ in range(3):
        await world.deliver(payment, event_id)

    assert world.provider.calls == [payment.id]
    assert len(world.webhooks.delivered) == 1
    assert (await world.stored(payment)).status is PaymentStatus.SUCCEEDED


async def test_crash_after_charge_before_commit(world: World) -> None:
    world.provider.outcome = ChargeOutcome.DECLINED
    payment, event_id = await world.accept()

    with pytest.raises(ProcessKilledError):
        await world.deliver(payment, event_id, transaction=CrashBeforeCommit)
    assert (await world.stored(payment)).status is PaymentStatus.PENDING  # rolled back

    await world.deliver(payment, event_id)  # redelivery

    stored = await world.stored(payment)
    assert stored.status is PaymentStatus.FAILED
    assert world.provider.calls == [payment.id, payment.id]
    assert world.provider.charges == 1  # gateway idempotency key = payment id
    assert len(world.webhooks.delivered) == 1


async def test_crash_after_commit_before_webhook(world: World) -> None:
    payment, event_id = await world.accept()
    world.webhooks.failures.append(ProcessKilledError())  # pyright: ignore[reportArgumentType]

    with pytest.raises(ProcessKilledError):
        await world.deliver(payment, event_id)
    committed = await world.stored(payment)
    assert committed.status is PaymentStatus.SUCCEEDED
    assert committed.webhook_delivered_at is None

    await world.deliver(payment, event_id)  # redelivery

    assert world.provider.calls == [payment.id]  # not charged again
    assert (await world.stored(payment)).webhook_delivered_at is not None
    assert [w.webhook_id for w in world.webhooks.delivered] == [event_id]

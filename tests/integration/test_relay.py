"""Relay against real Postgres and RabbitMQ."""

import asyncio
import json
from dataclasses import replace

import pytest
from faststream.rabbit import RabbitBroker, RabbitQueue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.db.models import OutboxRow
from outbox_payments.adapters.db.repositories import (
    SqlOutboxRepository,
    SqlPaymentRepository,
)
from outbox_payments.adapters.messaging.publisher import RabbitEventPublisher
from outbox_payments.adapters.messaging.topology import PAYMENTS_EXCHANGE, ROUTING_KEY
from outbox_payments.application.errors import PublishError
from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.relay_outbox import RelayOutbox
from tests.cases.application.create_payment import BASE_REQUEST
from tests.support.builders import make_payment
from tests.support.rabbit import drain

pytestmark = pytest.mark.anyio


async def accept(sessions: async_sessionmaker[AsyncSession], count: int) -> None:
    for n in range(count):
        async with sessions() as session:
            await CreatePayment(
                payments=SqlPaymentRepository(session),
                outbox=SqlOutboxRepository(session),
                transaction=session,
                clock=SystemClock(),
            ).execute(
                replace(CreatePaymentCommand(**BASE_REQUEST), idempotency_key=f"k-{n}")
            )


async def drain_outbox(
    sessions: async_sessionmaker[AsyncSession], broker: RabbitBroker, batch_size: int
) -> None:
    publisher = RabbitEventPublisher(broker)
    while True:
        async with sessions() as session:
            published = await RelayOutbox(
                outbox=SqlOutboxRepository(session),
                publisher=publisher,
                transaction=session,
                clock=SystemClock(),
            ).run_once(batch_size=batch_size)
        if published == 0:
            return


async def test_two_concurrent_relays_publish_every_event_exactly_once(
    sessions: async_sessionmaker[AsyncSession], broker: RabbitBroker
) -> None:
    await accept(sessions, 30)

    await asyncio.gather(
        drain_outbox(sessions, broker, 4), drain_outbox(sessions, broker, 4)
    )

    messages = await drain(broker, "payments.new")
    async with sessions() as session:
        rows = (await session.scalars(select(OutboxRow))).all()
    assert sorted(m.message_id or "" for m in messages) == sorted(
        str(r.id) for r in rows
    )
    assert all(r.published_at is not None for r in rows)
    assert {m.delivery_mode for m in messages} == {2}  # persistent
    body = json.loads(messages[0].body)
    assert set(body) == {"event_id", "payment_id", "occurred_at"}


async def test_unroutable_message_is_not_confirmed(broker: RabbitBroker) -> None:
    exchange = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    queue = await broker.declare_queue(RabbitQueue("payments.new", declare=False))
    await queue.unbind(exchange, routing_key=ROUTING_KEY)
    _, message = make_payment()
    try:
        with pytest.raises(PublishError):
            await RabbitEventPublisher(broker).publish(message)
    finally:
        await queue.bind(exchange, routing_key=ROUTING_KEY)

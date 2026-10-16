"""TTL + dead-lettering on a real RabbitMQ (TestRabbitBroker cannot emulate them)."""

import time

import pytest
from faststream.rabbit import RabbitBroker, RabbitQueue

from tests.support.rabbit import wait_for_messages

pytestmark = pytest.mark.anyio


async def test_retry_queue_returns_message_to_the_work_queue_after_its_ttl(
    broker: RabbitBroker,
) -> None:
    started = time.monotonic()
    await broker.publish(
        b'{"hello": 1}',
        queue="payments.new.retry.1",
        headers={"x-retry-count": 1},
        persist=True,
    )

    bodies = await wait_for_messages(broker, "payments.new", within=5)

    elapsed = time.monotonic() - started
    assert bodies == [b'{"hello": 1}']
    assert 0.9 <= elapsed < 4


async def test_longer_retry_level_holds_the_message_longer(
    broker: RabbitBroker,
) -> None:
    await broker.publish(b"slow", queue="payments.new.retry.2", persist=True)
    await broker.publish(b"fast", queue="payments.new.retry.1", persist=True)

    first = await wait_for_messages(broker, "payments.new", within=3)
    second = await wait_for_messages(broker, "payments.new", within=6)

    # Separate queues per delay: the 1 s message is not stuck behind the 4 s one.
    assert first == [b"fast"]
    assert second == [b"slow"]


async def test_rejected_message_falls_into_the_dlq(broker: RabbitBroker) -> None:
    await broker.publish(b"poison", queue="payments.new", persist=True)
    queue = await broker.declare_queue(RabbitQueue("payments.new", declare=False))
    message = await queue.get(no_ack=False, timeout=5)
    assert message is not None

    await message.reject(requeue=False)

    assert await wait_for_messages(broker, "payments.new.dlq", within=3) == [b"poison"]

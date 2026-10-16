"""RabbitMQ plumbing for integration and e2e tests."""

import os

from aio_pika.abc import AbstractIncomingMessage
from faststream.rabbit import RabbitBroker, RabbitQueue
from faststream.rabbit.schemas import Channel

from outbox_payments.adapters.messaging.retry import (
    DEAD_LETTER_QUEUE,
    PAYMENTS_QUEUE,
    RetryPolicy,
)
from outbox_payments.adapters.messaging.topology import declare_topology

RABBITMQ_URL = os.environ.get("TEST_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TEST_POLICY = RetryPolicy(max_retries=3, base_delay_seconds=1, backoff_factor=4)
ALL_QUEUES = [PAYMENTS_QUEUE, *(level.queue for level in TEST_POLICY.levels), DEAD_LETTER_QUEUE]


def confirming_broker(url: str = RABBITMQ_URL) -> RabbitBroker:
    return RabbitBroker(
        url, default_channel=Channel(publisher_confirms=True, on_return_raises=True), logger=None
    )


async def reset_topology(broker: RabbitBroker) -> None:
    await declare_topology(broker, TEST_POLICY)
    for name in ALL_QUEUES:
        queue = await broker.declare_queue(RabbitQueue(name, declare=False))
        await queue.purge()


async def drain(broker: RabbitBroker, queue_name: str) -> list[AbstractIncomingMessage]:
    queue = await broker.declare_queue(RabbitQueue(queue_name, declare=False))
    messages: list[AbstractIncomingMessage] = []
    while (message := await queue.get(no_ack=True, fail=False, timeout=5)) is not None:
        messages.append(message)
    return messages

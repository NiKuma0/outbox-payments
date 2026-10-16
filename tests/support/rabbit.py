"""RabbitMQ plumbing for integration tests.

Tests run in a dedicated ``payments_test`` virtual host on the compose RabbitMQ, so
they neither purge the queues of a running demo stack nor race its consumer for
messages. e2e tests talk to the stack itself and do not use this module.
"""

import asyncio
import os
import time
from urllib.parse import quote, unquote, urlsplit

import httpx
from aio_pika.abc import AbstractIncomingMessage
from faststream.rabbit import RabbitBroker, RabbitQueue
from faststream.rabbit.schemas import Channel

from outbox_payments.adapters.messaging.retry import (
    DEAD_LETTER_QUEUE,
    PAYMENTS_QUEUE,
    RetryPolicy,
)
from outbox_payments.adapters.messaging.topology import declare_topology

RABBITMQ_URL = os.environ.get(
    "TEST_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/payments_test"
)
RABBITMQ_API_URL = os.environ.get("TEST_RABBITMQ_API_URL", "http://localhost:15672/api")
TEST_POLICY = RetryPolicy(max_retries=3, base_delay_seconds=1, backoff_factor=4)
ALL_QUEUES = [
    PAYMENTS_QUEUE,
    *(level.queue for level in TEST_POLICY.levels),
    DEAD_LETTER_QUEUE,
]


async def prepare_vhost(
    url: str = RABBITMQ_URL, *, api_url: str = RABBITMQ_API_URL
) -> str:
    """Create the test vhost and grant the URL's user full rights on it. Returns the URL.

    Both management API calls are idempotent PUTs, so reruns are harmless.
    """
    target = urlsplit(url)
    vhost = unquote(target.path.removeprefix("/"))
    if vhost in {"", "/"}:
        raise RuntimeError(
            f"refusing to run integration tests on the default vhost of {url!r}: "
            "it is shared with the compose stack; point TEST_RABBITMQ_URL at a "
            "dedicated vhost"
        )
    user = unquote(target.username or "guest")
    password = unquote(target.password or "guest")
    async with httpx.AsyncClient(
        base_url=api_url, auth=(user, password), timeout=10
    ) as client:
        encoded = quote(vhost, safe="")
        (await client.put(f"/vhosts/{encoded}")).raise_for_status()
        (
            await client.put(
                f"/permissions/{encoded}/{quote(user, safe='')}",
                json={"configure": ".*", "write": ".*", "read": ".*"},
            )
        ).raise_for_status()
    return url


def confirming_broker(url: str = RABBITMQ_URL) -> RabbitBroker:
    return RabbitBroker(
        url,
        default_channel=Channel(publisher_confirms=True, on_return_raises=True),
        logger=None,
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


async def wait_for_messages(
    broker: RabbitBroker, queue: str, *, within: float
) -> list[bytes]:
    """Poll ``queue`` until it has messages (consuming them) or ``within`` passes."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if messages := await drain(broker, queue):
            return [m.body for m in messages]
        await asyncio.sleep(0.2)
    return []

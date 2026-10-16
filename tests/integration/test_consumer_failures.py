"""The consumer's last line of defence, on a real RabbitMQ.

Normally a failed message is republished to a retry queue or the DLQ and then acked.
If that republish itself fails, the handler raises, and the message must be
*rejected* (dead-lettered into the DLQ by the work queue's DLX), not requeued: a
requeue would redeliver it at once, forever, re-running the use case each time.
"""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from faststream.rabbit import RabbitBroker, RabbitQueue

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.messaging.retry import retry_queue_name
from outbox_payments.adapters.messaging.topology import PAYMENTS_EXCHANGE, ROUTING_KEY
from outbox_payments.application.errors import WebhookTemporarilyUnavailableError
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.entrypoints.consumer import ConsumerResources, create_broker
from tests.support.rabbit import TEST_POLICY, wait_for_messages

pytestmark = pytest.mark.anyio


class AlwaysUnavailable:
    """A ``process_payment`` factory whose use case always fails transiently."""

    entered = 0

    async def __aenter__(self) -> ProcessPayment:
        AlwaysUnavailable.entered += 1
        raise WebhookTemporarilyUnavailableError("receiver answered 503")

    async def __aexit__(self, *_: object) -> None:
        return None


async def test_message_is_dead_lettered_when_its_retry_queue_is_missing(
    broker: RabbitBroker, rabbitmq_url: str
) -> None:
    # The situation ADR 0002 creates on purpose when retry delays change.
    retry_queue = await broker.declare_queue(
        RabbitQueue(retry_queue_name(1), declare=False)
    )
    await retry_queue.delete(if_unused=False, if_empty=False)
    AlwaysUnavailable.entered = 0
    consumer = create_broker(
        rabbitmq_url,
        ConsumerResources(
            process_payment=AlwaysUnavailable,
            policy=TEST_POLICY,
            clock=SystemClock(),
        ),
        prefetch_count=1,
    )
    await consumer.start()
    try:
        body = {
            "event_id": str(uuid7()),
            "payment_id": str(uuid7()),
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        await broker.publish(
            json.dumps(body).encode(),
            exchange=PAYMENTS_EXCHANGE,
            routing_key=ROUTING_KEY,
            persist=True,
        )

        dead = await wait_for_messages(broker, "payments.new.dlq", within=5)
        await asyncio.sleep(0.5)  # a requeue loop would keep redelivering meanwhile
    finally:
        await consumer.stop()

    assert [json.loads(message) for message in dead] == [body]
    assert AlwaysUnavailable.entered == 1

"""RabbitMQ topology: one exchange, the work queue, TTL retry queues and a DLQ.

::

    relay --(payments.new)--> [payments] --> payments.new --> consumer
                                  ^                              | transient failure
                                  |  dead-letter on TTL expiry   v
                                  +------ payments.new.retry.N <-+  (1 s, 4 s, 16 s)
                                                                 | permanent failure
                                                                 v  or retries exhausted
                                                          payments.new.dlq

Each retry level is its own queue with a queue-level ``x-message-ttl``. Per-message
TTLs in a single delay queue would suffer head-of-line blocking: RabbitMQ only expires
messages at the head of a queue, so a 16 s message would hold back a 1 s one behind it.
Within one level every message has the same TTL, so FIFO order equals expiry order.
"""

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from outbox_payments.adapters.messaging.retry import (
    DEAD_LETTER_QUEUE,
    PAYMENTS_QUEUE,
    RetryPolicy,
)

EXCHANGE_NAME = "payments"
ROUTING_KEY = PAYMENTS_QUEUE

PAYMENTS_EXCHANGE = RabbitExchange(
    EXCHANGE_NAME, type=ExchangeType.DIRECT, durable=True
)


def payments_queue() -> RabbitQueue:
    return RabbitQueue(
        PAYMENTS_QUEUE,
        durable=True,
        routing_key=ROUTING_KEY,
        # Safety net: anything rejected without requeue (e.g. a crash inside the
        # failure handler itself) still ends up in the DLQ instead of vanishing.
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": DEAD_LETTER_QUEUE,
        },
    )


def retry_queues(policy: RetryPolicy) -> list[RabbitQueue]:
    return [
        RabbitQueue(
            level.queue,
            durable=True,
            arguments={
                "x-message-ttl": round(level.delay_seconds * 1000),
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": ROUTING_KEY,
            },
        )
        for level in policy.levels
    ]


def dead_letter_queue() -> RabbitQueue:
    return RabbitQueue(DEAD_LETTER_QUEUE, durable=True)


async def declare_topology(broker: RabbitBroker, policy: RetryPolicy) -> None:
    """Idempotent: safe to call from every process at startup.

    Changing a retry delay changes a queue argument, and RabbitMQ refuses to redeclare
    a queue with different arguments: delete the retry queues when changing delays.
    """
    exchange = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    queue = await broker.declare_queue(payments_queue())
    await queue.bind(exchange, routing_key=ROUTING_KEY)
    for retry_queue in retry_queues(policy):
        await broker.declare_queue(retry_queue)
    await broker.declare_queue(dead_letter_queue())

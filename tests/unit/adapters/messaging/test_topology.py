from outbox_payments.adapters.messaging.retry import RetryPolicy
from outbox_payments.adapters.messaging.topology import (
    dead_letter_queue,
    payments_queue,
    retry_queues,
)


def test_retry_queues_dead_letter_back_to_the_main_exchange_after_their_ttl() -> None:
    queues = retry_queues(RetryPolicy(max_retries=3, base_delay_seconds=1, backoff_factor=4))

    assert [q.name for q in queues] == [f"payments.new.retry.{n}" for n in (1, 2, 3)]
    for queue, ttl in zip(queues, (1000, 4000, 16000), strict=True):
        assert queue.durable
        assert queue.arguments is not None
        assert (
            queue.arguments.items()
            >= {
                "x-message-ttl": ttl,
                "x-dead-letter-exchange": "payments",
                "x-dead-letter-routing-key": "payments.new",
            }.items()
        )


def test_main_queue_dead_letters_rejections_into_the_dlq() -> None:
    queue = payments_queue()

    assert queue.durable
    assert queue.arguments is not None
    assert (
        queue.arguments.items()
        >= {
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "payments.new.dlq",
        }.items()
    )
    assert dead_letter_queue().name == "payments.new.dlq"

"""What the consumer does with a message, per failure kind and attempt number.

With ``MAX_RETRIES=3`` a message is delivered at most 4 times: the original delivery
plus three retries (1 s, 4 s, 16 s). The failure after the third retry dead-letters.
"""

from typing import Literal, NotRequired, TypedDict

type Failure = Literal[
    "none",
    "webhook-5xx",
    "webhook-4xx",
    "database-down",
    "malformed-body",
    "unknown-payment",
]


class ConsumerOutcomeCase(TypedDict):
    id: str
    failure: Failure
    incoming_retry_count: NotRequired[int]
    expected_queue: str | None
    expected_retry_count: NotRequired[int]


CONSUMER_OUTCOME_CASES: list[ConsumerOutcomeCase] = [
    {
        "id": "processed-message-is-acked-and-not-republished",
        "failure": "none",
        "expected_queue": None,
    },
    {
        "id": "gateway-decline-is-a-business-outcome-and-not-retried",
        "failure": "none",
        "incoming_retry_count": 1,
        "expected_queue": None,
    },
    {
        "id": "first-webhook-5xx-goes-to-the-one-second-queue",
        "failure": "webhook-5xx",
        "expected_queue": "payments.new.retry.1",
        "expected_retry_count": 1,
    },
    {
        "id": "second-webhook-5xx-goes-to-the-four-second-queue",
        "failure": "webhook-5xx",
        "incoming_retry_count": 1,
        "expected_queue": "payments.new.retry.2",
        "expected_retry_count": 2,
    },
    {
        "id": "third-webhook-5xx-goes-to-the-sixteen-second-queue",
        "failure": "webhook-5xx",
        "incoming_retry_count": 2,
        "expected_queue": "payments.new.retry.3",
        "expected_retry_count": 3,
    },
    {
        "id": "webhook-5xx-after-three-retries-goes-to-the-dlq",
        "failure": "webhook-5xx",
        "incoming_retry_count": 3,
        "expected_queue": "payments.new.dlq",
        "expected_retry_count": 3,
    },
    {
        "id": "database-outage-is-retried",
        "failure": "database-down",
        "expected_queue": "payments.new.retry.1",
        "expected_retry_count": 1,
    },
    {
        "id": "webhook-4xx-goes-straight-to-the-dlq",
        "failure": "webhook-4xx",
        "expected_queue": "payments.new.dlq",
        "expected_retry_count": 0,
    },
    {
        "id": "malformed-message-goes-straight-to-the-dlq",
        "failure": "malformed-body",
        "expected_queue": "payments.new.dlq",
        "expected_retry_count": 0,
    },
    {
        "id": "message-for-unknown-payment-goes-straight-to-the-dlq",
        "failure": "unknown-payment",
        "expected_queue": "payments.new.dlq",
        "expected_retry_count": 0,
    },
]

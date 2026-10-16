"""Backoff schedule and the retry -> DLQ cutoff.

``max_retries`` counts retries *after* the first delivery: with the default of 3 a
message is handled at most 4 times (1 + 3 retries) before it is dead-lettered.
"""

from typing import NotRequired, TypedDict


class RetryDecisionCase(TypedDict):
    id: str
    max_retries: int
    retries_so_far: int
    expected_queue: str
    expected_delay_seconds: NotRequired[float]


RETRY_DECISION_CASES: list[RetryDecisionCase] = [
    {
        "id": "first-failure-waits-one-second",
        "max_retries": 3,
        "retries_so_far": 0,
        "expected_queue": "payments.new.retry.1",
        "expected_delay_seconds": 1.0,
    },
    {
        "id": "second-failure-waits-four-seconds",
        "max_retries": 3,
        "retries_so_far": 1,
        "expected_queue": "payments.new.retry.2",
        "expected_delay_seconds": 4.0,
    },
    {
        "id": "third-failure-waits-sixteen-seconds",
        "max_retries": 3,
        "retries_so_far": 2,
        "expected_queue": "payments.new.retry.3",
        "expected_delay_seconds": 16.0,
    },
    {
        "id": "failure-after-third-retry-is-dead-lettered",
        "max_retries": 3,
        "retries_so_far": 3,
        "expected_queue": "payments.new.dlq",
    },
    {
        "id": "corrupted-oversized-counter-is-dead-lettered",
        "max_retries": 3,
        "retries_so_far": 99,
        "expected_queue": "payments.new.dlq",
    },
    {
        "id": "zero-max-retries-dead-letters-the-first-failure",
        "max_retries": 0,
        "retries_so_far": 0,
        "expected_queue": "payments.new.dlq",
    },
    {
        "id": "fifth-retry-of-five-waits-256-seconds",
        "max_retries": 5,
        "retries_so_far": 4,
        "expected_queue": "payments.new.retry.5",
        "expected_delay_seconds": 256.0,
    },
]

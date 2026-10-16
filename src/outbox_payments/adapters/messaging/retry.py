"""Retry schedule for the payments consumer.

``max_retries`` is the number of retries *after* the first delivery, so the default
of 3 means at most 4 deliveries. Retry ``n`` waits ``base * factor ** (n - 1)``
seconds (1 s, 4 s, 16 s by default) in its own TTL queue.
"""

from dataclasses import dataclass

PAYMENTS_QUEUE = "payments.new"
DEAD_LETTER_QUEUE = f"{PAYMENTS_QUEUE}.dlq"
RETRY_COUNT_HEADER = "x-retry-count"
LAST_ERROR_HEADER = "x-last-error"
FAILED_AT_HEADER = "x-failed-at"


def retry_queue_name(retry_number: int) -> str:
    return f"{PAYMENTS_QUEUE}.retry.{retry_number}"


@dataclass(frozen=True, slots=True)
class Retry:
    queue: str
    retry_number: int
    delay_seconds: float


@dataclass(frozen=True, slots=True)
class DeadLetter:
    queue: str = DEAD_LETTER_QUEUE


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_factor: float = 4.0

    def delay_for(self, retry_number: int) -> float:
        return float(self.base_delay_seconds * self.backoff_factor ** (retry_number - 1))

    @property
    def levels(self) -> list[Retry]:
        """One TTL queue per delay level, declared up front."""
        return [
            Retry(queue=retry_queue_name(n), retry_number=n, delay_seconds=self.delay_for(n))
            for n in range(1, self.max_retries + 1)
        ]

    def after_failure(self, *, retries_so_far: int) -> Retry | DeadLetter:
        if retries_so_far >= self.max_retries:
            return DeadLetter()
        retry_number = max(retries_so_far, 0) + 1
        return Retry(
            queue=retry_queue_name(retry_number),
            retry_number=retry_number,
            delay_seconds=self.delay_for(retry_number),
        )

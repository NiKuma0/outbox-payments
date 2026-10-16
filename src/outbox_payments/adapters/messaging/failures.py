"""Routing failed messages to a retry queue or the dead letter queue.

The failed message is republished (with publisher confirms) *before* the original is
acked. A crash in between duplicates the message rather than losing it, which the
idempotent consumer absorbs.
"""

import logging
from datetime import datetime

from faststream.rabbit import RabbitBroker, RabbitMessage

from outbox_payments.adapters.messaging.retry import (
    FAILED_AT_HEADER,
    LAST_ERROR_HEADER,
    RETRY_COUNT_HEADER,
    DeadLetter,
    Retry,
    RetryPolicy,
)

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 1000


def retries_so_far(message: RabbitMessage, policy: RetryPolicy) -> int:
    """Read ``x-retry-count``; a garbled counter is treated as exhausted, not as 0,
    so a corrupted header can never cause an infinite retry loop."""
    raw = message.headers.get(RETRY_COUNT_HEADER, 0)
    try:
        return max(int(str(raw)), 0)
    except ValueError:
        return policy.max_retries


class FailureRouter:
    def __init__(
        self,
        broker: RabbitBroker,
        policy: RetryPolicy,
        *,
        confirm_timeout_seconds: float = 5.0,
    ) -> None:
        self._broker = broker
        self._policy = policy
        self._timeout = confirm_timeout_seconds

    async def route(
        self,
        message: RabbitMessage,
        error: BaseException,
        *,
        permanent: bool,
        now: datetime,
    ) -> Retry | DeadLetter:
        retries = retries_so_far(message, self._policy)
        decision = (
            DeadLetter()
            if permanent
            else self._policy.after_failure(retries_so_far=retries)
        )
        headers: dict[str, object] = dict(message.headers)
        context = {"event_id": message.message_id, "error": _describe(error)}
        match decision:
            case Retry(retry_number=retry_number, delay_seconds=delay):
                headers[RETRY_COUNT_HEADER] = retry_number
                logger.warning(
                    "processing failed, retrying",
                    extra={**context, "retry": retry_number, "delay_seconds": delay},
                )
            case DeadLetter():
                headers[RETRY_COUNT_HEADER] = retries
                headers[LAST_ERROR_HEADER] = _describe(error)
                headers[FAILED_AT_HEADER] = now.isoformat()
                logger.error(
                    "processing failed, dead-lettered",
                    extra={**context, "retries": retries, "permanent": permanent},
                )
        # Default exchange, routing key = queue name: retry/DLQ queues need no bindings.
        await self._broker.publish(
            message.body,
            queue=decision.queue,
            headers=headers,  # pyright: ignore[reportArgumentType]
            message_id=message.message_id,
            content_type=message.content_type,
            persist=True,
            mandatory=True,
            timeout=self._timeout,
        )
        return decision


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:MAX_ERROR_LENGTH]

"""Application errors.

The split between *transient* and *permanent* failures is what the consumer's retry
policy is built on: transient errors are retried with backoff, permanent ones go
straight to the dead letter queue.
"""

from uuid import UUID


class ApplicationError(Exception):
    """Base class for use-case level failures."""


class PaymentNotFoundError(ApplicationError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"payment {payment_id} not found")
        self.payment_id = payment_id


class IdempotencyKeyConflictError(ApplicationError):
    """The key was already used for a request with a different body."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key {idempotency_key!r} was used with a different request"
        )
        self.idempotency_key = idempotency_key


class TransientError(ApplicationError):
    """Retrying later may succeed."""


class PermanentError(ApplicationError):
    """Retrying will never succeed; dead-letter immediately."""


class WebhookTemporarilyUnavailableError(TransientError):
    """5xx, 408, 429, timeouts and connection errors."""


class WebhookRejectedError(PermanentError):
    """The receiver refused the webhook for good (4xx other than 408/429, redirects)."""


class PublishError(TransientError):
    """The broker did not confirm the message."""

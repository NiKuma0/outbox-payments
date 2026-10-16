"""Webhook notifications and the rules for classifying a receiver's answer."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from outbox_payments.domain import JsonObject, Payment

_RETRYABLE_CLIENT_ERRORS = frozenset({408, 429})


@dataclass(frozen=True, slots=True, kw_only=True)
class WebhookNotification:
    """``webhook_id`` is sent as ``X-Webhook-Id`` and is stable across redeliveries,
    so the receiver can deduplicate."""

    webhook_id: UUID
    url: str
    payload: JsonObject


class WebhookVerdict(StrEnum):
    DELIVERED = "delivered"
    RETRY = "retry"
    REJECTED = "rejected"


def classify_webhook_status(status_code: int) -> WebhookVerdict:
    if 200 <= status_code < 300:
        return WebhookVerdict.DELIVERED
    if status_code >= 500 or status_code in _RETRYABLE_CLIENT_ERRORS:
        return WebhookVerdict.RETRY
    # 1xx/3xx (redirects are not followed, see SSRF notes) and the remaining 4xx.
    return WebhookVerdict.REJECTED


def notification_for(payment: Payment, *, webhook_id: UUID) -> WebhookNotification:
    return WebhookNotification(
        webhook_id=webhook_id,
        url=payment.webhook_url,
        payload={
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.money.amount),
            "currency": payment.money.currency.value,
            "metadata": payment.metadata,
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        },
    )

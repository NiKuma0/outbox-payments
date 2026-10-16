"""WebhookSender over httpx.

One attempt per call: retrying is the consumer's job (TTL queues), so a slow
receiver never pins a consumer slot through an in-process backoff loop. Redirects
are not followed: a webhook URL that redirects elsewhere is a classic SSRF vector.
"""

import httpx

from outbox_payments.application.errors import (
    WebhookRejectedError,
    WebhookTemporarilyUnavailableError,
)
from outbox_payments.application.webhooks import (
    WebhookNotification,
    WebhookVerdict,
    classify_webhook_status,
)

WEBHOOK_ID_HEADER = "X-Webhook-Id"


def create_webhook_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
        headers={"User-Agent": "outbox-payments-webhooks/0.1"},
    )


class HttpxWebhookSender:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, notification: WebhookNotification) -> None:
        try:
            response = await self._client.post(
                notification.url,
                json=notification.payload,
                headers={WEBHOOK_ID_HEADER: str(notification.webhook_id)},
                follow_redirects=False,
            )
        except httpx.TransportError as exc:  # timeouts, refused, reset, DNS
            raise WebhookTemporarilyUnavailableError(f"{type(exc).__name__}: {exc}") from exc

        match classify_webhook_status(response.status_code):
            case WebhookVerdict.DELIVERED:
                return
            case WebhookVerdict.RETRY:
                raise WebhookTemporarilyUnavailableError(
                    f"receiver answered {response.status_code}"
                )
            case WebhookVerdict.REJECTED:
                raise WebhookRejectedError(f"receiver answered {response.status_code}")

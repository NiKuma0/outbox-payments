import json
from collections.abc import Callable
from uuid import uuid7

import httpx
import pytest

from outbox_payments.adapters.webhooks.httpx_sender import HttpxWebhookSender
from outbox_payments.application.errors import (
    WebhookRejectedError,
    WebhookTemporarilyUnavailableError,
)
from outbox_payments.application.webhooks import WebhookNotification
from tests.cases._helpers import as_params
from tests.cases.adapters.webhooks.httpx_sender import (
    WEBHOOK_RESPONSE_CASES,
    WebhookResponseCase,
)

pytestmark = pytest.mark.anyio

NOTIFICATION = WebhookNotification(
    webhook_id=uuid7(), url="http://client.test/hook", payload={"status": "succeeded"}
)

EXCEPTIONS: dict[str, Callable[[httpx.Request], Exception]] = {
    "timeout": lambda request: httpx.ReadTimeout("timed out", request=request),
    "connect-error": lambda request: httpx.ConnectError("refused", request=request),
    "read-error": lambda request: httpx.ReadError("reset by peer", request=request),
}


def sender_answering(case: WebhookResponseCase, seen: list[httpx.Request]) -> HttpxWebhookSender:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "raises" in case:
            raise EXCEPTIONS[case["raises"]](request)
        status_code = case.get("status_code")
        assert status_code is not None, "a case either raises or answers"
        return httpx.Response(status_code, headers={"Location": "http://elsewhere"})

    return HttpxWebhookSender(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("case", as_params(WEBHOOK_RESPONSE_CASES))
async def test_webhook_response_classification(case: WebhookResponseCase) -> None:
    seen: list[httpx.Request] = []
    sender = sender_answering(case, seen)
    expected_error = {
        "delivered": None,
        "retry": WebhookTemporarilyUnavailableError,
        "dlq": WebhookRejectedError,
    }[case["expected"]]

    if expected_error is None:
        await sender.send(NOTIFICATION)
    else:
        with pytest.raises(expected_error):
            await sender.send(NOTIFICATION)

    assert len(seen) == 1  # never follows redirects, never retries by itself


async def test_request_carries_webhook_id_and_json_payload() -> None:
    seen: list[httpx.Request] = []
    sender = sender_answering({"id": "ok", "status_code": 200, "expected": "delivered"}, seen)

    await sender.send(NOTIFICATION)

    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == NOTIFICATION.url
    assert request.headers["X-Webhook-Id"] == str(NOTIFICATION.webhook_id)
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content) == NOTIFICATION.payload

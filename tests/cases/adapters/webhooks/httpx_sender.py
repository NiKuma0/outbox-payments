"""The receiver's answer -> what the consumer does with the message."""

from typing import Literal, NotRequired, TypedDict

type Verdict = Literal["delivered", "retry", "dlq"]


class WebhookResponseCase(TypedDict):
    id: str
    status_code: NotRequired[int]
    raises: NotRequired[Literal["timeout", "connect-error", "read-error"]]
    expected: Verdict


WEBHOOK_RESPONSE_CASES: list[WebhookResponseCase] = [
    {
        "id": "receiver-answers-200-and-message-is-acked",
        "status_code": 200,
        "expected": "delivered",
    },
    {
        "id": "receiver-answers-204-and-message-is-acked",
        "status_code": 204,
        "expected": "delivered",
    },
    {
        "id": "receiver-answers-500-and-message-is-retried",
        "status_code": 500,
        "expected": "retry",
    },
    {
        "id": "receiver-answers-503-and-message-is-retried",
        "status_code": 503,
        "expected": "retry",
    },
    {
        "id": "receiver-answers-408-and-message-is-retried",
        "status_code": 408,
        "expected": "retry",
    },
    {
        "id": "receiver-answers-429-and-message-is-retried",
        "status_code": 429,
        "expected": "retry",
    },
    {
        "id": "receiver-answers-400-and-message-goes-to-dlq",
        "status_code": 400,
        "expected": "dlq",
    },
    {
        "id": "receiver-answers-404-and-message-goes-to-dlq",
        "status_code": 404,
        "expected": "dlq",
    },
    {
        "id": "receiver-answers-410-and-message-goes-to-dlq",
        "status_code": 410,
        "expected": "dlq",
    },
    {
        "id": "receiver-redirect-is-not-followed-and-goes-to-dlq",
        "status_code": 307,
        "expected": "dlq",
    },
    {"id": "receiver-timeout-is-retried", "raises": "timeout", "expected": "retry"},
    {
        "id": "unreachable-receiver-is-retried",
        "raises": "connect-error",
        "expected": "retry",
    },
    {
        "id": "connection-dropped-mid-response-is-retried",
        "raises": "read-error",
        "expected": "retry",
    },
]

"""How the receiver's HTTP status decides between ack, retry and dead-lettering."""

from typing import Literal, TypedDict


class WebhookStatusCase(TypedDict):
    id: str
    status_code: int
    expected: Literal["delivered", "retry", "rejected"]


WEBHOOK_STATUS_CASES: list[WebhookStatusCase] = [
    {"id": "ok-means-delivered", "status_code": 200, "expected": "delivered"},
    {"id": "accepted-means-delivered", "status_code": 202, "expected": "delivered"},
    {"id": "no-content-means-delivered", "status_code": 204, "expected": "delivered"},
    {
        "id": "redirect-is-not-followed-and-rejected",
        "status_code": 302,
        "expected": "rejected",
    },
    {"id": "bad-request-is-rejected", "status_code": 400, "expected": "rejected"},
    {"id": "unauthorized-is-rejected", "status_code": 401, "expected": "rejected"},
    {"id": "not-found-is-rejected", "status_code": 404, "expected": "rejected"},
    {"id": "gone-is-rejected", "status_code": 410, "expected": "rejected"},
    {"id": "request-timeout-is-retried", "status_code": 408, "expected": "retry"},
    {"id": "too-many-requests-is-retried", "status_code": 429, "expected": "retry"},
    {"id": "server-error-is-retried", "status_code": 500, "expected": "retry"},
    {"id": "bad-gateway-is-retried", "status_code": 502, "expected": "retry"},
    {
        "id": "service-unavailable-is-retried",
        "status_code": 503,
        "expected": "retry",
    },
]

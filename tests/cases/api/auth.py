from typing import TypedDict


class AuthCase(TypedDict):
    id: str
    method: str
    path: str
    headers: dict[str, str]
    expected_status: int


API_KEY = "test-api-key"
PAYMENT_PATH = "/api/v1/payments/0199f1a2-7c3e-7d4b-9a10-2b3c4d5e6f70"

AUTH_CASES: list[AuthCase] = [
    {
        "id": "create-without-api-key-is-unauthorized",
        "method": "POST",
        "path": "/api/v1/payments",
        "headers": {"Idempotency-Key": "k"},
        "expected_status": 401,
    },
    {
        "id": "create-with-wrong-api-key-is-unauthorized",
        "method": "POST",
        "path": "/api/v1/payments",
        "headers": {"Idempotency-Key": "k", "X-API-Key": "wrong"},
        "expected_status": 401,
    },
    {
        "id": "read-without-api-key-is-unauthorized",
        "method": "GET",
        "path": PAYMENT_PATH,
        "headers": {},
        "expected_status": 401,
    },
    {
        "id": "read-with-api-key-is-authorized",
        "method": "GET",
        "path": PAYMENT_PATH,
        "headers": {"X-API-Key": API_KEY},
        "expected_status": 404,
    },
    {
        "id": "liveness-probe-needs-no-api-key",
        "method": "GET",
        "path": "/health",
        "headers": {},
        "expected_status": 200,
    },
    {
        "id": "readiness-probe-needs-no-api-key",
        "method": "GET",
        "path": "/ready",
        "headers": {},
        "expected_status": 200,
    },
]

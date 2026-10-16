from typing import NotRequired, TypedDict


class CreatePaymentValidationCase(TypedDict):
    id: str
    overrides: dict[str, object]
    expected_status: int
    expected_error_field: NotRequired[str]
    removed_fields: NotRequired[list[str]]


class IdempotencyKeyHeaderCase(TypedDict):
    id: str
    headers: dict[str, str]
    expected_status: int


class HttpIdempotencyCase(TypedDict):
    id: str
    second_key: str
    second_overrides: dict[str, object]
    expected_status: int
    expected_same_payment: bool


VALID_BODY: dict[str, object] = {
    "amount": "100.00",
    "currency": "RUB",
    "description": "Order #42",
    "metadata": {"order_id": 42},
    "webhook_url": "http://webhook-sink:8080/hook",
}

FIRST_KEY = "order-42-attempt-1"

CREATE_PAYMENT_VALIDATION_CASES: list[CreatePaymentValidationCase] = [
    {"id": "valid-payment-is-accepted", "overrides": {}, "expected_status": 202},
    {
        "id": "amount-as-json-number-is-accepted",
        "overrides": {"amount": 100.5},
        "expected_status": 202,
    },
    {
        "id": "empty-metadata-is-accepted",
        "overrides": {"metadata": {}},
        "expected_status": 202,
    },
    {
        "id": "https-webhook-is-accepted",
        "overrides": {"webhook_url": "https://client.example/hooks/payments"},
        "expected_status": 202,
    },
    {
        "id": "zero-amount-is-rejected",
        "overrides": {"amount": "0"},
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "negative-amount-is-rejected",
        "overrides": {"amount": "-10.00"},
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "fractions-of-a-cent-are-rejected",
        "overrides": {"amount": "10.001"},
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "amount-beyond-numeric-18-2-is-rejected",
        "overrides": {"amount": "12345678901234567.00"},
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "non-numeric-amount-is-rejected",
        "overrides": {"amount": "ten"},
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "unsupported-currency-is-rejected",
        "overrides": {"currency": "GBP"},
        "expected_status": 422,
        "expected_error_field": "currency",
    },
    {
        "id": "lowercase-currency-is-rejected",
        "overrides": {"currency": "rub"},
        "expected_status": 422,
        "expected_error_field": "currency",
    },
    {
        "id": "empty-description-is-rejected",
        "overrides": {"description": ""},
        "expected_status": 422,
        "expected_error_field": "description",
    },
    {
        "id": "overlong-description-is-rejected",
        "overrides": {"description": "x" * 501},
        "expected_status": 422,
        "expected_error_field": "description",
    },
    {
        "id": "metadata-must-be-an-object",
        "overrides": {"metadata": ["not", "an", "object"]},
        "expected_status": 422,
        "expected_error_field": "metadata",
    },
    {
        "id": "oversized-metadata-is-rejected",
        "overrides": {"metadata": {"blob": "x" * 17_000}},
        "expected_status": 422,
        "expected_error_field": "metadata",
    },
    {
        "id": "webhook-must-be-a-url",
        "overrides": {"webhook_url": "not a url"},
        "expected_status": 422,
        "expected_error_field": "webhook_url",
    },
    {
        "id": "webhook-must-be-http-or-https",
        "overrides": {"webhook_url": "ftp://client.example/hook"},
        "expected_status": 422,
        "expected_error_field": "webhook_url",
    },
    {
        "id": "missing-amount-is-rejected",
        "overrides": {},
        "removed_fields": ["amount"],
        "expected_status": 422,
        "expected_error_field": "amount",
    },
    {
        "id": "unknown-fields-are-rejected",
        "overrides": {"status": "succeeded"},
        "expected_status": 422,
        "expected_error_field": "status",
    },
]

IDEMPOTENCY_KEY_HEADER_CASES: list[IdempotencyKeyHeaderCase] = [
    {"id": "missing-idempotency-key-is-a-bad-request", "headers": {}, "expected_status": 400},
    {
        "id": "empty-idempotency-key-is-a-bad-request",
        "headers": {"Idempotency-Key": ""},
        "expected_status": 400,
    },
    {
        "id": "overlong-idempotency-key-is-a-bad-request",
        "headers": {"Idempotency-Key": "k" * 256},
        "expected_status": 400,
    },
    {
        "id": "idempotency-key-with-spaces-is-a-bad-request",
        "headers": {"Idempotency-Key": "two words"},
        "expected_status": 400,
    },
    {
        "id": "uuid-idempotency-key-is-accepted",
        "headers": {"Idempotency-Key": "0199f1a2-7c3e-7d4b-9a10-2b3c4d5e6f70"},
        "expected_status": 202,
    },
    {
        "id": "longest-allowed-idempotency-key-is-accepted",
        "headers": {"Idempotency-Key": "k" * 255},
        "expected_status": 202,
    },
]

HTTP_IDEMPOTENCY_CASES: list[HttpIdempotencyCase] = [
    {
        "id": "repeat-with-same-key-and-body-returns-the-same-payment",
        "second_key": FIRST_KEY,
        "second_overrides": {},
        "expected_status": 202,
        "expected_same_payment": True,
    },
    {
        "id": "repeat-with-same-key-and-different-body-is-a-conflict",
        "second_key": FIRST_KEY,
        "second_overrides": {"amount": "999.00"},
        "expected_status": 409,
        "expected_same_payment": False,
    },
    {
        "id": "same-body-with-new-key-creates-another-payment",
        "second_key": "order-42-attempt-2",
        "second_overrides": {},
        "expected_status": 202,
        "expected_same_payment": False,
    },
]

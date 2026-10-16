from decimal import Decimal
from typing import Literal, TypedDict

from outbox_payments.domain import Currency, JsonObject


class CreatePaymentRequest(TypedDict):
    idempotency_key: str
    amount: Decimal
    currency: Currency
    description: str
    metadata: JsonObject
    webhook_url: str


class CreatePaymentOverrides(TypedDict, total=False):
    idempotency_key: str
    amount: Decimal
    currency: Currency
    description: str
    metadata: JsonObject
    webhook_url: str


class IdempotencyCase(TypedDict):
    id: str
    second_request: CreatePaymentOverrides
    expected: Literal["same-payment", "new-payment", "conflict"]
    expected_payments: int
    expected_outbox_records: int


BASE_REQUEST: CreatePaymentRequest = {
    "idempotency_key": "order-42-attempt-1",
    "amount": Decimal("100.00"),
    "currency": Currency.RUB,
    "description": "Order #42",
    "metadata": {"order_id": 42},
    "webhook_url": "http://webhook-sink:8080/hook",
}

IDEMPOTENCY_CASES: list[IdempotencyCase] = [
    {
        "id": "same-key-and-same-body-returns-the-original-payment",
        "second_request": {},
        "expected": "same-payment",
        "expected_payments": 1,
        "expected_outbox_records": 1,
    },
    {
        "id": "same-key-and-equivalent-amount-spelling-is-still-a-retry",
        "second_request": {"amount": Decimal(100)},
        "expected": "same-payment",
        "expected_payments": 1,
        "expected_outbox_records": 1,
    },
    {
        "id": "same-key-and-different-amount-is-a-conflict",
        "second_request": {"amount": Decimal("200.00")},
        "expected": "conflict",
        "expected_payments": 1,
        "expected_outbox_records": 1,
    },
    {
        "id": "same-key-and-different-metadata-is-a-conflict",
        "second_request": {"metadata": {"order_id": 43}},
        "expected": "conflict",
        "expected_payments": 1,
        "expected_outbox_records": 1,
    },
    {
        "id": "new-key-and-same-body-is-a-new-payment",
        "second_request": {"idempotency_key": "order-42-attempt-2"},
        "expected": "new-payment",
        "expected_payments": 2,
        "expected_outbox_records": 2,
    },
]

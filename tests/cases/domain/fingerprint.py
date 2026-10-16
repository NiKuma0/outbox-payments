"""Request fingerprints decide whether a reused Idempotency-Key is a retry or a conflict."""

from decimal import Decimal
from typing import TypedDict

from outbox_payments.domain import Currency, JsonObject


class FingerprintRequest(TypedDict):
    amount: Decimal
    currency: Currency
    description: str
    metadata: JsonObject
    webhook_url: str


class FingerprintOverrides(TypedDict, total=False):
    amount: Decimal
    currency: Currency
    description: str
    metadata: JsonObject
    webhook_url: str


class FingerprintCase(TypedDict):
    id: str
    overrides: FingerprintOverrides
    same_fingerprint: bool


BASE_REQUEST: FingerprintRequest = {
    "amount": Decimal("100.00"),
    "currency": Currency.RUB,
    "description": "Order #42",
    "metadata": {"order_id": 42, "tags": ["a", "b"]},
    "webhook_url": "http://example.test/hook",
}

FINGERPRINT_CASES: list[FingerprintCase] = [
    {
        "id": "identical-request-has-identical-fingerprint",
        "overrides": {},
        "same_fingerprint": True,
    },
    {
        "id": "amount-spelling-does-not-matter",
        "overrides": {"amount": Decimal(100)},
        "same_fingerprint": True,
    },
    {
        "id": "metadata-key-order-does-not-matter",
        "overrides": {"metadata": {"tags": ["a", "b"], "order_id": 42}},
        "same_fingerprint": True,
    },
    {
        "id": "different-amount-is-a-different-request",
        "overrides": {"amount": Decimal("100.01")},
        "same_fingerprint": False,
    },
    {
        "id": "different-currency-is-a-different-request",
        "overrides": {"currency": Currency.USD},
        "same_fingerprint": False,
    },
    {
        "id": "different-description-is-a-different-request",
        "overrides": {"description": "Order #43"},
        "same_fingerprint": False,
    },
    {
        "id": "metadata-list-order-matters",
        "overrides": {"metadata": {"order_id": 42, "tags": ["b", "a"]}},
        "same_fingerprint": False,
    },
    {
        "id": "different-webhook-url-is-a-different-request",
        "overrides": {"webhook_url": "http://example.test/other"},
        "same_fingerprint": False,
    },
]

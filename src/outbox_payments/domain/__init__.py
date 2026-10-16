"""The domain layer: business rules in pure Python, no framework imports."""

from outbox_payments.domain.errors import (
    DomainError,
    InvalidMoneyError,
    InvalidStatusTransitionError,
)
from outbox_payments.domain.events import PaymentCreated
from outbox_payments.domain.fingerprint import request_fingerprint
from outbox_payments.domain.money import Currency, Money
from outbox_payments.domain.payment import Payment
from outbox_payments.domain.status import ChargeOutcome, PaymentStatus
from outbox_payments.domain.types import JsonObject, JsonValue

__all__ = [
    "ChargeOutcome",
    "Currency",
    "DomainError",
    "InvalidMoneyError",
    "InvalidStatusTransitionError",
    "JsonObject",
    "JsonValue",
    "Money",
    "Payment",
    "PaymentCreated",
    "PaymentStatus",
    "request_fingerprint",
]

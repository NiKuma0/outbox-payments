from decimal import Decimal
from typing import TypedDict

from outbox_payments.domain import Currency


class ValidMoneyCase(TypedDict):
    id: str
    amount: Decimal
    currency: Currency
    expected_amount: Decimal


class InvalidMoneyCase(TypedDict):
    id: str
    amount: Decimal


VALID_MONEY_CASES: list[ValidMoneyCase] = [
    {
        "id": "two-decimal-places-are-kept-as-is",
        "amount": Decimal("100.50"),
        "currency": Currency.RUB,
        "expected_amount": Decimal("100.50"),
    },
    {
        "id": "integer-amount-is-normalized-to-cents",
        "amount": Decimal(100),
        "currency": Currency.USD,
        "expected_amount": Decimal("100.00"),
    },
    {
        "id": "trailing-zeros-beyond-cents-are-harmless",
        "amount": Decimal("7.1000"),
        "currency": Currency.EUR,
        "expected_amount": Decimal("7.10"),
    },
    {
        "id": "smallest-positive-amount-is-one-cent",
        "amount": Decimal("0.01"),
        "currency": Currency.EUR,
        "expected_amount": Decimal("0.01"),
    },
    {
        "id": "largest-amount-fits-numeric-18-2",
        "amount": Decimal("9999999999999999.99"),
        "currency": Currency.RUB,
        "expected_amount": Decimal("9999999999999999.99"),
    },
]

INVALID_MONEY_CASES: list[InvalidMoneyCase] = [
    {"id": "zero-amount-is-not-money", "amount": Decimal(0)},
    {"id": "negative-amount-is-not-money", "amount": Decimal("-1.00")},
    {"id": "fractions-of-a-cent-are-never-rounded", "amount": Decimal("1.001")},
    {
        "id": "amount-overflowing-numeric-18-2-is-rejected",
        "amount": Decimal(10000000000000000),
    },
    {"id": "nan-is-not-money", "amount": Decimal("NaN")},
    {"id": "infinity-is-not-money", "amount": Decimal("Infinity")},
]

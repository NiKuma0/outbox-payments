from decimal import Decimal

import pytest

from outbox_payments.domain import Currency, InvalidMoneyError, Money
from tests.cases._helpers import as_params
from tests.cases.domain.money import (
    INVALID_MONEY_CASES,
    VALID_MONEY_CASES,
    InvalidMoneyCase,
    ValidMoneyCase,
)


@pytest.mark.parametrize("case", as_params(VALID_MONEY_CASES))
def test_valid_money(case: ValidMoneyCase) -> None:
    money = Money(case["amount"], case["currency"])

    assert money.amount == case["expected_amount"]
    assert money.amount.as_tuple().exponent == -2
    assert money.currency is case["currency"]


@pytest.mark.parametrize("case", as_params(INVALID_MONEY_CASES))
def test_invalid_money(case: InvalidMoneyCase) -> None:
    with pytest.raises(InvalidMoneyError):
        Money(case["amount"], Currency.RUB)


def test_money_is_a_value_object() -> None:
    assert Money(Decimal(1), Currency.USD) == Money(Decimal("1.00"), Currency.USD)
    assert Money(Decimal(1), Currency.USD) != Money(Decimal(1), Currency.EUR)

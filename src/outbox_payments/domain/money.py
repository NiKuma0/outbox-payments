"""Money as a value object.

Amounts are ``Decimal`` with exactly two fractional digits, matching ``NUMERIC(18, 2)``
in storage. Inputs with fractions of a cent are rejected, never rounded: silently
changing the amount a client asked to charge is worse than a 422.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from outbox_payments.domain.errors import InvalidMoneyError

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999999999.99")  # NUMERIC(18, 2): 16 integer digits


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise InvalidMoneyError(f"amount must be finite, got {self.amount}")
        try:
            normalized = self.amount.quantize(CENT)
        except InvalidOperation as exc:
            raise InvalidMoneyError(f"amount {self.amount} is out of range") from exc
        if normalized != self.amount:
            raise InvalidMoneyError(f"amount {self.amount} has fractions of a cent")
        if not CENT <= normalized <= MAX_AMOUNT:
            raise InvalidMoneyError(f"amount must be within [{CENT}, {MAX_AMOUNT}]")
        object.__setattr__(self, "amount", normalized)

import random
from decimal import Decimal
from uuid import uuid7

import pytest

from outbox_payments.adapters.payment_provider.emulated import EmulatedPaymentProvider
from outbox_payments.domain import ChargeOutcome, Currency, Money
from tests.cases._helpers import as_params
from tests.cases.adapters.payment_provider.emulated import (
    GATEWAY_DRAW_CASES,
    SUCCESS_RATE,
    GatewayDrawCase,
)

pytestmark = pytest.mark.anyio

MONEY = Money(Decimal("10.00"), Currency.USD)


class ScriptedRandom(random.Random):
    def __init__(self, values: list[float]) -> None:
        super().__init__()
        self.values = values

    def random(self) -> float:
        return self.values.pop(0)


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def provider(values: list[float], sleep: RecordingSleep) -> EmulatedPaymentProvider:
    return EmulatedPaymentProvider(
        rng=ScriptedRandom(values),
        sleep=sleep,
        min_delay=2.0,
        max_delay=5.0,
        success_rate=SUCCESS_RATE,
    )


@pytest.mark.parametrize("case", as_params(GATEWAY_DRAW_CASES))
async def test_outcome_follows_the_success_rate(case: GatewayDrawCase) -> None:
    sleep = RecordingSleep()

    outcome = await provider([0.5, case["draw"]], sleep).charge(uuid7(), MONEY)

    assert outcome is case["expected"]
    assert sleep.calls == [3.5]  # uniform(2, 5) at 0.5, slept through the injected sleep


async def test_repeated_charge_with_same_key_replays_the_outcome_without_work() -> None:
    sleep = RecordingSleep()
    gateway = provider([0.0, 0.95], sleep)
    payment_id = uuid7()

    first = await gateway.charge(payment_id, MONEY)
    second = await gateway.charge(payment_id, MONEY)

    assert first is second is ChargeOutcome.DECLINED
    assert len(sleep.calls) == 1
    assert gateway.charges == 1

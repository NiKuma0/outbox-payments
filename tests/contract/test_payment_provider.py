"""PaymentProvider contract: the fake used in use-case tests behaves like the emulator."""

import asyncio
from decimal import Decimal
from uuid import uuid7

import pytest

from outbox_payments.adapters.payment_provider.emulated import EmulatedPaymentProvider
from outbox_payments.application.ports import PaymentProvider
from outbox_payments.domain import ChargeOutcome, Currency, Money
from tests.fakes.provider import FakePaymentProvider

pytestmark = pytest.mark.anyio

MONEY = Money(Decimal("10.00"), Currency.EUR)


async def no_sleep(_: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture(
    params=[
        pytest.param("fake", marks=pytest.mark.unit),
        pytest.param("emulated", marks=pytest.mark.unit),
    ]
)
def provider(request: pytest.FixtureRequest) -> PaymentProvider:
    if request.param == "fake":
        return FakePaymentProvider()
    return EmulatedPaymentProvider(sleep=no_sleep)


async def test_same_key_always_yields_the_same_outcome(provider: PaymentProvider) -> None:
    payment_id = uuid7()

    outcomes = {await provider.charge(payment_id, MONEY) for _ in range(20)}

    assert len(outcomes) == 1
    assert outcomes <= set(ChargeOutcome)


async def test_different_keys_are_independent_charges(provider: PaymentProvider) -> None:
    outcomes = [await provider.charge(uuid7(), MONEY) for _ in range(5)]

    assert all(isinstance(outcome, ChargeOutcome) for outcome in outcomes)

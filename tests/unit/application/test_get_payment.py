from uuid import uuid7

import pytest

from outbox_payments.application.errors import PaymentNotFoundError
from outbox_payments.application.use_cases.get_payment import GetPayment
from tests.support.builders import make_payment
from tests.support.mocks import mock_payments

pytestmark = pytest.mark.anyio


async def test_returns_a_stored_payment() -> None:
    stored, _ = make_payment()
    payments = mock_payments(stored)

    found = await GetPayment(payments=payments).execute(stored.id)

    assert found == stored
    payments.get.assert_awaited_once_with(stored.id)


async def test_unknown_payment_is_reported() -> None:
    get_payment = GetPayment(payments=mock_payments())

    with pytest.raises(PaymentNotFoundError):
        await get_payment.execute(uuid7())

"""PaymentRepository + Transaction contract of the SQL adapter: what the unit-test mocks assume."""

import pytest

from outbox_payments.domain import ChargeOutcome, PaymentStatus
from tests.contract.conftest import Backend
from tests.support.builders import T0, make_payment

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


async def test_committed_payment_round_trips(backend: Backend) -> None:
    payment, _ = make_payment()
    async with backend.session() as repos:
        assert await repos.payments.add_if_absent(payment) is True
        await repos.transaction.commit()

    async with backend.session() as repos:
        assert await repos.payments.get(payment.id) == payment
        assert await repos.payments.get_by_idempotency_key("key-1") == payment


async def test_uncommitted_payment_is_rolled_back(backend: Backend) -> None:
    payment, _ = make_payment()
    async with backend.session() as repos:
        await repos.payments.add_if_absent(payment)

    async with backend.session() as repos:
        assert await repos.payments.get(payment.id) is None


async def test_uncommitted_payment_is_invisible_to_other_transactions(
    backend: Backend,
) -> None:
    payment, _ = make_payment()
    async with backend.session() as writer, backend.session() as reader:
        await writer.payments.add_if_absent(payment)

        assert await reader.payments.get(payment.id) is None


async def test_taken_idempotency_key_is_not_inserted_again(backend: Backend) -> None:
    first, _ = make_payment(idempotency_key="shared", request_hash="first")
    second, _ = make_payment(idempotency_key="shared", request_hash="second")
    async with backend.session() as repos:
        await repos.payments.add_if_absent(first)
        await repos.transaction.commit()

    async with backend.session() as repos:
        assert await repos.payments.add_if_absent(second) is False
        stored = await repos.payments.get_by_idempotency_key("shared")

    assert stored is not None
    assert stored.id == first.id
    assert stored.request_hash == "first"


async def test_completion_is_applied_only_while_pending(backend: Backend) -> None:
    payment, _ = make_payment()
    async with backend.session() as repos:
        await repos.payments.add_if_absent(payment)
        await repos.transaction.commit()

    payment.complete(ChargeOutcome.APPROVED, now=T0)
    async with backend.session() as repos:
        assert await repos.payments.complete_if_pending(payment) is True
        await repos.transaction.commit()

    payment.status = PaymentStatus.FAILED  # a stale writer with a different opinion
    async with backend.session() as repos:
        assert await repos.payments.complete_if_pending(payment) is False
        await repos.transaction.commit()
        stored = await repos.payments.get(payment.id)

    assert stored is not None
    assert stored.status is PaymentStatus.SUCCEEDED
    assert stored.processed_at == T0


async def test_webhook_delivery_time_is_written_once(backend: Backend) -> None:
    payment, _ = make_payment()
    payment.complete(ChargeOutcome.DECLINED, now=T0)
    async with backend.session() as repos:
        await repos.payments.add_if_absent(payment)
        await repos.transaction.commit()

    for delivered_at in (T0.replace(minute=1), T0.replace(minute=2)):
        payment.mark_webhook_delivered(now=delivered_at)
        async with backend.session() as repos:
            await repos.payments.mark_webhook_delivered(payment)
            await repos.transaction.commit()

    async with backend.session() as repos:
        stored = await repos.payments.get(payment.id)
    assert stored is not None
    assert stored.webhook_delivered_at == T0.replace(minute=1)

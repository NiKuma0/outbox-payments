"""OutboxRepository contract of the SQL adapter: what the unit-test mocks assume."""

from datetime import timedelta

import pytest

from tests.contract.conftest import Backend
from tests.support.builders import T0, make_payment

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


async def seed(backend: Backend, count: int) -> list[str]:
    keys: list[str] = []
    async with backend.session() as repos:
        for n in range(count):
            payment, message = make_payment(
                idempotency_key=f"key-{n}", now=T0 + timedelta(seconds=n)
            )
            await repos.payments.add_if_absent(payment)
            await repos.outbox.add(message)
            keys.append(str(message.id))
        await repos.transaction.commit()
    return keys


async def test_claims_unpublished_records_oldest_first(backend: Backend) -> None:
    ids = await seed(backend, 3)

    async with backend.session() as repos:
        batch = await repos.outbox.claim_batch(2)

    assert [str(m.id) for m in batch] == ids[:2]
    assert batch[0].event_type == "payment.created"
    assert batch[0].payload["event_id"] == ids[0]
    assert batch[0].attempts == 0


async def test_published_records_are_not_claimed_again(backend: Backend) -> None:
    await seed(backend, 3)
    async with backend.session() as repos:
        batch = await repos.outbox.claim_batch(2)
        await repos.outbox.mark_published([m.id for m in batch], at=T0)
        await repos.transaction.commit()

    async with backend.session() as repos:
        remaining = await repos.outbox.claim_batch(10)

    assert len(remaining) == 1
    assert remaining[0].id not in {m.id for m in batch}


async def test_concurrent_claims_skip_locked_records(backend: Backend) -> None:
    await seed(backend, 4)

    async with backend.session() as relay_a, backend.session() as relay_b:
        batch_a = await relay_a.outbox.claim_batch(2)
        batch_b = await relay_b.outbox.claim_batch(10)

    assert len(batch_a) == 2
    assert len(batch_b) == 2
    assert {m.id for m in batch_a}.isdisjoint({m.id for m in batch_b})


async def test_locks_are_released_by_commit(backend: Backend) -> None:
    await seed(backend, 1)
    async with backend.session() as relay_a:
        assert len(await relay_a.outbox.claim_batch(1)) == 1
        await relay_a.transaction.commit()

        async with backend.session() as relay_b:
            assert len(await relay_b.outbox.claim_batch(1)) == 1


async def test_failures_are_counted_and_kept(backend: Backend) -> None:
    await seed(backend, 1)
    for error in ("connection refused", "channel closed"):
        async with backend.session() as repos:
            [message] = await repos.outbox.claim_batch(1)
            await repos.outbox.record_failure(message.id, error)
            await repos.transaction.commit()

    async with backend.session() as repos:
        [message] = await repos.outbox.claim_batch(1)

    assert message.attempts == 2
    assert message.last_error == "channel closed"
    assert message.published_at is None


async def test_purge_deletes_only_old_published_records(backend: Backend) -> None:
    await seed(backend, 3)
    async with backend.session() as repos:
        old, recent, _unpublished = await repos.outbox.claim_batch(3)
        await repos.outbox.mark_published([old.id], at=T0)
        await repos.outbox.mark_published([recent.id], at=T0 + timedelta(days=2))
        await repos.transaction.commit()

    async with backend.session() as repos:
        deleted = await repos.outbox.delete_published_before(T0 + timedelta(days=1))
        await repos.transaction.commit()

    async with backend.session() as repos:
        left = await repos.outbox.claim_batch(10)
    assert deleted == 1
    assert len(left) == 1  # the unpublished one; `recent` is published but kept

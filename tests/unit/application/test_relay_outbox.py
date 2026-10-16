from dataclasses import replace
from datetime import timedelta

import pytest

from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.relay_outbox import RelayOutbox
from tests.cases.application.create_payment import BASE_REQUEST
from tests.fakes.clock import FrozenClock
from tests.fakes.publisher import FakeEventPublisher
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
)

pytestmark = pytest.mark.anyio


async def accept_payments(
    store: InMemoryStore, clock: FrozenClock, count: int, *, batch: str = "a"
) -> None:
    for n in range(count):
        tx = store.begin()
        await CreatePayment(
            payments=InMemoryPaymentRepository(tx),
            outbox=InMemoryOutboxRepository(tx),
            transaction=tx,
            clock=clock,
        ).execute(
            replace(
                CreatePaymentCommand(**BASE_REQUEST), idempotency_key=f"key-{batch}-{n}"
            )
        )
        clock.advance(timedelta(milliseconds=1))


def relay(
    store: InMemoryStore, publisher: FakeEventPublisher, clock: FrozenClock
) -> RelayOutbox:
    tx = store.begin()
    return RelayOutbox(
        outbox=InMemoryOutboxRepository(tx),
        publisher=publisher,
        transaction=tx,
        clock=clock,
    )


async def test_publishes_oldest_first_in_batches_and_marks_published() -> None:
    store, clock, publisher = InMemoryStore(), FrozenClock(), FakeEventPublisher()
    await accept_payments(store, clock, 3)

    assert await relay(store, publisher, clock).run_once(batch_size=2) == 2
    assert await relay(store, publisher, clock).run_once(batch_size=2) == 1
    assert await relay(store, publisher, clock).run_once(batch_size=2) == 0

    created_order = sorted(store.outbox.values(), key=lambda m: m.created_at)
    assert [m.id for m in publisher.published] == [m.id for m in created_order]
    assert all(m.published_at == clock.now() for m in store.outbox.values())


async def test_broker_outage_keeps_records_for_the_next_round() -> None:
    store, clock, publisher = InMemoryStore(), FrozenClock(), FakeEventPublisher()
    await accept_payments(store, clock, 2)
    publisher.broker_down = True

    assert await relay(store, publisher, clock).run_once(batch_size=10) == 0

    records = sorted(store.outbox.values(), key=lambda m: m.created_at)
    assert [m.published_at for m in records] == [None, None]
    assert records[0].attempts == 1
    assert records[0].last_error == "broker unavailable"
    assert records[1].attempts == 0  # the round stops at the first failure

    publisher.broker_down = False
    assert await relay(store, publisher, clock).run_once(batch_size=10) == 2
    assert all(m.published_at is not None for m in store.outbox.values())


async def test_purge_deletes_only_published_records_older_than_retention() -> None:
    store, clock, publisher = InMemoryStore(), FrozenClock(), FakeEventPublisher()
    await accept_payments(store, clock, 1)
    await relay(store, publisher, clock).run_once(batch_size=10)
    clock.advance(timedelta(days=8))
    await accept_payments(store, clock, 1, batch="b")  # unpublished, must survive

    deleted = await relay(store, publisher, clock).purge(retention=timedelta(days=7))

    assert deleted == 1
    [survivor] = store.outbox.values()
    assert survivor.published_at is None

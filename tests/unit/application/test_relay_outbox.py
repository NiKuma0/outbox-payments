from datetime import timedelta
from unittest.mock import Mock, call

import pytest

from outbox_payments.application.errors import PublishError
from outbox_payments.application.outbox import OutboxMessage
from outbox_payments.application.use_cases.relay_outbox import RelayOutbox
from tests.fakes.clock import FrozenClock
from tests.support.builders import make_payment
from tests.support.mocks import mock_outbox, mock_publisher, mock_transaction

pytestmark = pytest.mark.anyio


def messages(count: int) -> list[OutboxMessage]:
    return [make_payment(idempotency_key=f"key-{n}")[1] for n in range(count)]


class Ports:
    def __init__(self, claimed: list[OutboxMessage] | None = None) -> None:
        self.outbox = mock_outbox()
        self.outbox.claim_batch.return_value = claimed or []
        self.publisher = mock_publisher()
        self.transaction = mock_transaction()
        self.clock = FrozenClock()

    def relay(self) -> RelayOutbox:
        return RelayOutbox(
            outbox=self.outbox,
            publisher=self.publisher,
            transaction=self.transaction,
            clock=self.clock,
        )


def published(publisher: Mock) -> list[OutboxMessage]:
    return [c.args[0] for c in publisher.publish.await_args_list]


async def test_publishes_the_claimed_batch_in_order_and_marks_it_published() -> None:
    batch = messages(3)
    ports = Ports(batch)

    assert await ports.relay().run_once(batch_size=3) == 3

    ports.outbox.claim_batch.assert_awaited_once_with(3)
    assert published(ports.publisher) == batch
    ports.outbox.mark_published.assert_awaited_once_with(
        [m.id for m in batch], at=ports.clock.now()
    )
    ports.transaction.commit.assert_awaited_once()


async def test_empty_round_publishes_nothing() -> None:
    ports = Ports()

    assert await ports.relay().run_once(batch_size=10) == 0

    ports.publisher.publish.assert_not_awaited()
    ports.outbox.mark_published.assert_not_awaited()
    ports.transaction.commit.assert_awaited_once()  # ends the claiming transaction


async def test_broker_outage_records_the_failure_and_stops_the_round() -> None:
    batch = messages(3)
    ports = Ports(batch)
    ports.publisher.publish.side_effect = [None, PublishError("broker unavailable")]

    assert await ports.relay().run_once(batch_size=10) == 1

    assert published(ports.publisher) == batch[:2]  # the third is not even tried
    assert ports.outbox.mock_calls[1:] == [
        call.record_failure(batch[1].id, "broker unavailable"),
        call.mark_published([batch[0].id], at=ports.clock.now()),
    ]
    ports.transaction.commit.assert_awaited_once()


async def test_purge_deletes_records_published_before_the_retention_window() -> None:
    ports = Ports()
    ports.outbox.delete_published_before.return_value = 1

    deleted = await ports.relay().purge(retention=timedelta(days=7))

    assert deleted == 1
    ports.outbox.delete_published_before.assert_awaited_once_with(
        ports.clock.now() - timedelta(days=7)
    )
    ports.transaction.commit.assert_awaited_once()

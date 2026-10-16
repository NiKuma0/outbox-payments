"""ProcessPayment must be safe to re-run from any step: every redelivery scenario below
starts from what a crash at a different point would have left committed."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid7

import pytest

from outbox_payments.application.errors import (
    PaymentNotFoundError,
    WebhookRejectedError,
    WebhookTemporarilyUnavailableError,
)
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.domain import ChargeOutcome, Payment, PaymentStatus
from tests.cases._helpers import as_params
from tests.cases.application.process_payment import (
    EXTERNAL_CALL_CASES,
    GATEWAY_OUTCOME_CASES,
    ExternalCallCase,
    GatewayOutcomeCase,
)
from tests.fakes.clock import FrozenClock
from tests.fakes.provider import FakePaymentProvider
from tests.fakes.webhooks import RecordingWebhookSender
from tests.support.builders import T0, make_payment
from tests.support.mocks import mock_payments, mock_transaction, serve

pytestmark = pytest.mark.anyio


def pending() -> Payment:
    payment, _ = make_payment(metadata={"order_id": 42})
    return payment


def completed(
    outcome: ChargeOutcome = ChargeOutcome.APPROVED,
    *,
    delivered: bool = False,
    of: Payment | None = None,
) -> Payment:
    """``of`` (a copy of it) or a new payment, completed as a committed charge left it."""
    payment = pending() if of is None else deepcopy(of)
    payment.complete(outcome, now=T0 + timedelta(seconds=1))
    if delivered:
        payment.mark_webhook_delivered(now=T0 + timedelta(seconds=2))
    return payment


@dataclass
class World:
    stored: Payment | None = field(default_factory=pending)
    clock: FrozenClock = field(default_factory=FrozenClock)
    provider: FakePaymentProvider = field(default_factory=FakePaymentProvider)
    webhooks: RecordingWebhookSender = field(default_factory=RecordingWebhookSender)
    transaction: Mock = field(default_factory=mock_transaction)
    event_id = uuid7()

    def __post_init__(self) -> None:
        self.payments = mock_payments(self.stored)

    async def deliver(self) -> None:
        self.clock.advance(timedelta(seconds=1))
        await ProcessPayment(
            payments=self.payments,
            provider=self.provider,
            webhooks=self.webhooks,
            transaction=self.transaction,
            clock=self.clock,
        ).execute(payment_id=self.payment.id, event_id=self.event_id)

    @property
    def payment(self) -> Payment:
        assert self.stored is not None
        return self.stored

    def completed_with(self) -> Payment:
        """The payment the last ``complete_if_pending`` call tried to persist."""
        return self.payments.complete_if_pending.await_args.args[0]

    def delivered_with(self) -> Payment:
        return self.payments.mark_webhook_delivered.await_args.args[0]


@pytest.mark.parametrize("case", as_params(GATEWAY_OUTCOME_CASES))
async def test_gateway_outcome_sets_final_status_and_webhook(
    case: GatewayOutcomeCase,
) -> None:
    world = World(provider=FakePaymentProvider(case["outcome"]))

    await world.deliver()

    stored = world.completed_with()
    assert stored.status is case["expected_status"]
    assert stored.processed_at is not None
    assert world.delivered_with().webhook_delivered_at is not None
    assert world.transaction.commit.await_count == 2  # after the charge, after the hook
    [webhook] = world.webhooks.delivered
    assert webhook.webhook_id == world.event_id
    assert webhook.url == world.payment.webhook_url
    assert webhook.payload == {
        "payment_id": str(world.payment.id),
        "processed_at": stored.processed_at.isoformat(),
        **case["expected_webhook_payload"],
    }


async def test_fully_processed_payment_is_left_alone() -> None:
    world = World(stored=completed(delivered=True))

    await world.deliver()

    assert world.provider.calls == []
    assert world.webhooks.attempts == []
    world.transaction.commit.assert_not_awaited()


async def test_crash_after_charge_before_commit_replays_the_gateway_idempotently() -> (
    None
):
    world = World(provider=FakePaymentProvider(ChargeOutcome.DECLINED))
    world.transaction.commit.side_effect = [
        ConnectionError("process killed"),
        None,
        None,
    ]

    with pytest.raises(ConnectionError):
        await world.deliver()
    # Nothing was committed, so the redelivery loads the payment still pending.
    await world.deliver()

    assert world.provider.calls == [
        world.payment.id,
        world.payment.id,
    ]  # asked twice...
    assert world.provider.charges == 1  # ...charged once, same key
    assert world.completed_with().status is PaymentStatus.FAILED
    assert len(world.webhooks.delivered) == 1


async def test_webhook_failure_keeps_the_committed_outcome() -> None:
    world = World(
        webhooks=RecordingWebhookSender([WebhookTemporarilyUnavailableError("503")])
    )

    with pytest.raises(WebhookTemporarilyUnavailableError):
        await world.deliver()

    assert world.completed_with().status is PaymentStatus.SUCCEEDED
    world.transaction.commit.assert_awaited_once()
    world.payments.mark_webhook_delivered.assert_not_awaited()


async def test_redelivery_after_a_committed_charge_resumes_at_the_webhook() -> None:
    world = World(stored=completed())

    await world.deliver()

    assert world.provider.calls == []
    world.payments.complete_if_pending.assert_not_awaited()
    assert len(world.webhooks.delivered) == 1
    assert world.delivered_with().webhook_delivered_at is not None
    world.transaction.commit.assert_awaited_once()


async def test_rejected_webhook_keeps_the_final_status() -> None:
    world = World(webhooks=RecordingWebhookSender([WebhookRejectedError("404")]))

    with pytest.raises(WebhookRejectedError):
        await world.deliver()

    assert world.completed_with().status is PaymentStatus.SUCCEEDED
    world.payments.mark_webhook_delivered.assert_not_awaited()


async def test_losing_the_completion_race_reports_the_winners_outcome() -> None:
    world = World(provider=FakePaymentProvider(ChargeOutcome.APPROVED))
    world.payments.complete_if_pending.return_value = False
    serve(
        world.payments,
        world.payment,
        completed(ChargeOutcome.DECLINED, of=world.payment),
    )

    await world.deliver()

    [webhook] = world.webhooks.delivered
    assert webhook.payload["status"] == "failed"
    assert world.delivered_with().status is PaymentStatus.FAILED


async def test_unknown_payment_is_a_permanent_error() -> None:
    world = World()
    world.payments = mock_payments()

    with pytest.raises(PaymentNotFoundError):
        await world.deliver()


def journaled(journal: list[str], name: str, answer: Callable[..., object]) -> object:
    """A mock ``side_effect`` that logs ``name`` and then answers like before."""

    def side_effect(*args: object, **kwargs: object) -> object:
        journal.append(name)
        return answer(*args, **kwargs)

    return side_effect


@pytest.mark.parametrize("case", as_params(EXTERNAL_CALL_CASES))
async def test_no_transaction_is_open_during_external_calls(
    case: ExternalCallCase,
) -> None:
    journal: list[str] = []
    stored = {
        "pending": pending,
        "charged": completed,
        "delivered": lambda: completed(delivered=True),
    }[case["stored"]]()
    world = World(
        stored=stored,
        provider=FakePaymentProvider(journal=journal),
        webhooks=RecordingWebhookSender(journal=journal),
    )
    if case["loses_completion_race"]:
        serve(world.payments, stored, completed(ChargeOutcome.DECLINED, of=stored))
    won = not case["loses_completion_race"]

    def complete_if_pending(_: Payment) -> bool:
        return won

    def nothing(*_: object) -> None:
        return None

    payments, transaction = world.payments, world.transaction
    payments.get.side_effect = journaled(journal, "get", payments.get.side_effect)
    payments.complete_if_pending.side_effect = journaled(
        journal, "complete_if_pending", complete_if_pending
    )
    payments.mark_webhook_delivered.side_effect = journaled(
        journal, "mark_webhook_delivered", nothing
    )
    transaction.commit.side_effect = journaled(journal, "commit", nothing)
    transaction.rollback.side_effect = journaled(journal, "rollback", nothing)

    await world.deliver()

    assert journal == case["expected_journal"]

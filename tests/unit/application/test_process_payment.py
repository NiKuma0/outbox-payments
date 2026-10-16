"""ProcessPayment must be safe to re-run from any step: every scenario below is a
redelivery of the same message after a crash at a different point."""

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid7

import pytest

from outbox_payments.application.errors import (
    PaymentNotFoundError,
    WebhookRejectedError,
    WebhookTemporarilyUnavailableError,
)
from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.domain import ChargeOutcome, Payment, PaymentStatus
from tests.cases._helpers import as_params
from tests.cases.application.create_payment import BASE_REQUEST
from tests.cases.application.process_payment import (
    GATEWAY_OUTCOME_CASES,
    GatewayOutcomeCase,
)
from tests.fakes.clock import FrozenClock
from tests.fakes.provider import FakePaymentProvider
from tests.fakes.store import (
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    InMemoryStore,
    InMemoryTransaction,
)
from tests.fakes.webhooks import RecordingWebhookSender

pytestmark = pytest.mark.anyio


@dataclass
class World:
    store: InMemoryStore = field(default_factory=InMemoryStore)
    clock: FrozenClock = field(default_factory=FrozenClock)
    provider: FakePaymentProvider = field(default_factory=FakePaymentProvider)
    webhooks: RecordingWebhookSender = field(default_factory=RecordingWebhookSender)

    async def create_payment(self) -> tuple[Payment, UUID]:
        tx = self.store.begin()
        payment = await CreatePayment(
            payments=InMemoryPaymentRepository(tx),
            outbox=InMemoryOutboxRepository(tx),
            transaction=tx,
            clock=self.clock,
        ).execute(CreatePaymentCommand(**BASE_REQUEST))
        [message] = self.store.outbox.values()
        return payment, message.id

    async def deliver(
        self, payment_id: UUID, event_id: UUID, tx: InMemoryTransaction | None = None
    ) -> None:
        """One message delivery = one fresh transaction, like one session per message."""
        tx = tx or self.store.begin()
        self.clock.advance(timedelta(seconds=1))
        await ProcessPayment(
            payments=InMemoryPaymentRepository(tx),
            provider=self.provider,
            webhooks=self.webhooks,
            transaction=tx,
            clock=self.clock,
        ).execute(payment_id=payment_id, event_id=event_id)

    def stored(self, payment_id: UUID) -> Payment:
        return self.store.payments[payment_id]


@pytest.mark.parametrize("case", as_params(GATEWAY_OUTCOME_CASES))
async def test_gateway_outcome_sets_final_status_and_webhook(
    case: GatewayOutcomeCase,
) -> None:
    world = World(provider=FakePaymentProvider(case["outcome"]))
    payment, event_id = await world.create_payment()

    await world.deliver(payment.id, event_id)

    stored = world.stored(payment.id)
    assert stored.status is case["expected_status"]
    assert stored.processed_at is not None
    assert stored.webhook_delivered_at is not None
    [webhook] = world.webhooks.delivered
    assert webhook.webhook_id == event_id
    assert webhook.url == payment.webhook_url
    assert webhook.payload == {
        "payment_id": str(payment.id),
        "processed_at": stored.processed_at.isoformat(),
        **case["expected_webhook_payload"],
    }


async def test_duplicate_event_charges_once_and_notifies_once() -> None:
    world = World()
    payment, event_id = await world.create_payment()

    await world.deliver(payment.id, event_id)
    await world.deliver(payment.id, event_id)

    assert world.provider.calls == [payment.id]
    assert len(world.webhooks.delivered) == 1


async def test_crash_after_charge_before_commit_replays_the_gateway_idempotently() -> (
    None
):
    world = World(provider=FakePaymentProvider(ChargeOutcome.DECLINED))
    payment, event_id = await world.create_payment()
    crashing = world.store.begin()
    crashing.fail_next_commit = ConnectionError("process killed")

    with pytest.raises(ConnectionError):
        await world.deliver(payment.id, event_id, tx=crashing)
    assert world.stored(payment.id).status is PaymentStatus.PENDING

    await world.deliver(payment.id, event_id)

    assert world.provider.calls == [payment.id, payment.id]  # asked twice...
    assert world.provider.charges == 1  # ...charged once, same key
    assert world.stored(payment.id).status is PaymentStatus.FAILED
    assert len(world.webhooks.delivered) == 1


async def test_crash_after_commit_before_webhook_resumes_at_the_webhook() -> None:
    world = World(
        webhooks=RecordingWebhookSender([WebhookTemporarilyUnavailableError("503")])
    )
    payment, event_id = await world.create_payment()

    with pytest.raises(WebhookTemporarilyUnavailableError):
        await world.deliver(payment.id, event_id)
    assert world.stored(payment.id).status is PaymentStatus.SUCCEEDED
    assert world.stored(payment.id).webhook_delivered_at is None

    await world.deliver(payment.id, event_id)

    assert world.provider.calls == [payment.id]
    assert len(world.webhooks.attempts) == 2
    assert world.stored(payment.id).webhook_delivered_at is not None


async def test_rejected_webhook_keeps_the_final_status() -> None:
    world = World(webhooks=RecordingWebhookSender([WebhookRejectedError("404")]))
    payment, event_id = await world.create_payment()

    with pytest.raises(WebhookRejectedError):
        await world.deliver(payment.id, event_id)

    assert world.stored(payment.id).status is PaymentStatus.SUCCEEDED
    assert world.stored(payment.id).webhook_delivered_at is None


async def test_unknown_payment_is_a_permanent_error() -> None:
    with pytest.raises(PaymentNotFoundError):
        await World().deliver(uuid7(), uuid7())

"""The FastStream handler end to end in-process, via TestRabbitBroker and mocks.

TestRabbitBroker does not emulate TTLs or dead-lettering; that half of the retry
mechanism is covered against a real RabbitMQ in tests/integration/test_retry_topology.py.
"""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import Mock
from uuid import uuid7

import pytest
from faststream.rabbit import RabbitBroker, RabbitMessage, RabbitQueue, TestRabbitBroker

from outbox_payments.adapters.messaging.retry import RetryPolicy
from outbox_payments.adapters.messaging.topology import PAYMENTS_EXCHANGE, ROUTING_KEY
from outbox_payments.application.errors import (
    WebhookRejectedError,
    WebhookTemporarilyUnavailableError,
)
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.domain import Payment, PaymentStatus
from outbox_payments.entrypoints.consumer import ConsumerResources, create_broker
from tests.cases._helpers import as_params
from tests.cases.entrypoints.consumer import (
    CONSUMER_OUTCOME_CASES,
    ConsumerOutcomeCase,
    Failure,
)
from tests.fakes.clock import FrozenClock
from tests.fakes.provider import FakePaymentProvider
from tests.fakes.webhooks import RecordingWebhookSender
from tests.support.builders import make_payment
from tests.support.mocks import mock_payments, mock_transaction

pytestmark = pytest.mark.anyio

DESTINATIONS = [
    "payments.new.retry.1",
    "payments.new.retry.2",
    "payments.new.retry.3",
    "payments.new.dlq",
]


@dataclass
class Captured:
    queue: str
    body: bytes
    headers: dict[str, object]
    message_id: str | None


@dataclass
class Harness:
    failure: Failure
    clock: FrozenClock = field(default_factory=FrozenClock)
    provider: FakePaymentProvider = field(default_factory=FakePaymentProvider)
    captured: list[Captured] = field(default_factory=list[Captured])
    transaction: Mock = field(default_factory=mock_transaction)

    def __post_init__(self) -> None:
        self.payment, self.message = make_payment()
        self.payments = mock_payments(self.payment)
        failures: dict[Failure, list[Exception]] = {
            "webhook-5xx": [
                WebhookTemporarilyUnavailableError("receiver answered 503")
            ],
            "webhook-4xx": [WebhookRejectedError("receiver answered 404")],
        }
        self.webhooks = RecordingWebhookSender(failures.get(self.failure, []))

    @asynccontextmanager
    async def process_payment(self) -> AsyncGenerator[ProcessPayment]:
        if self.failure == "database-down":
            raise ConnectionRefusedError("postgres:5432")
        yield ProcessPayment(
            payments=self.payments,
            provider=self.provider,
            webhooks=self.webhooks,
            transaction=self.transaction,
            clock=self.clock,
        )

    def broker(self) -> RabbitBroker:
        broker = create_broker(
            "amqp://test/",
            ConsumerResources(
                process_payment=self.process_payment,
                policy=RetryPolicy(
                    max_retries=3, base_delay_seconds=1, backoff_factor=4
                ),
                clock=self.clock,
            ),
            prefetch_count=1,
        )
        for name in DESTINATIONS:
            broker.subscriber(RabbitQueue(name, declare=False))(
                self._capture_into(name)
            )
        return broker

    def _capture_into(self, queue: str) -> Callable[[RabbitMessage], Awaitable[None]]:
        async def capture(message: RabbitMessage) -> None:
            headers = cast("dict[str, object]", message.headers)
            self.captured.append(
                Captured(queue, message.body, headers, message.message_id)
            )

        return capture

    def event_payload(self) -> dict[str, str]:
        """What the relay publishes for the stored payment."""
        return cast("dict[str, str]", self.message.payload)

    def delivered_with(self) -> Payment:
        return self.payments.mark_webhook_delivered.await_args.args[0]


@pytest.mark.parametrize("case", as_params(CONSUMER_OUTCOME_CASES))
async def test_consumer_outcome(case: ConsumerOutcomeCase) -> None:
    harness = Harness(case["failure"])
    payload = harness.event_payload()
    if case["failure"] == "unknown-payment":
        payload = {**payload, "payment_id": str(uuid7())}
    body = (
        b"{not json"
        if case["failure"] == "malformed-body"
        else json.dumps(payload).encode()
    )
    retry_count = case.get("incoming_retry_count")

    async with TestRabbitBroker(harness.broker()) as broker:
        await broker.publish(
            body,
            exchange=PAYMENTS_EXCHANGE,
            routing_key=ROUTING_KEY,
            headers=None if retry_count is None else {"x-retry-count": retry_count},
            message_id=payload["event_id"],
        )

    if case["expected_queue"] is None:
        assert harness.captured == []
        return
    [republished] = harness.captured
    assert republished.queue == case["expected_queue"]
    assert republished.body == body  # forwarded untouched
    assert republished.message_id == payload["event_id"]
    assert republished.headers["x-retry-count"] == case.get("expected_retry_count")
    if republished.queue.endswith(".dlq"):
        assert republished.headers["x-failed-at"] == harness.clock.now().isoformat()
        assert isinstance(republished.headers["x-last-error"], str)
        assert republished.headers["x-last-error"]


async def test_successful_message_completes_payment_and_sends_webhook() -> None:
    harness = Harness("none")
    payload = harness.event_payload()

    async with TestRabbitBroker(harness.broker()) as broker:
        await broker.publish(
            json.dumps(payload).encode(),
            exchange=PAYMENTS_EXCHANGE,
            routing_key=ROUTING_KEY,
        )

    payment = harness.delivered_with()
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.webhook_delivered_at is not None
    assert [str(w.webhook_id) for w in harness.webhooks.delivered] == [
        payload["event_id"]
    ]

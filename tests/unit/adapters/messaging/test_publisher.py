import pytest
from faststream.rabbit import RabbitBroker, RabbitMessage, TestRabbitBroker

from outbox_payments.adapters.messaging.publisher import RabbitEventPublisher
from outbox_payments.adapters.messaging.topology import (
    PAYMENTS_EXCHANGE,
    payments_queue,
)
from outbox_payments.application.errors import PublishError
from tests.support.builders import make_payment

pytestmark = pytest.mark.anyio


async def test_publishes_payload_to_the_payments_queue_with_event_id_as_message_id() -> (
    None
):
    broker = RabbitBroker()
    # TestRabbitBroker does not carry delivery_mode through; persistence is asserted
    # against a real broker in tests/integration/test_relay.py.
    received: list[tuple[object, str | None, str | None]] = []

    @broker.subscriber(payments_queue(), PAYMENTS_EXCHANGE)
    async def _capture(body: dict[str, str], message: RabbitMessage) -> None:  # pyright: ignore[reportUnusedFunction]
        received.append((body, message.message_id, message.raw_message.type))

    _, outbox_message = make_payment()
    async with TestRabbitBroker(broker) as test_broker:
        await RabbitEventPublisher(test_broker).publish(outbox_message)

    assert received == [
        (outbox_message.payload, str(outbox_message.id), "payment.created")
    ]


async def test_unconfirmed_publish_is_reported_as_publish_error() -> None:
    disconnected = RabbitBroker("amqp://guest:guest@127.0.0.1:1/")
    _, outbox_message = make_payment()

    with pytest.raises(PublishError):
        await RabbitEventPublisher(disconnected).publish(outbox_message)

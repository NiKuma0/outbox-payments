"""EventPublisher over RabbitMQ with publisher confirms.

The broker's channel is opened with ``publisher_confirms=True`` (FastStream default)
and ``on_return_raises=True``, so ``publish`` returns only after RabbitMQ has taken
responsibility for a *routed*, persistent message; anything else raises.
"""

import json

from faststream.rabbit import RabbitBroker

from outbox_payments.adapters.messaging.topology import PAYMENTS_EXCHANGE, ROUTING_KEY
from outbox_payments.application.errors import PublishError
from outbox_payments.application.outbox import OutboxMessage


class RabbitEventPublisher:
    def __init__(
        self, broker: RabbitBroker, *, confirm_timeout_seconds: float = 5.0
    ) -> None:
        self._broker = broker
        self._timeout = confirm_timeout_seconds

    async def publish(self, message: OutboxMessage) -> None:
        try:
            await self._broker.publish(
                # Serialized here, not by FastStream: the bytes on the wire are exactly
                # the JSON stored in the outbox row.
                json.dumps(message.payload, separators=(",", ":")).encode(),
                exchange=PAYMENTS_EXCHANGE,
                routing_key=ROUTING_KEY,
                persist=True,  # delivery_mode=2: survives a broker restart
                mandatory=True,  # unroutable => returned => error, not silently dropped
                message_id=str(message.id),
                message_type=message.event_type,
                content_type="application/json",
                timestamp=message.created_at,
                timeout=self._timeout,
            )
        except Exception as exc:  # adapter boundary: any failure means "not confirmed"
            raise PublishError(f"{type(exc).__name__}: {exc}") from exc

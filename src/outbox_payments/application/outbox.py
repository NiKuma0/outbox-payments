"""Outbox records: domain events serialized for the message relay."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from outbox_payments.domain import JsonObject, PaymentCreated

PAYMENTS_NEW_ROUTING_KEY = "payments.new"


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboxMessage:
    """One row of the outbox table. ``id`` *is* the event id, which consumers dedupe on."""

    id: UUID
    event_type: str
    aggregate_id: UUID
    payload: JsonObject
    created_at: datetime
    published_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None


def outbox_message_for(event: PaymentCreated) -> OutboxMessage:
    return OutboxMessage(
        id=event.event_id,
        event_type=event.event_type,
        aggregate_id=event.payment_id,
        payload={
            "event_id": str(event.event_id),
            "payment_id": str(event.payment_id),
            "occurred_at": event.occurred_at.isoformat(),
        },
        created_at=event.occurred_at,
    )

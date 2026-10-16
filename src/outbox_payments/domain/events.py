"""Domain events. Each one becomes exactly one outbox record."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCreated:
    event_type: ClassVar[str] = "payment.created"

    payment_id: UUID
    occurred_at: datetime
    event_id: UUID = field(default_factory=uuid7)

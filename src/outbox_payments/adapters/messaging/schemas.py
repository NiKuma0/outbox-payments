"""Wire format of messages on ``payments.new``."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaymentCreatedMessage(BaseModel):
    """Mirrors the outbox payload. Unknown fields are ignored so producers can add
    fields without breaking older consumers."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_id: UUID
    payment_id: UUID
    occurred_at: datetime

"""HTTP request/response schemas. Money travels as a JSON string, never a float."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    UrlConstraints,
    field_validator,
)

from outbox_payments.domain import Currency, Payment, PaymentStatus

MAX_METADATA_BYTES = 16 * 1024
MAX_DESCRIPTION_LENGTH = 500

WebhookUrl = Annotated[HttpUrl, UrlConstraints(max_length=2048)]


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Annotated[
        Decimal, Field(gt=0, max_digits=18, decimal_places=2, examples=["100.00"])
    ]
    currency: Currency
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
    metadata: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    webhook_url: WebhookUrl

    @field_validator("metadata")
    @classmethod
    def _limit_metadata_size(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        size = len(json.dumps(value, separators=(",", ":")).encode())
        if size > MAX_METADATA_BYTES:
            raise ValueError(
                f"metadata must not exceed {MAX_METADATA_BYTES} bytes as JSON"
            )
        return value


class PaymentAcceptedResponse(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime

    @classmethod
    def of(cls, payment: Payment) -> PaymentAcceptedResponse:
        return cls(
            payment_id=payment.id, status=payment.status, created_at=payment.created_at
        )


class PaymentResponse(BaseModel):
    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, JsonValue]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def of(cls, payment: Payment) -> PaymentResponse:
        return cls(
            id=payment.id,
            amount=payment.money.amount,
            currency=payment.money.currency,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]

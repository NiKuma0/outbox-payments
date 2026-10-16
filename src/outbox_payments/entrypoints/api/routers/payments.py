from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from outbox_payments.application.use_cases.create_payment import (
    CreatePayment,
    CreatePaymentCommand,
)
from outbox_payments.application.use_cases.get_payment import GetPayment
from outbox_payments.entrypoints.api.deps import (
    get_create_payment,
    get_get_payment,
    idempotency_key,
    require_api_key,
)
from outbox_payments.entrypoints.api.schemas import (
    CreatePaymentRequest,
    PaymentAcceptedResponse,
    PaymentResponse,
)

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    body: CreatePaymentRequest,
    response: Response,
    key: Annotated[str, Depends(idempotency_key)],
    use_case: Annotated[CreatePayment, Depends(get_create_payment)],
) -> PaymentAcceptedResponse:
    """Accept a payment for asynchronous processing.

    Repeating the request with the same ``Idempotency-Key`` and body returns the
    original payment; the same key with a different body is a 409.
    """
    payment = await use_case.execute(
        CreatePaymentCommand(
            idempotency_key=key,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata=body.metadata,
            webhook_url=str(body.webhook_url),
        )
    )
    response.headers["Location"] = f"{router.prefix}/{payment.id}"
    return PaymentAcceptedResponse.of(payment)


@router.get("/{payment_id}")
async def get_payment(
    payment_id: UUID, use_case: Annotated[GetPayment, Depends(get_get_payment)]
) -> PaymentResponse:
    return PaymentResponse.of(await use_case.execute(payment_id))

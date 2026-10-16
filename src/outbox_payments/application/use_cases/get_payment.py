"""GetPayment: read a payment by id."""

from uuid import UUID

from outbox_payments.application.errors import PaymentNotFoundError
from outbox_payments.application.ports import PaymentRepository
from outbox_payments.domain import Payment


class GetPayment:
    def __init__(self, *, payments: PaymentRepository) -> None:
        self._payments = payments

    async def execute(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

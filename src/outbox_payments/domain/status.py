"""The payment state machine.

``pending`` is the only non-terminal status. A charge outcome moves the payment to
exactly one terminal status, once. Everything else is forbidden, which is what makes
redelivered messages harmless.
"""

from enum import StrEnum


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def can_transition_to(self, target: PaymentStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS[self]

    @property
    def is_final(self) -> bool:
        return not _ALLOWED_TRANSITIONS[self]


_ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}),
    PaymentStatus.SUCCEEDED: frozenset(),
    PaymentStatus.FAILED: frozenset(),
}


class ChargeOutcome(StrEnum):
    """What the payment gateway decided. A decline is a business outcome, not an error."""

    APPROVED = "approved"
    DECLINED = "declined"

    @property
    def final_status(self) -> PaymentStatus:
        return PaymentStatus.SUCCEEDED if self is ChargeOutcome.APPROVED else PaymentStatus.FAILED

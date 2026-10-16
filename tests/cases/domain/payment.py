from typing import TypedDict

from outbox_payments.domain import ChargeOutcome, PaymentStatus


class StatusTransitionCase(TypedDict):
    id: str
    current: PaymentStatus
    target: PaymentStatus
    allowed: bool


class ChargeOutcomeCase(TypedDict):
    id: str
    outcome: ChargeOutcome
    expected_status: PaymentStatus


STATUS_TRANSITION_CASES: list[StatusTransitionCase] = [
    {
        "id": "pending-payment-can-succeed",
        "current": PaymentStatus.PENDING,
        "target": PaymentStatus.SUCCEEDED,
        "allowed": True,
    },
    {
        "id": "pending-payment-can-fail",
        "current": PaymentStatus.PENDING,
        "target": PaymentStatus.FAILED,
        "allowed": True,
    },
    {
        "id": "pending-payment-cannot-become-pending-again",
        "current": PaymentStatus.PENDING,
        "target": PaymentStatus.PENDING,
        "allowed": False,
    },
    {
        "id": "succeeded-payment-cannot-fail-later",
        "current": PaymentStatus.SUCCEEDED,
        "target": PaymentStatus.FAILED,
        "allowed": False,
    },
    {
        "id": "succeeded-payment-cannot-be-reopened",
        "current": PaymentStatus.SUCCEEDED,
        "target": PaymentStatus.PENDING,
        "allowed": False,
    },
    {
        "id": "succeeded-payment-cannot-succeed-twice",
        "current": PaymentStatus.SUCCEEDED,
        "target": PaymentStatus.SUCCEEDED,
        "allowed": False,
    },
    {
        "id": "failed-payment-cannot-succeed-later",
        "current": PaymentStatus.FAILED,
        "target": PaymentStatus.SUCCEEDED,
        "allowed": False,
    },
    {
        "id": "failed-payment-cannot-be-reopened",
        "current": PaymentStatus.FAILED,
        "target": PaymentStatus.PENDING,
        "allowed": False,
    },
]

CHARGE_OUTCOME_CASES: list[ChargeOutcomeCase] = [
    {
        "id": "approved-charge-makes-payment-succeeded",
        "outcome": ChargeOutcome.APPROVED,
        "expected_status": PaymentStatus.SUCCEEDED,
    },
    {
        "id": "declined-charge-makes-payment-failed",
        "outcome": ChargeOutcome.DECLINED,
        "expected_status": PaymentStatus.FAILED,
    },
]

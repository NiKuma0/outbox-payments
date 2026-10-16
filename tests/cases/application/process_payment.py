from typing import Literal, TypedDict

from outbox_payments.domain import ChargeOutcome, JsonObject, PaymentStatus


class GatewayOutcomeCase(TypedDict):
    id: str
    outcome: ChargeOutcome
    expected_status: PaymentStatus
    expected_webhook_payload: JsonObject


GATEWAY_OUTCOME_CASES: list[GatewayOutcomeCase] = [
    {
        "id": "approved-charge-notifies-client-of-success",
        "outcome": ChargeOutcome.APPROVED,
        "expected_status": PaymentStatus.SUCCEEDED,
        "expected_webhook_payload": {
            "status": "succeeded",
            "amount": "100.00",
            "currency": "RUB",
            "metadata": {"order_id": 42},
        },
    },
    {
        "id": "declined-charge-is-a-business-outcome-and-notifies-client-of-failure",
        "outcome": ChargeOutcome.DECLINED,
        "expected_status": PaymentStatus.FAILED,
        "expected_webhook_payload": {
            "status": "failed",
            "amount": "100.00",
            "currency": "RUB",
            "metadata": {"order_id": 42},
        },
    },
]


class ExternalCallCase(TypedDict):
    """``expected_journal`` is every repository call, transaction end and external
    call in order. A gateway or webhook call must never follow a repository call
    without a ``commit``/``rollback`` in between: that would hold a pooled connection
    in an open transaction for the 2-5 s charge or the webhook timeout."""

    id: str
    stored: Literal["pending", "charged", "delivered"]
    loses_completion_race: bool
    expected_journal: list[str]


EXTERNAL_CALL_CASES: list[ExternalCallCase] = [
    {
        "id": "pending-payment-ends-each-transaction-before-calling-out",
        "stored": "pending",
        "loses_completion_race": False,
        "expected_journal": [
            "get",
            "rollback",
            "charge",
            "complete_if_pending",
            "commit",
            "webhook",
            "mark_webhook_delivered",
            "commit",
        ],
    },
    {
        "id": "charged-payment-ends-the-read-before-the-webhook",
        "stored": "charged",
        "loses_completion_race": False,
        "expected_journal": [
            "get",
            "rollback",
            "webhook",
            "mark_webhook_delivered",
            "commit",
        ],
    },
    {
        "id": "lost-completion-race-ends-the-reload-before-the-webhook",
        "stored": "pending",
        "loses_completion_race": True,
        "expected_journal": [
            "get",
            "rollback",
            "charge",
            "complete_if_pending",
            "commit",
            "get",
            "rollback",
            "webhook",
            "mark_webhook_delivered",
            "commit",
        ],
    },
    {
        "id": "fully-processed-payment-only-reads",
        "stored": "delivered",
        "loses_completion_race": False,
        "expected_journal": ["get", "rollback"],
    },
]

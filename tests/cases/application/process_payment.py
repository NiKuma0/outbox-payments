from typing import TypedDict

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

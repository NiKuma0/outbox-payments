"""The emulated gateway approves a charge when its random draw is below the success rate."""

from typing import TypedDict

from outbox_payments.domain import ChargeOutcome


class GatewayDrawCase(TypedDict):
    id: str
    draw: float
    expected: ChargeOutcome


SUCCESS_RATE = 0.9

GATEWAY_DRAW_CASES: list[GatewayDrawCase] = [
    {"id": "lowest-draw-is-approved", "draw": 0.0, "expected": ChargeOutcome.APPROVED},
    {
        "id": "draw-just-below-success-rate-is-approved",
        "draw": 0.8999,
        "expected": ChargeOutcome.APPROVED,
    },
    {
        "id": "draw-at-success-rate-is-declined",
        "draw": 0.9,
        "expected": ChargeOutcome.DECLINED,
    },
    {
        "id": "highest-draw-is-declined",
        "draw": 0.9999,
        "expected": ChargeOutcome.DECLINED,
    },
]

"""Request fingerprinting for idempotency.

The fingerprint is a SHA-256 over a canonical JSON form of the *validated* request, so
cosmetic differences (``"100"`` vs ``"100.00"``, metadata key order) do not turn a
legitimate retry into a 409, while any semantic difference does.
"""

import hashlib
import json

from outbox_payments.domain.money import Money
from outbox_payments.domain.types import JsonObject


def request_fingerprint(
    *, money: Money, description: str, metadata: JsonObject, webhook_url: str
) -> str:
    canonical = {
        "amount": str(money.amount),
        "currency": money.currency.value,
        "description": description,
        "metadata": metadata,
        "webhook_url": webhook_url,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()

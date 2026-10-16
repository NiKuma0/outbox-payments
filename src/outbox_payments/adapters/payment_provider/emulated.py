"""A stand-in payment gateway: 2-5 s latency, 90 % approvals by default.

Randomness and sleeping are injected, so tests are deterministic and never wait.
Like a real gateway it is idempotent on the key it is given: the payment id. The
record of past charges lives in memory here; a real gateway keeps it on its side,
which is what makes "crash after charge, before commit" safe across restarts.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from uuid import UUID

from outbox_payments.domain import ChargeOutcome, Money


class EmulatedPaymentProvider:
    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        success_rate: float = 0.9,
    ) -> None:
        self._rng = rng or random.Random()
        self._sleep = sleep
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate
        self._outcomes: dict[UUID, ChargeOutcome] = {}

    @property
    def charges(self) -> int:
        return len(self._outcomes)

    async def charge(self, payment_id: UUID, money: Money) -> ChargeOutcome:
        if (known := self._outcomes.get(payment_id)) is not None:
            return known
        await self._sleep(self._rng.uniform(self._min_delay, self._max_delay))
        approved = self._rng.random() < self._success_rate
        outcome = ChargeOutcome.APPROVED if approved else ChargeOutcome.DECLINED
        return self._outcomes.setdefault(payment_id, outcome)

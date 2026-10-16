from uuid import UUID

from outbox_payments.domain import ChargeOutcome, Money


class FakePaymentProvider:
    """Scripted gateway that honours the idempotency key like a real one would."""

    def __init__(
        self,
        outcome: ChargeOutcome = ChargeOutcome.APPROVED,
        *,
        journal: list[str] | None = None,
    ) -> None:
        self.outcome = outcome
        self.journal = journal
        self.outcomes: dict[UUID, ChargeOutcome] = {}
        self.calls: list[UUID] = []

    @property
    def charges(self) -> int:
        """Charges that actually moved money (not idempotent replays)."""
        return len(self.outcomes)

    async def charge(self, payment_id: UUID, money: Money) -> ChargeOutcome:
        self.calls.append(payment_id)
        if self.journal is not None:
            self.journal.append("charge")
        return self.outcomes.setdefault(payment_id, self.outcome)

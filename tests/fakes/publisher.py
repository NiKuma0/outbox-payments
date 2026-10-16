from outbox_payments.application.errors import PublishError
from outbox_payments.application.outbox import OutboxMessage


class FakeEventPublisher:
    """Collects confirmed messages; while ``broker_down`` every publish is unconfirmed."""

    def __init__(self) -> None:
        self.published: list[OutboxMessage] = []
        self.broker_down = False

    async def publish(self, message: OutboxMessage) -> None:
        if self.broker_down:
            raise PublishError("broker unavailable")
        self.published.append(message)

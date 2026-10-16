from outbox_payments.application.webhooks import WebhookNotification


class RecordingWebhookSender:
    """Records deliveries; ``failures`` are raised one by one before succeeding."""

    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.failures = list(failures or [])
        self.attempts: list[WebhookNotification] = []
        self.delivered: list[WebhookNotification] = []

    async def send(self, notification: WebhookNotification) -> None:
        self.attempts.append(notification)
        if self.failures:
            raise self.failures.pop(0)
        self.delivered.append(notification)

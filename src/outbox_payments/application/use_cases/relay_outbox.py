"""RelayOutbox: move committed events from the outbox table to the broker.

Per round: claim a batch (``FOR UPDATE SKIP LOCKED`` in SQL, so replicas never pick the
same rows), publish each record and wait for the broker's confirm, mark the confirmed
ones as published, commit. A crash after a confirm but before the commit republishes
those records on the next round: delivery is **at-least-once**, and consumers dedupe.
"""

import logging
from datetime import timedelta
from uuid import UUID

from outbox_payments.application.errors import PublishError
from outbox_payments.application.ports import (
    Clock,
    EventPublisher,
    OutboxRepository,
    Transaction,
)

logger = logging.getLogger(__name__)


class RelayOutbox:
    def __init__(
        self,
        *,
        outbox: OutboxRepository,
        publisher: EventPublisher,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._outbox = outbox
        self._publisher = publisher
        self._transaction = transaction
        self._clock = clock

    async def run_once(self, *, batch_size: int) -> int:
        """Publish one batch. Returns how many records were confirmed by the broker."""
        published: list[UUID] = []
        for message in await self._outbox.claim_batch(batch_size):
            try:
                await self._publisher.publish(message)
            except PublishError as exc:
                # The broker is most likely down: stop the round instead of burning
                # through the batch, keep the error for operators, retry next round.
                await self._outbox.record_failure(message.id, str(exc))
                logger.warning(
                    "publish failed",
                    extra={"event_id": str(message.id), "error": str(exc)},
                )
                break
            published.append(message.id)
            logger.info(
                "event published",
                extra={
                    "event_id": str(message.id),
                    "payment_id": str(message.aggregate_id),
                },
            )

        if published:
            await self._outbox.mark_published(published, at=self._clock.now())
        await self._transaction.commit()
        return len(published)

    async def purge(self, *, retention: timedelta) -> int:
        """Delete records published more than ``retention`` ago."""
        deleted = await self._outbox.delete_published_before(
            self._clock.now() - retention
        )
        await self._transaction.commit()
        if deleted:
            logger.info("outbox purged", extra={"deleted": deleted})
        return deleted

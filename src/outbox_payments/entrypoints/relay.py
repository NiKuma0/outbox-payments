"""Outbox relay process: ``python -m outbox_payments.entrypoints.relay``.

Runs as its own compose service and can be scaled to several replicas: claims use
``FOR UPDATE SKIP LOCKED``, so replicas share the backlog instead of duplicating it.
"""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import partial

from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import Channel

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.db.repositories import SqlOutboxRepository
from outbox_payments.adapters.db.session import create_engine, create_session_factory
from outbox_payments.adapters.messaging.publisher import RabbitEventPublisher
from outbox_payments.adapters.messaging.retry import RetryPolicy
from outbox_payments.adapters.messaging.topology import declare_topology
from outbox_payments.application.use_cases.relay_outbox import RelayOutbox
from outbox_payments.config import Settings, get_settings
from outbox_payments.entrypoints.heartbeat import DEFAULT_PATH, beat_forever
from outbox_payments.entrypoints.logs import configure_logging
from outbox_payments.entrypoints.signals import (
    install_stop_signals,
    sleep_unless_stopped,
)

logger = logging.getLogger(__name__)


class RelayWorker:
    """The polling loop, independent of SQL and AMQP so it can be unit tested.

    A full batch means there is probably more backlog, so the next round starts at
    once; a partial or failed round waits ``poll_interval``. Shutdown is checked
    between rounds, so a SIGTERM never interrupts a batch between publish and commit.
    """

    def __init__(
        self,
        *,
        relay_round: Callable[[], Awaitable[int]],
        purge: Callable[[], Awaitable[int]],
        batch_size: int,
        poll_interval: float,
        cleanup_interval: float,
        idle: Callable[[float], Awaitable[None]],
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._relay_round = relay_round
        self._purge = purge
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._cleanup_interval = cleanup_interval
        self._idle = idle
        self._monotonic = monotonic
        self._last_purge = -math.inf

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._purge_if_due()
            try:
                published = await self._relay_round()
            except Exception:
                logger.exception("relay round failed")
                published = 0
            if published < self._batch_size:
                await self._idle(self._poll_interval)

    async def _purge_if_due(self) -> None:
        now = self._monotonic()
        if now - self._last_purge < self._cleanup_interval:
            return
        self._last_purge = now
        try:
            await self._purge()
        except Exception:
            logger.exception("outbox purge failed")


async def connect_until_ready(
    broker: RabbitBroker, stop: asyncio.Event, interval: float
) -> bool:
    """Keep trying to connect. Payments keep accumulating in the outbox meanwhile."""
    while not stop.is_set():
        try:
            await broker.connect()
        except Exception as exc:  # noqa: BLE001 - any failure means "try again later"
            logger.warning("broker unavailable, retrying", extra={"error": repr(exc)})
            await sleep_unless_stopped(stop, interval)
        else:
            return True
    return False


async def serve(settings: Settings) -> None:
    stop = asyncio.Event()
    install_stop_signals(stop)

    engine = create_engine(settings.database_url, pool_size=2)
    sessions = create_session_factory(engine)
    broker = RabbitBroker(
        settings.rabbitmq_url,
        default_channel=Channel(publisher_confirms=True, on_return_raises=True),
        logger=None,
    )
    clock = SystemClock()
    publisher = RabbitEventPublisher(broker)

    async def relay_round() -> int:
        async with sessions() as session:
            return await RelayOutbox(
                outbox=SqlOutboxRepository(session),
                publisher=publisher,
                transaction=session,
                clock=clock,
            ).run_once(batch_size=settings.relay_batch_size)

    async def purge() -> int:
        async with sessions() as session:
            return await RelayOutbox(
                outbox=SqlOutboxRepository(session),
                publisher=publisher,
                transaction=session,
                clock=clock,
            ).purge(retention=timedelta(days=settings.outbox_retention_days))

    try:
        if await connect_until_ready(
            broker, stop, settings.relay_poll_interval_seconds * 4
        ):
            policy = RetryPolicy(
                max_retries=settings.max_retries,
                base_delay_seconds=settings.retry_base_delay_seconds,
                backoff_factor=settings.retry_backoff_factor,
            )
            await declare_topology(broker, policy)
            logger.info(
                "relay started", extra={"batch_size": settings.relay_batch_size}
            )
            heartbeat = asyncio.create_task(
                beat_forever(DEFAULT_PATH, partial(broker.ping, timeout=2.0))
            )
            await RelayWorker(
                relay_round=relay_round,
                purge=purge,
                batch_size=settings.relay_batch_size,
                poll_interval=settings.relay_poll_interval_seconds,
                cleanup_interval=settings.outbox_cleanup_interval_seconds,
                idle=partial(sleep_unless_stopped, stop),
            ).run(stop)
            heartbeat.cancel()
    finally:
        await broker.stop()
        await engine.dispose()
        logger.info("relay stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(serve(settings))


if __name__ == "__main__":
    main()

"""Payments consumer: ``python -m outbox_payments.entrypoints.consumer``.

Exactly one replica runs in compose (see docs/ARCHITECTURE.md for why and for what
changes when scaling out). The handler never lets an exception escape for a known
failure: it republishes the message to a retry queue or the DLQ and then acks.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Annotated

from faststream import AckPolicy, Depends, FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage
from faststream.rabbit.schemas import Channel
from pydantic import ValidationError

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.db.repositories import SqlPaymentRepository
from outbox_payments.adapters.db.session import create_engine, create_session_factory
from outbox_payments.adapters.messaging.failures import FailureRouter
from outbox_payments.adapters.messaging.retry import RetryPolicy
from outbox_payments.adapters.messaging.schemas import PaymentCreatedMessage
from outbox_payments.adapters.messaging.topology import (
    PAYMENTS_EXCHANGE,
    declare_topology,
    payments_queue,
)
from outbox_payments.adapters.payment_provider.emulated import EmulatedPaymentProvider
from outbox_payments.adapters.webhooks.httpx_sender import (
    HttpxWebhookSender,
    create_webhook_client,
)
from outbox_payments.application.errors import PaymentNotFoundError, PermanentError
from outbox_payments.application.ports import Clock
from outbox_payments.application.use_cases.process_payment import ProcessPayment
from outbox_payments.config import Settings, get_settings
from outbox_payments.domain import DomainError
from outbox_payments.entrypoints.heartbeat import DEFAULT_PATH, beat_forever
from outbox_payments.entrypoints.logs import configure_logging

logger = logging.getLogger(__name__)

type ProcessPaymentFactory = Callable[[], AbstractAsyncContextManager[ProcessPayment]]


class MalformedMessageError(PermanentError):
    """The body is not a valid ``payment.created`` event; no retry can fix it."""


def is_permanent(error: BaseException) -> bool:
    """Retrying cannot help: bad input, unknown payment, receiver said no.

    Everything else (webhook 5xx/408/429/timeouts, database or broker outages, and
    errors we did not foresee) is retried; MAX_RETRIES bounds the cost of being wrong.
    """
    return isinstance(error, PermanentError | PaymentNotFoundError | DomainError)


@dataclass(frozen=True)
class ConsumerResources:
    process_payment: ProcessPaymentFactory
    policy: RetryPolicy
    clock: Clock


def create_broker(
    url: str, resources: ConsumerResources, *, prefetch_count: int
) -> RabbitBroker:
    broker = RabbitBroker(
        url,
        default_channel=Channel(
            prefetch_count=prefetch_count,
            publisher_confirms=True,
            on_return_raises=True,
        ),
        graceful_timeout=30,  # > max processing time (5 s gateway + 5 s webhook)
        logger=None,
    )
    failures = FailureRouter(broker, resources.policy)

    def provide_process_payment() -> ProcessPaymentFactory:
        return resources.process_payment

    @broker.subscriber(
        payments_queue(), PAYMENTS_EXCHANGE, ack_policy=AckPolicy.NACK_ON_ERROR
    )
    async def on_payment_created(  # pyright: ignore[reportUnusedFunction]
        message: RabbitMessage,
        process_payment: Annotated[
            ProcessPaymentFactory, Depends(provide_process_payment)
        ],
    ) -> None:
        # Returning normally acks. If routing a failure itself fails (broker trouble),
        # the exception nacks with requeue, so the message is never lost.
        try:
            event = _parse(message)
            # One session per message, opened inside the try: a database outage is
            # routed to a retry queue like any other transient failure.
            async with process_payment() as use_case:
                await use_case.execute(
                    payment_id=event.payment_id, event_id=event.event_id
                )
        except Exception as exc:  # noqa: BLE001 - every failure is routed, see is_permanent
            await failures.route(
                message, exc, permanent=is_permanent(exc), now=resources.clock.now()
            )

    return broker


def _parse(message: RabbitMessage) -> PaymentCreatedMessage:
    try:
        return PaymentCreatedMessage.model_validate_json(message.body)
    except ValidationError as exc:
        raise MalformedMessageError(str(exc)) from exc


def create_app(settings: Settings) -> FastStream:
    engine = create_engine(settings.database_url, pool_size=2)
    sessions = create_session_factory(engine)
    webhook_client = create_webhook_client(settings.webhook_timeout_seconds)
    provider = EmulatedPaymentProvider(
        min_delay=settings.payment_min_delay_seconds,
        max_delay=settings.payment_max_delay_seconds,
        success_rate=settings.payment_success_rate,
    )
    webhooks = HttpxWebhookSender(webhook_client)
    clock = SystemClock()
    policy = RetryPolicy(
        max_retries=settings.max_retries,
        base_delay_seconds=settings.retry_base_delay_seconds,
        backoff_factor=settings.retry_backoff_factor,
    )

    @asynccontextmanager
    async def process_payment() -> AsyncGenerator[ProcessPayment]:
        async with sessions() as session:
            yield ProcessPayment(
                payments=SqlPaymentRepository(session),
                provider=provider,
                webhooks=webhooks,
                transaction=session,
                clock=clock,
            )

    broker = create_broker(
        settings.rabbitmq_url,
        ConsumerResources(process_payment=process_payment, policy=policy, clock=clock),
        prefetch_count=settings.consumer_prefetch_count,
    )

    # Topology must exist before the subscriber starts consuming.
    async def declare() -> None:
        await broker.connect()
        await declare_topology(broker, policy)
        logger.info("topology declared", extra={"max_retries": policy.max_retries})

    heartbeat: list[asyncio.Task[None]] = []

    async def start_heartbeat() -> None:
        heartbeat.append(
            asyncio.create_task(
                beat_forever(DEFAULT_PATH, partial(broker.ping, timeout=2.0))
            )
        )

    async def stop_heartbeat() -> None:
        for task in heartbeat:
            task.cancel()

    async def close() -> None:
        await webhook_client.aclose()
        await engine.dispose()
        logger.info("consumer stopped")

    # FastStream handles SIGTERM/SIGINT: it stops consuming, waits up to
    # graceful_timeout for in-flight messages, then runs on_shutdown/after_shutdown.
    return FastStream(
        broker,
        on_startup=[declare],
        after_startup=[start_heartbeat],
        on_shutdown=[stop_heartbeat],
        after_shutdown=[close],
        logger=None,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(create_app(settings).run())


if __name__ == "__main__":
    main()

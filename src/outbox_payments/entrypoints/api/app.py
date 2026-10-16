"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI

from outbox_payments.adapters.clock import SystemClock
from outbox_payments.adapters.db.health import database_is_reachable
from outbox_payments.adapters.db.session import create_engine, create_session_factory
from outbox_payments.adapters.messaging.health import broker_is_reachable
from outbox_payments.config import Settings, get_settings
from outbox_payments.entrypoints.api.deps import ApiState
from outbox_payments.entrypoints.api.problems import install_problem_handlers
from outbox_payments.entrypoints.api.routers import health, payments
from outbox_payments.entrypoints.logs import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    state = ApiState(settings=settings, clock=SystemClock())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        engine = create_engine(settings.database_url, pool_size=settings.database_pool_size)
        state.session_factory = create_session_factory(engine)
        state.readiness_probes = {
            "database": partial(database_is_reachable, engine),
            "broker": partial(broker_is_reachable, settings.rabbitmq_url),
        }
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="outbox-payments",
        version="0.1.0",
        summary="Asynchronous payment processing with a transactional outbox.",
        lifespan=lifespan,
    )
    app.state.api = state
    install_problem_handlers(app)
    app.include_router(payments.router)
    app.include_router(health.router)
    return app


def main() -> FastAPI:
    """``uvicorn --factory outbox_payments.entrypoints.api.app:main``"""
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)

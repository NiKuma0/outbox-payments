"""Composition root of the API process: wiring via ``Depends`` and ``app.state``.

Long-lived resources (engine, session factory, probes) live in ``ApiState`` on
``app.state``; per-request objects (one ``AsyncSession``, the use cases using it) are
built by dependencies. Tests swap any of them with ``app.dependency_overrides``.
"""

import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, cast

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from outbox_payments.adapters.db.repositories import (
    SqlOutboxRepository,
    SqlPaymentRepository,
)
from outbox_payments.application.ports import Clock
from outbox_payments.application.use_cases.create_payment import CreatePayment
from outbox_payments.application.use_cases.get_payment import GetPayment
from outbox_payments.config import Settings
from outbox_payments.entrypoints.api.problems import ProblemError

type Probe = Callable[[], Awaitable[bool]]

IDEMPOTENCY_KEY = re.compile(r"[\x21-\x7e]{1,255}")  # printable ASCII, no spaces


@dataclass
class ApiState:
    settings: Settings
    clock: Clock
    session_factory: async_sessionmaker[AsyncSession] | None = None
    readiness_probes: dict[str, Probe] = field(default_factory=dict[str, Probe])


def get_state(request: Request) -> ApiState:
    return cast("ApiState", request.app.state.api)


StateDep = Annotated[ApiState, Depends(get_state)]


async def get_session(state: StateDep) -> AsyncIterator[AsyncSession]:
    if state.session_factory is None:
        raise RuntimeError("database is not initialised; is the lifespan running?")
    # Closing the session rolls back anything uncommitted. Committing is the use
    # case's job: committing here, after the response is built, could send a 202
    # for a payment that then fails to commit.
    async with state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_create_payment(session: SessionDep, state: StateDep) -> CreatePayment:
    return CreatePayment(
        payments=SqlPaymentRepository(session),
        outbox=SqlOutboxRepository(session),
        transaction=session,
        clock=state.clock,
    )


def get_get_payment(session: SessionDep) -> GetPayment:
    return GetPayment(payments=SqlPaymentRepository(session))


def get_readiness_probes(state: StateDep) -> Mapping[str, Probe]:
    return state.readiness_probes


async def require_api_key(
    state: StateDep,
    x_api_key: Annotated[str | None, Depends(APIKeyHeader(name="X-API-Key"))] = None,
) -> None:
    expected = state.settings.api_key.get_secret_value().encode()
    # compare_digest: the comparison time does not depend on how many bytes match.
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected):
        raise ProblemError(
            401, "Missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"}
        )


async def idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if key is None:
        raise ProblemError(
            400,
            "Idempotency-Key header is required",
            problem_type="/problems/idempotency-key-missing",
        )
    if not IDEMPOTENCY_KEY.fullmatch(key):
        raise ProblemError(
            400,
            "Invalid Idempotency-Key header",
            detail="Use 1-255 printable ASCII characters without spaces, e.g. a UUID.",
            problem_type="/problems/idempotency-key-invalid",
        )
    return key

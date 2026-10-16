"""Black-box tests against the compose stack (`make test-e2e` starts it)."""

import asyncio
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient

API_URL = os.environ.get("E2E_API_URL", "http://localhost:8000")
SINK_URL = os.environ.get("E2E_SINK_URL", "http://localhost:8080")
RABBITMQ_API_URL = os.environ.get("E2E_RABBITMQ_API_URL", "http://localhost:15672/api")
API_KEY = os.environ.get("E2E_API_KEY", "dev-api-key")


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(base_url=API_URL, headers={"X-API-Key": API_KEY}, timeout=10) as c:
        yield c


@pytest.fixture
async def sink() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(base_url=SINK_URL, timeout=10) as client:
        yield client


@pytest.fixture
async def rabbitmq() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(base_url=RABBITMQ_API_URL, auth=("guest", "guest"), timeout=10) as c:
        yield c


async def eventually[T](
    probe: Callable[[], Awaitable[T | None]], *, within: float, every: float = 0.5
) -> T:
    """Poll ``probe`` until it returns something truthy or ``within`` seconds pass."""
    deadline = time.monotonic() + within
    while True:
        if result := await probe():
            return result
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {within}s")
        await asyncio.sleep(every)

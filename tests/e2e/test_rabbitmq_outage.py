"""RabbitMQ outage: the API keeps accepting payments and the outbox catches up.

The broker is stopped and started by `make test-e2e`, not from here: it runs this
module twice, with ``E2E_OUTAGE_PHASE=down`` while RabbitMQ is stopped and with
``E2E_OUTAGE_PHASE=recovered`` after it is back. The payment created in the first
phase is handed to the second through the pytest cache. Without the variable (a bare
`pytest`) both tests are skipped.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.e2e.conftest import create, deliveries, eventually, new_key

pytestmark = pytest.mark.anyio

PHASE = os.environ.get("E2E_OUTAGE_PHASE")


def payment_file(cache: pytest.Cache) -> Path:
    return cache.mkdir("e2e-rabbitmq-outage") / "payment-id"


def only_in(phase: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        PHASE != phase, reason=f"outage phase {phase!r} is driven by `make test-e2e`"
    )


@only_in("down")
async def test_api_accepts_payments_while_rabbitmq_is_down(
    api: AsyncClient, sink: AsyncClient, cache: pytest.Cache
) -> None:
    payment_file(cache).unlink(missing_ok=True)

    accepted = await create(api, new_key())
    payment_id = accepted["payment_id"]
    await asyncio.sleep(2)  # give the relay a chance to (wrongly) get it through

    payment = (await api.get(f"/api/v1/payments/{payment_id}")).json()
    assert payment["status"] == "pending"
    assert await deliveries(sink, payment_id) == []
    payment_file(cache).write_text(payment_id)


@only_in("recovered")
async def test_outbox_catches_up_once_rabbitmq_is_back(
    sink: AsyncClient, cache: pytest.Cache
) -> None:
    file = payment_file(cache)
    assert file.exists(), "the 'down' phase did not record a payment"
    payment_id = file.read_text()

    async def delivered() -> list[dict[str, Any]] | None:
        return await deliveries(sink, payment_id) or None

    await eventually(delivered, within=90, every=1)

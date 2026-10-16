import asyncio
import json
import subprocess
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.cases.api.create_payment import VALID_BODY
from tests.e2e.conftest import eventually

pytestmark = pytest.mark.anyio

FINAL = {"succeeded", "failed"}


def new_key() -> str:
    return f"e2e-{uuid4()}"


async def create(api: AsyncClient, key: str, **overrides: object) -> dict[str, Any]:
    response = await api.post(
        "/api/v1/payments",
        json={**VALID_BODY, **overrides},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def deliveries(sink: AsyncClient, payment_id: str) -> list[dict[str, Any]]:
    response = await sink.get("/received", params={"payment_id": payment_id})
    return response.json()


async def test_created_payment_is_processed_and_webhook_reaches_the_sink(
    api: AsyncClient, sink: AsyncClient
) -> None:
    accepted = await create(api, new_key())
    payment_id = accepted["payment_id"]
    assert accepted["status"] == "pending"

    async def delivered() -> list[dict[str, Any]] | None:
        received = await deliveries(sink, payment_id)
        return [r for r in received if r["answered"] == 200] or None

    [webhook] = await eventually(delivered, within=30)
    payment = (await api.get(f"/api/v1/payments/{payment_id}")).json()

    assert payment["status"] in FINAL
    assert payment["processed_at"] is not None
    assert webhook["payload"]["status"] == payment["status"]
    assert webhook["payload"]["amount"] == "100.00"
    assert webhook["webhook_id"]  # X-Webhook-Id = event id


async def test_repeating_the_request_returns_the_same_payment(api: AsyncClient) -> None:
    key = new_key()
    first = await create(api, key)

    second = await create(api, key)
    conflict = await api.post(
        "/api/v1/payments",
        json={**VALID_BODY, "amount": "999.00"},
        headers={"Idempotency-Key": key},
    )

    assert second["payment_id"] == first["payment_id"]
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


async def test_failing_receiver_is_retried_three_times_then_dead_lettered(
    api: AsyncClient, sink: AsyncClient, rabbitmq: AsyncClient
) -> None:
    accepted = await create(api, new_key(), webhook_url="http://webhook-sink:8080/fail")
    payment_id = accepted["payment_id"]

    async def dead_lettered() -> dict[str, Any] | None:
        response = await rabbitmq.post(
            "/queues/%2F/payments.new.dlq/get",
            json={"count": 1000, "ackmode": "ack_requeue_true", "encoding": "auto"},
        )
        for message in response.json():
            if json.loads(message["payload"])["payment_id"] == payment_id:
                return message
        return None

    # 2-5 s gateway + 1 s + 4 s + 16 s of retry delays, plus webhook round trips.
    message = await eventually(dead_lettered, within=60, every=1)

    headers = message["properties"]["headers"]
    assert headers["x-retry-count"] == 3
    assert "500" in headers["x-last-error"]
    assert headers["x-failed-at"]
    received = await deliveries(sink, payment_id)
    assert len(received) == 4  # first delivery + 3 retries
    assert len({r["webhook_id"] for r in received}) == 1  # same X-Webhook-Id every time
    payment = (await api.get(f"/api/v1/payments/{payment_id}")).json()
    assert (
        payment["status"] in FINAL
    )  # the charge itself was committed before the webhook


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


async def test_api_keeps_accepting_while_rabbitmq_is_down_and_outbox_catches_up(
    api: AsyncClient, sink: AsyncClient
) -> None:
    await asyncio.to_thread(compose, "stop", "rabbitmq")
    try:
        accepted = await create(api, new_key())
        payment_id = accepted["payment_id"]
        await asyncio.sleep(2)
        still_pending = (await api.get(f"/api/v1/payments/{payment_id}")).json()
        assert still_pending["status"] == "pending"
        assert await deliveries(sink, payment_id) == []
    finally:
        # `start` returns before the broker accepts connections; wait for the healthcheck
        # so tests that run after this one do not hit a half-booted RabbitMQ.
        await asyncio.to_thread(compose, "up", "-d", "--wait", "rabbitmq")

    async def delivered() -> list[dict[str, Any]] | None:
        return await deliveries(sink, payment_id) or None

    await eventually(delivered, within=90, every=1)

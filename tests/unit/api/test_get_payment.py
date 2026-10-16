import pytest
from httpx import AsyncClient

from tests.cases.api.create_payment import FIRST_KEY, VALID_BODY

pytestmark = pytest.mark.anyio


async def test_returns_full_payment_details(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/payments", json=VALID_BODY, headers={"Idempotency-Key": FIRST_KEY}
    )
    payment_id = created.json()["payment_id"]

    response = await client.get(f"/api/v1/payments/{payment_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": payment_id,
        "amount": "100.00",
        "currency": "RUB",
        "description": "Order #42",
        "metadata": {"order_id": 42},
        "status": "pending",
        "idempotency_key": FIRST_KEY,
        "webhook_url": "http://webhook-sink:8080/hook",
        "created_at": created.json()["created_at"],
        "processed_at": None,
    }


async def test_unknown_payment_is_a_problem_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/payments/0199f1a2-7c3e-7d4b-9a10-2b3c4d5e6f70")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Payment not found"


async def test_malformed_payment_id_is_a_validation_problem(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/payments/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "payment_id"

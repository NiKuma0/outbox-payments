import pytest
from httpx import AsyncClient

from tests.cases._helpers import as_params
from tests.cases.api.create_payment import (
    CREATE_PAYMENT_VALIDATION_CASES,
    FIRST_KEY,
    HTTP_IDEMPOTENCY_CASES,
    IDEMPOTENCY_KEY_HEADER_CASES,
    VALID_BODY,
    CreatePaymentValidationCase,
    HttpIdempotencyCase,
    IdempotencyKeyHeaderCase,
)
from tests.fakes.store import InMemoryStore

pytestmark = pytest.mark.anyio

URL = "/api/v1/payments"
PROBLEM_JSON = "application/problem+json"


def body_with(
    overrides: dict[str, object], removed: list[str] | None = None
) -> dict[str, object]:
    body = {**VALID_BODY, **overrides}
    for field in removed or []:
        del body[field]
    return body


@pytest.mark.parametrize("case", as_params(CREATE_PAYMENT_VALIDATION_CASES))
async def test_create_payment_validation(
    case: CreatePaymentValidationCase, client: AsyncClient
) -> None:
    response = await client.post(
        URL,
        json=body_with(case["overrides"], case.get("removed_fields")),
        headers={"Idempotency-Key": FIRST_KEY},
    )

    assert response.status_code == case["expected_status"], response.text
    if "expected_error_field" in case:
        assert response.headers["content-type"] == PROBLEM_JSON
        problem = response.json()
        assert problem["status"] == 422
        assert case["expected_error_field"] in {
            error["field"] for error in problem["errors"]
        }


async def test_accepted_payment_response(
    client: AsyncClient, store: InMemoryStore
) -> None:
    response = await client.post(
        URL, json=VALID_BODY, headers={"Idempotency-Key": FIRST_KEY}
    )

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"payment_id", "status", "created_at"}
    assert body["status"] == "pending"
    assert response.headers["location"] == f"{URL}/{body['payment_id']}"
    assert [str(p) for p in store.payments] == [body["payment_id"]]
    assert len(store.outbox) == 1


@pytest.mark.parametrize("case", as_params(IDEMPOTENCY_KEY_HEADER_CASES))
async def test_idempotency_key_header(
    case: IdempotencyKeyHeaderCase, client: AsyncClient
) -> None:
    response = await client.post(URL, json=VALID_BODY, headers=case["headers"])

    assert response.status_code == case["expected_status"], response.text
    if case["expected_status"] == 400:
        assert response.headers["content-type"] == PROBLEM_JSON


@pytest.mark.parametrize("case", as_params(HTTP_IDEMPOTENCY_CASES))
async def test_idempotent_create(
    case: HttpIdempotencyCase, client: AsyncClient
) -> None:
    first = await client.post(
        URL, json=VALID_BODY, headers={"Idempotency-Key": FIRST_KEY}
    )

    second = await client.post(
        URL,
        json=body_with(case["second_overrides"]),
        headers={"Idempotency-Key": case["second_key"]},
    )

    assert second.status_code == case["expected_status"], second.text
    if case["expected_status"] == 409:
        assert second.headers["content-type"] == PROBLEM_JSON
        assert second.json()["status"] == 409
    else:
        same = second.json()["payment_id"] == first.json()["payment_id"]
        assert same is case["expected_same_payment"]

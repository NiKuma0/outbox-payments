from unittest.mock import Mock

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
    client: AsyncClient, payments: Mock, outbox: Mock, transaction: Mock
) -> None:
    response = await client.post(
        URL, json=VALID_BODY, headers={"Idempotency-Key": FIRST_KEY}
    )

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"payment_id", "status", "created_at"}
    assert body["status"] == "pending"
    assert response.headers["location"] == f"{URL}/{body['payment_id']}"
    stored = payments.add_if_absent.await_args.args[0]
    assert str(stored.id) == body["payment_id"]
    outbox.add.assert_awaited_once()
    transaction.commit.assert_awaited_once()


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
    case: HttpIdempotencyCase, client: AsyncClient, payments: Mock
) -> None:
    first = await client.post(
        URL, json=VALID_BODY, headers={"Idempotency-Key": FIRST_KEY}
    )
    # The unique index on the key decides; answer the way Postgres would.
    payments.add_if_absent.return_value = case["second_key"] != FIRST_KEY
    payments.get_by_idempotency_key.return_value = (
        payments.add_if_absent.await_args.args[0]
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

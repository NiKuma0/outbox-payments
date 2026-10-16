import pytest
from httpx import AsyncClient

from tests.cases._helpers import as_params
from tests.cases.api.auth import AUTH_CASES, AuthCase
from tests.cases.api.create_payment import VALID_BODY

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("case", as_params(AUTH_CASES))
async def test_api_key_is_required_on_business_endpoints(
    case: AuthCase, client: AsyncClient
) -> None:
    client.headers.pop("X-API-Key")

    response = await client.request(
        case["method"],
        case["path"],
        headers=case["headers"],
        json=VALID_BODY if case["method"] == "POST" else None,
    )

    assert response.status_code == case["expected_status"], response.text
    if case["expected_status"] == 401:
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["www-authenticate"] == "ApiKey"

import pytest
from httpx import AsyncClient

from tests.cases._helpers import as_params
from tests.cases.api.health import READINESS_CASES, ReadinessCase
from tests.unit.api.conftest import ProbeSwitch

pytestmark = pytest.mark.anyio


async def test_liveness_does_not_touch_dependencies(
    client: AsyncClient, probes: ProbeSwitch
) -> None:
    probes.database_up = probes.broker_up = False

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("case", as_params(READINESS_CASES))
async def test_readiness(case: ReadinessCase, client: AsyncClient, probes: ProbeSwitch) -> None:
    probes.database_up, probes.broker_up = case["database_up"], case["broker_up"]

    response = await client.get("/ready")

    assert response.status_code == case["expected_status"]
    assert response.json() == case["expected_body"]

import pytest
from httpx import ASGITransport, AsyncClient

from tests.cases._helpers import as_params
from tests.cases.tools.webhook_sink import SINK_FAILURE_CASES, SinkFailureCase
from tools.webhook_sink.app import create_app

pytestmark = pytest.mark.anyio


async def sink(monkeypatch: pytest.MonkeyPatch, *, fail: bool) -> AsyncClient:
    monkeypatch.setenv("WEBHOOK_SINK_FAIL", "true" if fail else "")
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://sink")


async def test_records_webhooks_and_answers_200(monkeypatch: pytest.MonkeyPatch) -> None:
    async with await sink(monkeypatch, fail=False) as client:
        answer = await client.post(
            "/hook", json={"payment_id": "p1"}, headers={"X-Webhook-Id": "e1"}
        )
        await client.post("/hook", json={"payment_id": "p2"})
        received = (await client.get("/received", params={"payment_id": "p1"})).json()

    assert answer.status_code == 200
    assert [(r["webhook_id"], r["answered"]) for r in received] == [("e1", 200)]


@pytest.mark.parametrize("case", as_params(SINK_FAILURE_CASES))
async def test_failure_modes(monkeypatch: pytest.MonkeyPatch, case: SinkFailureCase) -> None:
    async with await sink(monkeypatch, fail=case["fail_flag"]) as client:
        answer = await client.post(case["path"], json={"payment_id": "p1"})

    assert answer.status_code == case["expected_status"]

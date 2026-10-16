import pytest

from outbox_payments.application.webhooks import classify_webhook_status
from tests.cases._helpers import as_params
from tests.cases.application.webhooks import WEBHOOK_STATUS_CASES, WebhookStatusCase


@pytest.mark.parametrize("case", as_params(WEBHOOK_STATUS_CASES))
def test_webhook_status_classification(case: WebhookStatusCase) -> None:
    assert classify_webhook_status(case["status_code"]) == case["expected"]

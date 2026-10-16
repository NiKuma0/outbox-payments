import pytest

from outbox_payments.adapters.messaging.retry import DeadLetter, Retry, RetryPolicy
from tests.cases._helpers import as_params
from tests.cases.adapters.messaging.retry import RETRY_DECISION_CASES, RetryDecisionCase


@pytest.mark.parametrize("case", as_params(RETRY_DECISION_CASES))
def test_retry_decision(case: RetryDecisionCase) -> None:
    policy = RetryPolicy(
        max_retries=case["max_retries"], base_delay_seconds=1, backoff_factor=4
    )

    decision = policy.after_failure(retries_so_far=case["retries_so_far"])

    assert decision.queue == case["expected_queue"]
    if "expected_delay_seconds" in case:
        assert isinstance(decision, Retry)
        assert decision.delay_seconds == case["expected_delay_seconds"]
        assert decision.retry_number == case["retries_so_far"] + 1
    else:
        assert isinstance(decision, DeadLetter)


def test_one_retry_queue_per_delay_level() -> None:
    policy = RetryPolicy(max_retries=3, base_delay_seconds=1, backoff_factor=4)

    assert [(level.queue, level.delay_seconds) for level in policy.levels] == [
        ("payments.new.retry.1", 1.0),
        ("payments.new.retry.2", 4.0),
        ("payments.new.retry.3", 16.0),
    ]

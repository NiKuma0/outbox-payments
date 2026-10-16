import logging

import pytest

from outbox_payments.entrypoints.logs import KeyValueFormatter
from tests.cases._helpers import as_params
from tests.cases.entrypoints.logs import LOG_LINE_CASES, LogLineCase


def render(message: str, extra: dict[str, object]) -> str:
    record = logging.LogRecord(
        "payments", logging.INFO, __file__, 1, message, None, None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return KeyValueFormatter().format(record)


@pytest.mark.parametrize("case", as_params(LOG_LINE_CASES))
def test_key_value_format(case: LogLineCase) -> None:
    line = render(case["message"], case["extra"])

    assert line.startswith("ts=")
    assert " level=INFO logger=payments " in line
    assert case["expected_fragment"] in line

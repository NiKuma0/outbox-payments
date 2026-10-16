from typing import TypedDict


class LogLineCase(TypedDict):
    id: str
    message: str
    extra: dict[str, object]
    expected_fragment: str


LOG_LINE_CASES: list[LogLineCase] = [
    {
        "id": "plain-message-is-quoted",
        "message": "payment accepted",
        "extra": {},
        "expected_fragment": 'msg="payment accepted"',
    },
    {
        "id": "context-fields-become-key-value-pairs",
        "message": "webhook delivered",
        "extra": {"payment_id": "p-1", "event_id": "e-1"},
        "expected_fragment": 'msg="webhook delivered" payment_id=p-1 event_id=e-1',
    },
    {
        "id": "values-with-spaces-are-quoted",
        "message": "publish failed",
        "extra": {"error": "connection refused"},
        "expected_fragment": 'error="connection refused"',
    },
    {
        "id": "numbers-are-left-bare",
        "message": "outbox purged",
        "extra": {"deleted": 3},
        "expected_fragment": "deleted=3",
    },
]

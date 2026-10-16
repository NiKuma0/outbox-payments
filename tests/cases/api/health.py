from typing import TypedDict


class ReadinessCase(TypedDict):
    id: str
    database_up: bool
    broker_up: bool
    expected_status: int
    expected_body: dict[str, object]


READINESS_CASES: list[ReadinessCase] = [
    {
        "id": "everything-up-means-ready",
        "database_up": True,
        "broker_up": True,
        "expected_status": 200,
        "expected_body": {"status": "ready", "checks": {"database": "ok", "broker": "ok"}},
    },
    {
        "id": "database-down-means-not-ready",
        "database_up": False,
        "broker_up": True,
        "expected_status": 503,
        "expected_body": {
            "status": "not_ready",
            "checks": {"database": "unavailable", "broker": "ok"},
        },
    },
    {
        "id": "broker-down-means-not-ready",
        "database_up": True,
        "broker_up": False,
        "expected_status": 503,
        "expected_body": {
            "status": "not_ready",
            "checks": {"database": "ok", "broker": "unavailable"},
        },
    },
]

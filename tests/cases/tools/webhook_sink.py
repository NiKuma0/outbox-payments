from typing import TypedDict


class SinkFailureCase(TypedDict):
    id: str
    fail_flag: bool
    path: str
    expected_status: int


SINK_FAILURE_CASES: list[SinkFailureCase] = [
    {
        "id": "hook-answers-200-by-default",
        "fail_flag": False,
        "path": "/hook",
        "expected_status": 200,
    },
    {
        "id": "fail-flag-makes-hook-answer-500",
        "fail_flag": True,
        "path": "/hook",
        "expected_status": 500,
    },
    {
        "id": "fail-path-always-answers-500",
        "fail_flag": False,
        "path": "/fail",
        "expected_status": 500,
    },
]

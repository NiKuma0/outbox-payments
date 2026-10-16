from typing import TypedDict

from tests.cases._helpers import as_params


class _Case(TypedDict):
    id: str
    value: int


def test_as_params_uses_case_id_as_pytest_id() -> None:
    cases: list[_Case] = [
        {"id": "first-case", "value": 1},
        {"id": "second-case", "value": 2},
    ]

    params = as_params(cases)

    assert [p.id for p in params] == ["first-case", "second-case"]
    assert [p.values for p in params] == [(cases[0],), (cases[1],)]

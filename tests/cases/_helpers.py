"""The only module under ``tests/cases`` that may contain code.

Case modules are pure data; this helper is the single bridge between a list of case
dicts and ``pytest.mark.parametrize``.
"""

from collections.abc import Iterable, Mapping

import pytest
from _pytest.mark.structures import ParameterSet  # pytest exposes no public alias


def as_params[C: Mapping[str, object]](cases: Iterable[C]) -> list[ParameterSet]:
    """Wrap each case so its ``"id"`` becomes the pytest test id."""
    return [pytest.param(case, id=str(case["id"])) for case in cases]

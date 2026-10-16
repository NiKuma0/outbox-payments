"""Enforce the dependency rule by parsing imports with ``ast``."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.cases._helpers import as_params
from tests.cases.architecture import LAYER_RULE_CASES, LayerRuleCase

PACKAGE = "outbox_payments"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / PACKAGE


def imported_modules(path: Path) -> Iterator[str]:
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def violations(case: LayerRuleCase) -> list[str]:
    layer_root = PACKAGE_ROOT / case["layer"]
    found: list[str] = []
    for path in sorted(layer_root.rglob("*.py")):
        for module in imported_modules(path):
            top, _, rest = module.partition(".")
            inner = rest.partition(".")[0]
            if (top == PACKAGE and inner in case["forbidden_internal"]) or (
                top in case["forbidden_external"]
            ):
                found.append(f"{path.relative_to(PACKAGE_ROOT)} imports {module}")
    return found


def test_layers_exist() -> None:
    for case in LAYER_RULE_CASES:
        assert (PACKAGE_ROOT / case["layer"]).is_dir(), case["layer"]


@pytest.mark.parametrize("case", as_params(LAYER_RULE_CASES))
def test_dependencies_point_inward(case: LayerRuleCase) -> None:
    assert violations(case) == []


def test_checker_detects_a_violation(tmp_path: Path) -> None:
    offending = tmp_path / "bad.py"
    offending.write_text(
        "from outbox_payments.adapters.db import models\nimport sqlalchemy\n"
    )

    modules = list(imported_modules(offending))

    assert modules == ["outbox_payments.adapters.db", "sqlalchemy"]

"""Meta-tests that keep ``tests/cases`` honest.

* every case id is unique across the whole suite and is kebab-case,
* case modules are data only (no functions, no I/O, restricted imports),
* the cases tree mirrors the test tree.
"""

import ast
import importlib
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = TESTS_ROOT / "cases"
LEVELS = ("unit", "integration", "e2e", "contract")
KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_IMPORT_PREFIXES = ("typing", "decimal", "outbox_payments.domain", "tests.cases")
ALLOWED_CALLS = frozenset({"Decimal"})


def case_module_paths() -> list[Path]:
    return sorted(
        path
        for path in CASES_ROOT.rglob("*.py")
        if not path.name.startswith("_") and path.name != "__init__.py"
    )


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(TESTS_ROOT.parent).with_suffix("").parts)


def iter_case_ids(module_path: Path) -> Iterator[str]:
    module = importlib.import_module(module_name(module_path))
    for value in vars(module).values():
        if isinstance(value, list):
            for item in value:  # pyright: ignore[reportUnknownVariableType]
                if isinstance(item, dict) and "id" in item:
                    yield str(item["id"])  # pyright: ignore[reportUnknownArgumentType]


def purity_violations(source: str) -> list[str]:
    """Return human-readable reasons why ``source`` is not a pure data module."""
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.Lambda():
                violations.append(f"line {node.lineno}: functions are not allowed")
            case ast.Import(names=names):
                violations.extend(
                    f"line {node.lineno}: import of {alias.name!r} is not allowed"
                    for alias in names
                    if not alias.name.startswith(ALLOWED_IMPORT_PREFIXES)
                )
            case ast.ImportFrom(module=module) if not (module or "").startswith(
                ALLOWED_IMPORT_PREFIXES
            ):
                violations.append(f"line {node.lineno}: import from {module!r} is not allowed")
            case ast.Call(func=ast.Name(id=name)) if name in ALLOWED_CALLS:
                pass
            case ast.Call():
                violations.append(f"line {node.lineno}: calls other than Decimal() are not allowed")
            case ast.ClassDef(body=body) if not all(
                isinstance(stmt, ast.AnnAssign | ast.Expr | ast.Pass) for stmt in body
            ):
                violations.append(f"line {node.lineno}: classes may only declare TypedDict fields")
            case _:
                pass
    return violations


@pytest.mark.parametrize(
    ("source", "expected_violations"),
    [
        pytest.param("X: list[int] = [1, 2]", 0, id="plain-literals-are-pure"),
        pytest.param("from decimal import Decimal\nX = Decimal('1')", 0, id="decimal-is-pure"),
        pytest.param("def f() -> None: ...", 1, id="function-is-impure"),
        pytest.param("import os", 1, id="stdlib-io-import-is-impure"),
        pytest.param("X = open('f')", 1, id="arbitrary-call-is-impure"),
        pytest.param("class C:\n    def m(self): ...", 2, id="class-with-method-is-impure"),
    ],
)
def test_purity_checker(source: str, expected_violations: int) -> None:
    assert len(purity_violations(source)) == expected_violations


def test_case_ids_are_unique_and_kebab_case() -> None:
    ids = [case_id for path in case_module_paths() for case_id in iter_case_ids(path)]

    duplicates = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    not_kebab = sorted(case_id for case_id in ids if not KEBAB_CASE.fullmatch(case_id))

    assert duplicates == []
    assert not_kebab == []


def test_case_modules_are_pure_data() -> None:
    report = {
        str(path.relative_to(CASES_ROOT)): violations
        for path in case_module_paths()
        if (violations := purity_violations(path.read_text()))
    }

    assert report == {}


def test_cases_tree_mirrors_tests_tree() -> None:
    orphans: list[str] = []
    for path in case_module_paths():
        relative = path.relative_to(CASES_ROOT)
        test_file = relative.with_name(f"test_{relative.name}")
        if not any((TESTS_ROOT / level / test_file).exists() for level in LEVELS):
            orphans.append(str(relative))

    assert orphans == []

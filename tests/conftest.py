"""Root pytest configuration.

The test level (unit / integration / e2e) is derived from the directory a test lives in,
so a test cannot forget its marker and `pytest -m unit` always means "no I/O".
Contract suites in ``tests/contract`` declare their level explicitly (``pytestmark``):
the repository suites run on Postgres (integration), the gateway suite is pure (unit).
"""

from pathlib import Path

import pytest

_TESTS_ROOT = Path(__file__).parent
_LEVELS = ("unit", "integration", "e2e")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        relative = item.path.relative_to(_TESTS_ROOT)
        level = relative.parts[0]
        if level in _LEVELS:
            item.add_marker(getattr(pytest.mark, level))
        elif not any(item.get_closest_marker(name) for name in _LEVELS):
            # tests/contract/ declares its level in each module instead.
            raise pytest.UsageError(f"{item.nodeid} has no test level marker")

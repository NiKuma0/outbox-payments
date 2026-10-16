import os
import time
from pathlib import Path

import pytest

from outbox_payments.entrypoints.heartbeat import beat_once, is_fresh

pytestmark = pytest.mark.anyio


async def healthy() -> bool:
    return True


async def unhealthy() -> bool:
    return False


async def test_healthy_probe_touches_the_file(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat"

    await beat_once(path, healthy)

    assert path.exists()


async def test_unhealthy_probe_leaves_the_file_stale(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat"

    await beat_once(path, unhealthy)

    assert not path.exists()


def test_freshness_check(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat"
    assert not is_fresh(path, max_age=30)

    path.touch()
    assert is_fresh(path, max_age=30)

    old = time.time() - 60
    os.utime(path, (old, old))
    assert not is_fresh(path, max_age=30)

"""File-based liveness for worker processes without an HTTP port.

The worker touches a file while its dependencies answer; the container healthcheck
runs ``python -m outbox_payments.entrypoints.heartbeat <path> <max_age>`` and fails
when the file is older than ``max_age`` seconds.
"""

import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("/tmp/heartbeat")


async def beat_once(path: Path, probe: Callable[[], Awaitable[bool]]) -> None:
    try:
        healthy = await probe()
    except Exception:  # noqa: BLE001 - an exploding probe simply means "not healthy"
        healthy = False
    if healthy:
        await asyncio.to_thread(path.touch)


async def beat_forever(
    path: Path, probe: Callable[[], Awaitable[bool]], *, interval: float = 5.0
) -> None:
    while True:
        await beat_once(path, probe)
        await asyncio.sleep(interval)


def is_fresh(path: Path, *, max_age: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age
    except FileNotFoundError:
        return False


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    max_age = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    sys.exit(0 if is_fresh(path, max_age=max_age) else 1)


if __name__ == "__main__":
    main()

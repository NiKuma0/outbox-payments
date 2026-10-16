"""Graceful shutdown helpers shared by long-running processes."""

import asyncio
import contextlib
import logging
import signal

logger = logging.getLogger(__name__)


def install_stop_signals(stop: asyncio.Event) -> None:
    """SIGTERM/SIGINT set ``stop``; the worker finishes its current unit of work."""
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, _on_signal, stop, signum)


def _on_signal(stop: asyncio.Event, signum: int) -> None:
    logger.info("shutdown requested", extra={"signal": signal.Signals(signum).name})
    stop.set()


async def sleep_unless_stopped(stop: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking immediately when ``stop`` is set."""
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(seconds):
            await stop.wait()

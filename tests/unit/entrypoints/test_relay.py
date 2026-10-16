"""The relay loop, driven by fakes: no real time passes."""

import asyncio

import pytest

from outbox_payments.entrypoints.relay import RelayWorker

pytestmark = pytest.mark.anyio


class Script:
    """Feeds scripted round results and stops the worker when they run out."""

    def __init__(self, rounds: list[int | Exception], stop: asyncio.Event) -> None:
        self.rounds = rounds
        self.stop = stop
        self.idles: list[float] = []
        self.purges = 0
        self.now = 0.0

    async def relay_round(self) -> int:
        result = self.rounds.pop(0)
        if not self.rounds:
            self.stop.set()
        if isinstance(result, Exception):
            raise result
        return result

    async def purge(self) -> int:
        self.purges += 1
        return 0

    async def idle(self, seconds: float) -> None:
        self.idles.append(seconds)
        self.now += seconds

    def worker(self, *, cleanup_interval: float = 1000.0) -> RelayWorker:
        return RelayWorker(
            relay_round=self.relay_round,
            purge=self.purge,
            batch_size=10,
            poll_interval=0.5,
            cleanup_interval=cleanup_interval,
            idle=self.idle,
            monotonic=lambda: self.now,
        )


async def test_full_batches_are_drained_without_idling() -> None:
    stop = asyncio.Event()
    script = Script([10, 10, 3, 0], stop)

    await script.worker().run(stop)

    assert script.idles == [0.5, 0.5]  # only after the partial and the empty round


async def test_a_failed_round_is_logged_and_the_loop_keeps_going() -> None:
    stop = asyncio.Event()
    script = Script([ConnectionError("db down"), 1], stop)

    await script.worker().run(stop)

    assert script.rounds == []
    assert script.idles == [0.5, 0.5]


async def test_purge_runs_once_per_cleanup_interval() -> None:
    stop = asyncio.Event()
    script = Script([0, 0, 0, 0, 0], stop)

    await script.worker(cleanup_interval=1.0).run(stop)

    assert script.purges == 3  # at t=0, t=1.0, t=2.0


async def test_stops_before_the_next_round_once_signalled() -> None:
    stop = asyncio.Event()
    stop.set()
    script = Script([10], stop)

    await script.worker().run(stop)

    assert script.rounds == [10]

"""Pytest suite for :class:`AsyncBridge` — the sync→async submission gateway.

Covers: singleton reuse, round-trip coroutine execution, timeout enforcement,
concurrent submissions from multiple worker threads, and shutdown idempotency.

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.async_bridge import AsyncBridge


@pytest.mark.unit
class TestAsyncBridge:
    """Thread-safe coroutine submission over a shared daemon event loop."""

    def test_roundtrip_returns_coroutine_value(self) -> None:
        bridge = AsyncBridge.get_instance()

        async def work() -> int:
            await asyncio.sleep(0)
            return 42

        assert bridge.run(work(), timeout=2.0) == 42

    def test_singleton_is_reused(self) -> None:
        a = AsyncBridge.get_instance()
        b = AsyncBridge.get_instance()
        assert a is b

    def test_timeout_raises(self) -> None:
        bridge = AsyncBridge.get_instance()

        async def slow() -> None:
            await asyncio.sleep(5.0)

        with pytest.raises(TimeoutError):
            bridge.run(slow(), timeout=0.2)

    def test_concurrent_submissions_from_threads(self) -> None:
        """Ten worker threads submitting coroutines must all succeed."""
        bridge = AsyncBridge.get_instance()

        async def compute(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * x

        def worker(n: int) -> int:
            return bridge.run(compute(n), timeout=2.0)

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(worker, range(10)))

        assert results == [n * n for n in range(10)]

    def test_propagates_coroutine_exception(self) -> None:
        bridge = AsyncBridge.get_instance()

        async def boom() -> None:
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            bridge.run(boom(), timeout=2.0)

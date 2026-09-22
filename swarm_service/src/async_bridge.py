"""Async/sync bridge — long-lived daemon event loop for thread-safe coroutines.

The Swarm-Forge orchestrator dispatches DAG nodes onto a ``ThreadPoolExecutor``.
Some downstream subsystems (``SkillSynthesisEngine``) are coroutine-based, and
calling :func:`asyncio.run` from inside a worker thread spins up a fresh event
loop per call, stalls during ``await asyncio.to_thread(...)`` subcalls, and is
prone to ``RuntimeError: This event loop is already running`` under contention.

:class:`AsyncBridge` solves this with a single dedicated daemon thread hosting
one persistent event loop. Workers submit coroutines via
:func:`asyncio.run_coroutine_threadsafe` and block on the returned future up
to a timeout — giving us deterministic, thread-safe, non-leaky coroutine
execution from synchronous call sites.

Example:
    >>> bridge = AsyncBridge()
    >>> async def work() -> int: return 42
    >>> bridge.run(work(), timeout=5.0)
    42

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from typing import Any, Coroutine, TypeVar

logger: logging.Logger = logging.getLogger(__name__)

_DEFAULT_SHUTDOWN_TIMEOUT_SEC: float = 5.0
_DEFAULT_COROUTINE_TIMEOUT_SEC: float = 90.0

T = TypeVar("T")


class AsyncBridge:
    """Singleton-style bridge from synchronous worker threads to async code.

    Owns exactly one daemon thread hosting exactly one :class:`asyncio` event
    loop. Every coroutine submitted via :meth:`run` is scheduled onto that
    shared loop, blocking the caller until completion or timeout. The loop
    outlives individual DAG runs, so repeated submissions pay no setup cost.
    """

    _instance_lock: threading.Lock = threading.Lock()
    _instance: AsyncBridge | None = None

    def __init__(self) -> None:
        """Spin up the daemon thread and its event loop.

        Called exactly once by :meth:`get_instance`.
        """
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready: threading.Event = threading.Event()
        self._shutdown: bool = False
        self._thread: threading.Thread = threading.Thread(
            target=self._thread_main,
            name="SwarmForge-AsyncBridge",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=_DEFAULT_SHUTDOWN_TIMEOUT_SEC)
        atexit.register(self.shutdown)
        logger.debug("AsyncBridge: daemon event loop started")

    @classmethod
    def get_instance(cls) -> AsyncBridge:
        """Return the process-wide :class:`AsyncBridge` singleton.

        Returns:
            The shared bridge, creating it on first call.
        """
        with cls._instance_lock:
            if cls._instance is None or cls._instance._shutdown:
                cls._instance = cls()
            return cls._instance

    def _thread_main(self) -> None:
        """Daemon-thread target: install the loop and run forever."""
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            except Exception:  # noqa: BLE001 — shutdown path
                logger.debug("AsyncBridge: loop.close raised during shutdown")

    def run(
        self,
        coro: Coroutine[Any, Any, T],
        timeout: float = _DEFAULT_COROUTINE_TIMEOUT_SEC,
    ) -> T:
        """Submit *coro* to the shared loop and block for its result.

        Args:
            coro: The coroutine object to execute.
            timeout: Maximum seconds to wait for completion. A ``TimeoutError``
                is raised once exceeded; the coroutine is then cancelled on
                the loop thread.

        Returns:
            The value returned by the awaited coroutine.

        Raises:
            RuntimeError: If the bridge has already been shut down.
            TimeoutError: If the coroutine exceeds *timeout*.
        """
        if self._shutdown:
            raise RuntimeError("AsyncBridge: already shut down")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise

    def shutdown(self, timeout: float = _DEFAULT_SHUTDOWN_TIMEOUT_SEC) -> None:
        """Stop the event loop and join the daemon thread.

        Idempotent. Safe to call from ``atexit``.

        Args:
            timeout: Seconds to wait for graceful loop shutdown.
        """
        if self._shutdown:
            return
        self._shutdown = True
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except RuntimeError:
            # Loop may already be closed; nothing to do.
            return
        self._thread.join(timeout=timeout)
        logger.debug("AsyncBridge: shut down cleanly")

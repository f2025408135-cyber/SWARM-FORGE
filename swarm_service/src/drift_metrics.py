"""Drift metrics — hallucination-loop detection for repeated identical failures.

Keeps a per-node history of terminal outcomes and flags any node that
produces :data:`ANOMALY_THRESHOLD` consecutive identical non-success
outcomes as a drift loop. The orchestrator uses this signal to short-
circuit retry storms where a child agent is stuck regenerating the same
failing result.

Example:
    >>> dd = DriftDetector()
    >>> for _ in range(3):
    ...     dd.record_node_result("n1", {"status": "error"})
    >>> dd.loop_anomaly("n1")
    True

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import collections
import logging
from typing import Any, Final

logger: logging.Logger = logging.getLogger(__name__)

ANOMALY_THRESHOLD: Final[int] = 3
STATUS_SUCCESS: Final[str] = "success"
STATUS_UNKNOWN: Final[str] = "unknown"


class DriftDetector:
    """Flags nodes that repeat the same non-success outcome a threshold of times.

    Per-node history is unbounded (append-only); detection is a simple
    suffix check over the last :data:`ANOMALY_THRESHOLD` entries.
    """

    def __init__(self) -> None:
        """Initialise an empty per-node outcome history."""
        self._history: dict[str, list[str]] = collections.defaultdict(list)

    def record_node_result(
        self, node_id: str, result: dict[str, Any]
    ) -> None:
        """Append *result*'s status to the history for *node_id*.

        Args:
            node_id: Identifier of the DAG node whose result is being
                recorded.
            result: Result dict; only its ``status`` key is consulted.
        """
        outcome: str = result.get("status", STATUS_UNKNOWN)
        self._history[node_id].append(outcome)

    def loop_anomaly(self, node_id: str) -> bool:
        """Return True when the last *N* outcomes are identical and non-success.

        Args:
            node_id: Identifier of the DAG node to inspect.

        Returns:
            True if :data:`ANOMALY_THRESHOLD` consecutive identical
            non-success outcomes have been recorded for *node_id*.
        """
        history: list[str] = self._history[node_id]
        if len(history) < ANOMALY_THRESHOLD:
            return False
        recent: list[str] = history[-ANOMALY_THRESHOLD:]
        return len(set(recent)) == 1 and recent[0] != STATUS_SUCCESS

"""
Drift / hallucination-loop detection: flags nodes that repeatedly fail identically.
"""
from __future__ import annotations

import collections
from typing import Any


_ANOMALY_THRESHOLD = 3  # consecutive identical-error outcomes to trigger abort


class DriftDetector:
    def __init__(self) -> None:
        self._history: dict[str, list[str]] = collections.defaultdict(list)

    def record_node_result(self, node_id: str, result: dict[str, Any]) -> None:
        outcome = result.get("status", "unknown")
        self._history[node_id].append(outcome)

    def loop_anomaly(self, node_id: str) -> bool:
        history = self._history[node_id]
        if len(history) < _ANOMALY_THRESHOLD:
            return False
        recent = history[-_ANOMALY_THRESHOLD:]
        # A loop anomaly is _ANOMALY_THRESHOLD consecutive identical non-success outcomes.
        return len(set(recent)) == 1 and recent[0] != "success"

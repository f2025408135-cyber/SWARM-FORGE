"""
DAG execution engine: Kahn's-algorithm state manager + sequential runner.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger("swarmforge.dag")

_NodeStatus = str  # "pending" | "running" | "success" | "failed" | "skipped"


class DAGManager:
    """Tracks ready/running/terminal state for every node in a DAG."""

    def __init__(self, dag: dict[str, Any]) -> None:
        nodes: list[dict[str, Any]] = dag["nodes"]
        self._nodes: dict[str, dict[str, Any]] = {n["node_id"]: n for n in nodes}
        self._status: dict[str, _NodeStatus] = {n: "pending" for n in self._nodes}

        self._children: dict[str, list[str]] = defaultdict(list)
        self._in_degree: dict[str, int] = {n: 0 for n in self._nodes}
        for node in nodes:
            for dep in node["dependencies"]:
                self._children[dep].append(node["node_id"])
                self._in_degree[node["node_id"]] += 1

    def get_ready_nodes(self) -> list[str]:
        return [
            nid
            for nid, status in self._status.items()
            if status == "pending" and self._in_degree[nid] == 0
        ]

    def mark_running(self, node_id: str) -> None:
        self._status[node_id] = "running"

    def mark_complete(self, node_id: str, success: bool) -> None:
        self._status[node_id] = "success" if success else "failed"
        if success:
            for child in self._children[node_id]:
                self._in_degree[child] -= 1
        else:
            self._abort_subtree(node_id)

    def abort_subtree(self, node_id: str) -> None:
        self._status[node_id] = "failed"
        self._abort_subtree(node_id)

    def is_finished(self) -> bool:
        return all(
            s in ("success", "failed", "skipped")
            for s in self._status.values()
        )

    def get_node(self, node_id: str) -> dict[str, Any]:
        return self._nodes[node_id]

    def get_statuses(self) -> dict[str, _NodeStatus]:
        return dict(self._status)

    def _abort_subtree(self, node_id: str) -> None:
        queue = list(self._children[node_id])
        while queue:
            nid = queue.pop()
            if self._status[nid] == "pending":
                self._status[nid] = "skipped"
            queue.extend(self._children[nid])


class ParallelDAGRunner:
    """Runs DAG nodes sequentially in dependency order (Kahn's algorithm).

    Named 'Parallel' for API compatibility; actual execution is sequential
    via OS subprocesses in production callers — no threads are used here.
    """

    def __init__(
        self,
        dag_manager: DAGManager,
        executor_fn: Callable[[dict[str, Any]], dict[str, Any]],
        max_workers: int = 4,  # kept for API compatibility, unused
    ) -> None:
        self._manager = dag_manager
        self._executor_fn = executor_fn

    def run(self) -> dict[str, dict[str, Any]]:
        node_results: dict[str, dict[str, Any]] = {}
        submitted: set[str] = set()
        queue: list[str] = []

        def enqueue_ready() -> None:
            for node_id in self._manager.get_ready_nodes():
                if node_id not in submitted:
                    submitted.add(node_id)
                    queue.append(node_id)

        enqueue_ready()

        while queue:
            node_id = queue.pop(0)
            self._manager.mark_running(node_id)
            node = self._manager.get_node(node_id)
            result = self._run_node(node)
            success = result.get("status") == "success"
            self._manager.mark_complete(node_id, success)
            node_results[node_id] = result
            enqueue_ready()

        return node_results

    def _run_node(self, node: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._executor_fn(node)
        except Exception as exc:
            logger.exception("Node %s executor raised", node["node_id"])
            return {"status": "error", "error": str(exc)}

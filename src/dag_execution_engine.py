"""
DAG execution engine: Kahn's-algorithm state manager + thread-parallel runner.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
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

        self._lock = threading.Lock()

    def get_ready_nodes(self) -> list[str]:
        with self._lock:
            return [
                nid
                for nid, status in self._status.items()
                if status == "pending" and self._in_degree[nid] == 0
            ]

    def mark_running(self, node_id: str) -> None:
        with self._lock:
            self._status[node_id] = "running"

    def mark_complete(self, node_id: str, success: bool) -> None:
        with self._lock:
            self._status[node_id] = "success" if success else "failed"
            if success:
                for child in self._children[node_id]:
                    self._in_degree[child] -= 1
            else:
                self._abort_subtree_locked(node_id)

    def abort_subtree(self, node_id: str) -> None:
        with self._lock:
            self._status[node_id] = "failed"
            self._abort_subtree_locked(node_id)

    def is_finished(self) -> bool:
        with self._lock:
            return all(
                s in ("success", "failed", "skipped")
                for s in self._status.values()
            )

    def get_node(self, node_id: str) -> dict[str, Any]:
        return self._nodes[node_id]

    def get_statuses(self) -> dict[str, _NodeStatus]:
        with self._lock:
            return dict(self._status)

    def _abort_subtree_locked(self, node_id: str) -> None:
        queue = list(self._children[node_id])
        while queue:
            nid = queue.pop()
            if self._status[nid] == "pending":
                self._status[nid] = "skipped"
            queue.extend(self._children[nid])


class ParallelDAGRunner:
    """Runs DAG nodes in parallel threads, respecting dependency ordering."""

    def __init__(
        self,
        dag_manager: DAGManager,
        executor_fn: Callable[[dict[str, Any]], dict[str, Any]],
        max_workers: int = 4,
    ) -> None:
        self._manager = dag_manager
        self._executor_fn = executor_fn
        self._max_workers = max_workers

    def run(self) -> dict[str, dict[str, Any]]:
        node_results: dict[str, dict[str, Any]] = {}
        submitted: set[str] = set()
        submit_lock = threading.Lock()
        active_futures: dict[Future[dict[str, Any]], str] = {}

        def submit_ready(pool: ThreadPoolExecutor) -> None:
            with submit_lock:
                for node_id in self._manager.get_ready_nodes():
                    if node_id in submitted:
                        continue
                    submitted.add(node_id)
                    self._manager.mark_running(node_id)
                    node = self._manager.get_node(node_id)
                    future: Future[dict[str, Any]] = pool.submit(
                        self._run_node, node
                    )
                    active_futures[future] = node_id

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            submit_ready(pool)

            while active_futures:
                done = [f for f in list(active_futures) if f.done()]

                for future in done:
                    node_id = active_futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.exception("Future for %s raised", node_id)
                        result = {"status": "error", "error": str(exc)}

                    success = result.get("status") == "success"
                    self._manager.mark_complete(node_id, success)
                    node_results[node_id] = result
                    submit_ready(pool)

                if not done:
                    threading.Event().wait(0.05)

        return node_results

    def _run_node(self, node: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._executor_fn(node)
        except Exception as exc:
            logger.exception("Node %s executor raised", node["node_id"])
            return {"status": "error", "error": str(exc)}

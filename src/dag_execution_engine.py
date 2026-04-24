"""
DAG execution engine: Kahn's-algorithm state manager + parallel runner.
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger("swarmforge.dag")

_NodeStatus = str  # "pending" | "running" | "success" | "failed" | "skipped"


class DAGManager:
    """Tracks ready/running/terminal state for every node in a DAG."""

    def __init__(self, dag: dict[str, Any]) -> None:
        nodes: list[dict[str, Any]] = dag["nodes"]
        self._nodes: dict[str, dict[str, Any]] = {n["node_id"]: n for n in nodes}
        self._status: dict[str, _NodeStatus] = {n: "pending" for n in self._nodes}

        # CHANGE 1: cycle detection runs before in_degree is built
        self._detect_cycles(nodes)

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

    def _detect_cycles(self, nodes: list[dict[str, Any]]) -> None:
        """DFS WHITE/GRAY/BLACK cycle detection over the raw nodes list.

        Runs before self._children is populated, so builds its own adjacency.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        adj: dict[str, list[str]] = defaultdict(list)
        all_ids: set[str] = {n["node_id"] for n in nodes}
        for node in nodes:
            for dep in node["dependencies"]:
                adj[dep].append(node["node_id"])

        color: dict[str, int] = {n: WHITE for n in all_ids}

        def dfs(node_id: str) -> None:
            color[node_id] = GRAY
            for child in adj[node_id]:
                if color[child] == GRAY:
                    raise ValueError(
                        f"DAG contains circular dependencies: cycle through node {child}"
                    )
                if color[child] == WHITE:
                    dfs(child)
            color[node_id] = BLACK

        for nid in all_ids:
            if color[nid] == WHITE:
                dfs(nid)


class ParallelDAGRunner:
    """Runs DAG nodes in parallel using ThreadPoolExecutor."""

    def __init__(
        self,
        dag_manager: DAGManager,
        executor_fn: Callable[[dict[str, Any]], dict[str, Any]],
        max_workers: int = 4,
    ) -> None:
        self._manager = dag_manager
        self._executor_fn = executor_fn
        self.max_workers = max_workers
        self._governance_lock = threading.Lock()

    def run(self) -> dict[str, dict[str, Any]]:
        node_results: dict[str, dict[str, Any]] = {}
        submitted: set[str] = set()
        futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}

        def enqueue_ready(executor: ThreadPoolExecutor) -> None:
            for node_id in self._manager.get_ready_nodes():
                if node_id in submitted:
                    continue
                node = self._manager.get_node(node_id)

                # CHANGE 3: boardroom governance gate
                if node.get("metadata", {}).get("requires_approval"):
                    with self._governance_lock:
                        print(
                            f"[BOARDROOM GOVERNANCE: Node {node_id} requires human "
                            "authorization. Cost/Risk threshold exceeded.]"
                        )
                        answer = input("Authorize? [y/n]: ").strip().lower()
                    if answer != "y":
                        submitted.add(node_id)
                        self._manager.mark_complete(node_id, success=False)
                        node_results[node_id] = {
                            "status": "rejected",
                            "error": "boardroom_governance_rejected",
                        }
                        continue

                # CHANGE 2: submit to thread pool (truly parallel)
                submitted.add(node_id)
                self._manager.mark_running(node_id)
                future = executor.submit(self._run_node, node)
                futures[future] = node_id

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            enqueue_ready(executor)
            while futures:
                done, _ = concurrent.futures.wait(
                    list(futures.keys()),
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for future in done:
                    node_id = futures.pop(future)
                    result = future.result()
                    success = result.get("status") == "success"
                    self._manager.mark_complete(node_id, success)
                    node_results[node_id] = result
                enqueue_ready(executor)

        return node_results

    def _run_node(self, node: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._executor_fn(node)
        except Exception as exc:
            logger.exception("Node %s executor raised", node["node_id"])
            return {"status": "error", "error": str(exc)}

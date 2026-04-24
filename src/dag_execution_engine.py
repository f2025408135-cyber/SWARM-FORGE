"""DAG execution engine — Kahn bookkeeping plus a ThreadPoolExecutor parallel runner.

:class:`DAGManager` tracks node readiness via in-degree bookkeeping (Kahn's
algorithm) and performs a DFS WHITE/GRAY/BLACK cycle check at construction
time. :class:`ParallelDAGRunner` drives execution: it submits every ready
node to a :class:`~concurrent.futures.ThreadPoolExecutor`, waits for any
completion with :func:`concurrent.futures.wait`, and re-enqueues newly
unblocked nodes until the DAG is drained.

Example:
    >>> manager = DAGManager(dag_dict)
    >>> runner = ParallelDAGRunner(manager, executor_fn=run_node)
    >>> results = runner.run()

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Final

logger: logging.Logger = logging.getLogger(__name__)

MAX_PARALLEL_WORKERS: Final[int] = 4
STATUS_PENDING: Final[str] = "pending"
STATUS_RUNNING: Final[str] = "running"
STATUS_SUCCESS: Final[str] = "success"
STATUS_FAILED: Final[str] = "failed"
STATUS_SKIPPED: Final[str] = "skipped"
STATUS_ERROR: Final[str] = "error"
STATUS_REJECTED: Final[str] = "rejected"
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED}
)

_NodeStatus = str


class DAGManager:
    """Tracks ready/running/terminal state for every node in a DAG.

    Maintains an in-degree table per node so that ``get_ready_nodes`` is an
    O(N) scan over pending nodes with zero outstanding dependencies. Cycles
    are detected eagerly at construction so an ill-formed DAG never reaches
    the runner.
    """

    def __init__(self, dag: dict[str, Any]) -> None:
        """Index nodes, build the adjacency graph, and detect cycles.

        Args:
            dag: Raw DAG dict with a ``"nodes"`` list where each node has
                ``node_id`` and ``dependencies`` keys.

        Raises:
            ValueError: If the dependency graph contains a cycle.
        """
        nodes: list[dict[str, Any]] = dag["nodes"]
        self._nodes: dict[str, dict[str, Any]] = {n["node_id"]: n for n in nodes}
        self._status: dict[str, _NodeStatus] = {
            n: STATUS_PENDING for n in self._nodes
        }

        self._detect_cycles(nodes)

        self._children: dict[str, list[str]] = defaultdict(list)
        self._in_degree: dict[str, int] = {n: 0 for n in self._nodes}
        for node in nodes:
            for dep in node["dependencies"]:
                self._children[dep].append(node["node_id"])
                self._in_degree[node["node_id"]] += 1

    def get_ready_nodes(self) -> list[str]:
        """Return every pending node with zero outstanding dependencies.

        Returns:
            The list of node IDs eligible for immediate scheduling.
        """
        return [
            nid
            for nid, status in self._status.items()
            if status == STATUS_PENDING and self._in_degree[nid] == 0
        ]

    def mark_running(self, node_id: str) -> None:
        """Transition *node_id* from pending to running.

        Args:
            node_id: ID of the node being dispatched.
        """
        self._status[node_id] = STATUS_RUNNING

    def mark_complete(self, node_id: str, success: bool) -> None:
        """Transition *node_id* to terminal state and propagate to children.

        Args:
            node_id: ID of the node whose execution finished.
            success: True if the node reached ``success`` status; False
                routes the whole subtree to ``skipped``.
        """
        self._status[node_id] = STATUS_SUCCESS if success else STATUS_FAILED
        if success:
            for child in self._children[node_id]:
                self._in_degree[child] -= 1
        else:
            self._abort_subtree(node_id)

    def abort_subtree(self, node_id: str) -> None:
        """Mark *node_id* failed and cascade-skip every descendant.

        Args:
            node_id: Root of the subtree to abort.
        """
        self._status[node_id] = STATUS_FAILED
        self._abort_subtree(node_id)

    def is_finished(self) -> bool:
        """Return True when every node has reached a terminal status.

        Returns:
            True if all nodes are in success/failed/skipped state.
        """
        return all(s in _TERMINAL_STATUSES for s in self._status.values())

    def get_node(self, node_id: str) -> dict[str, Any]:
        """Return the raw node dict for *node_id*.

        Args:
            node_id: ID of the node to look up.

        Returns:
            The original node dict supplied at construction time.
        """
        return self._nodes[node_id]

    def get_statuses(self) -> dict[str, _NodeStatus]:
        """Return a defensive copy of the status map.

        Returns:
            A fresh ``{node_id: status}`` dict the caller may mutate freely.
        """
        return dict(self._status)

    def _abort_subtree(self, node_id: str) -> None:
        """BFS through descendants of *node_id* marking pending ones skipped.

        Args:
            node_id: Root node whose children and grandchildren should be
                cascade-skipped if still pending.
        """
        queue: list[str] = list(self._children[node_id])
        while queue:
            nid: str = queue.pop()
            if self._status[nid] == STATUS_PENDING:
                self._status[nid] = STATUS_SKIPPED
            queue.extend(self._children[nid])

    def _detect_cycles(self, nodes: list[dict[str, Any]]) -> None:
        """DFS WHITE/GRAY/BLACK cycle detection over the raw nodes list.

        Uses the three-colour DFS algorithm from CLRS:

        * WHITE nodes have not yet been visited.
        * GRAY nodes are on the current recursion stack; finding a GRAY
          descendant during traversal proves a back-edge, i.e. a cycle.
        * BLACK nodes have been fully explored and proven acyclic.

        Runs before ``self._children`` is populated and so builds its own
        adjacency list.

        Args:
            nodes: Raw node dicts as supplied to the constructor.

        Raises:
            ValueError: If a back-edge to a GRAY ancestor is discovered.
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
                        f"DAG contains circular dependencies: cycle through "
                        f"node {child}"
                    )
                if color[child] == WHITE:
                    dfs(child)
            color[node_id] = BLACK

        for nid in all_ids:
            if color[nid] == WHITE:
                dfs(nid)


class ParallelDAGRunner:
    """Runs DAG nodes in parallel using :class:`ThreadPoolExecutor`.

    Submits every ready node as a Future, waits for the first completion,
    re-enqueues newly unblocked nodes, and repeats until the DAG is drained.
    Boardroom HITL governance: any node whose metadata sets
    ``requires_approval`` is gated behind a synchronous human prompt under
    ``_governance_lock`` before dispatch.
    """

    def __init__(
        self,
        dag_manager: DAGManager,
        executor_fn: Callable[[dict[str, Any]], dict[str, Any]],
        max_workers: int = MAX_PARALLEL_WORKERS,
    ) -> None:
        """Initialise the runner with a DAG state manager and executor.

        Args:
            dag_manager: Pre-constructed :class:`DAGManager` holding the DAG
                state.
            executor_fn: Callable invoked with each node dict; must return a
                result dict containing a ``status`` key.
            max_workers: Maximum concurrent threads for node execution.
        """
        self._manager: DAGManager = dag_manager
        self._executor_fn: Callable[[dict[str, Any]], dict[str, Any]] = executor_fn
        self.max_workers: int = max_workers
        self._governance_lock: threading.Lock = threading.Lock()

    def run(self) -> dict[str, dict[str, Any]]:
        """Drain the DAG in parallel and return every node's result.

        Returns:
            A ``{node_id: result_dict}`` mapping covering every node that
            was submitted (skipped nodes are omitted).
        """
        node_results: dict[str, dict[str, Any]] = {}
        submitted: set[str] = set()
        futures: dict[concurrent.futures.Future[dict[str, Any]], str] = {}

        def enqueue_ready(executor: ThreadPoolExecutor) -> None:
            for node_id in self._manager.get_ready_nodes():
                if node_id in submitted:
                    continue
                node: dict[str, Any] = self._manager.get_node(node_id)

                if node.get("metadata", {}).get("requires_approval"):
                    with self._governance_lock:
                        logger.warning(
                            "BOARDROOM GOVERNANCE: Node %s requires human "
                            "authorization. Cost/Risk threshold exceeded.",
                            node_id,
                        )
                        answer: str = input(
                            f"Authorize node '{node_id}'? [y/n]: "
                        ).strip().lower()
                    if answer != "y":
                        submitted.add(node_id)
                        self._manager.mark_complete(node_id, success=False)
                        node_results[node_id] = {
                            "status": STATUS_REJECTED,
                            "error": "boardroom_governance_rejected",
                        }
                        continue

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
                    node_id: str = futures.pop(future)
                    result: dict[str, Any] = future.result()
                    success: bool = result.get("status") == STATUS_SUCCESS
                    self._manager.mark_complete(node_id, success)
                    node_results[node_id] = result
                enqueue_ready(executor)

        return node_results

    def _run_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """Invoke the user executor and convert any exception to an error result.

        Args:
            node: Raw node dict dispatched to the executor.

        Returns:
            The executor's result dict, or an error dict on uncaught
            exception.
        """
        try:
            return self._executor_fn(node)
        except Exception as exc:
            logger.exception("Node %s executor raised", node["node_id"])
            return {"status": STATUS_ERROR, "error": str(exc)}

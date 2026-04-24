"""Parallel DAG Execution Engine for multi-agent swarm orchestration.

Parses JSON task topologies, validates acyclicity via Kahn's algorithm, and
executes independent branches concurrently using a ``ThreadPoolExecutor``.
Failed nodes propagate cancellation downstream while independent branches
continue executing.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom errors
# ---------------------------------------------------------------------------

class CircularDependencyError(Exception):
    """Raised when the task graph contains a cycle.

    Attributes
    ----------
    cycle_nodes:
        The set of node IDs involved in the detected cycle.
    """

    def __init__(self, message: str, cycle_nodes: set[str] | None = None) -> None:
        self.cycle_nodes: set[str] = cycle_nodes or set()
        super().__init__(message)


class MissingDependencyError(Exception):
    """Raised when a node references a dependency that does not exist.

    Attributes
    ----------
    missing:
        Mapping of ``node_id`` → set of unknown dependency IDs.
    """

    def __init__(
        self,
        message: str,
        missing: dict[str, set[str]] | None = None,
    ) -> None:
        self.missing: dict[str, set[str]] = missing or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class NodeStatus(Enum):
    """Lifecycle states for a task node inside the DAG runner."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskNode:
    """A single vertex in the execution DAG.

    Attributes
    ----------
    node_id:
        Unique identifier (e.g. ``"agent_recon"``).
    dependencies:
        Set of ``node_id`` values that must reach :attr:`NodeStatus.COMPLETED`
        before this node can be scheduled.
    executable_payload:
        Arbitrary metadata dict forwarded to the execution callback.
    status:
        Current lifecycle state.  Defaults to :attr:`NodeStatus.PENDING`.
    """
    node_id: str
    dependencies: set[str] = field(default_factory=set)
    executable_payload: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING


# ---------------------------------------------------------------------------
# DAG manager — graph construction + topological validation
# ---------------------------------------------------------------------------

class DAGManager:
    """Builds, validates, and topologically sorts a task dependency graph.

    Nodes may be added in **any order**, including with forward references
    (dependencies on nodes not yet registered).  All structural validation
    — missing dependencies and cycle detection — is deferred to
    :meth:`validate_and_sort`, which rebuilds the adjacency list from
    scratch each time.

    Internally maintains an adjacency list (node → dependents) and an
    in-degree counter for Kahn's algorithm.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}

    # -- mutation -----------------------------------------------------------

    def add_node(self, node: TaskNode) -> None:
        """Register *node*.

        Forward references in *node.dependencies* are permitted; they will
        be validated when :meth:`validate_and_sort` is called.

        Raises
        ------
        ValueError
            If *node.node_id* was already registered.
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Duplicate node_id: '{node.node_id}'")
        self._nodes[node.node_id] = node

    # -- graph construction (internal) --------------------------------------

    def _build_graph(self) -> tuple[dict[str, set[str]], dict[str, int]]:
        """Rebuild adjacency list and in-degree map from registered nodes.

        Returns
        -------
        tuple[dict[str, set[str]], dict[str, int]]
            ``(adjacency, in_degree)`` — where *adjacency* maps each node
            to its set of successors and *in_degree* counts incoming edges.
        """
        adjacency: dict[str, set[str]] = {nid: set() for nid in self._nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}

        for nid, node in self._nodes.items():
            for dep in node.dependencies:
                adjacency.setdefault(dep, set()).add(nid)
                in_degree[nid] = in_degree.get(nid, 0) + 1

        return adjacency, in_degree

    # -- validation ---------------------------------------------------------

    def validate_and_sort(self) -> list[str]:
        """Validate the graph and return a topological ordering.

        Checks for missing dependencies first, then runs Kahn's algorithm.

        Returns
        -------
        list[str]
            Node IDs in a valid execution order (dependencies before
            dependents).

        Raises
        ------
        MissingDependencyError
            If any node references a dependency not present in the graph.
        CircularDependencyError
            If the graph contains at least one cycle.  The offending nodes
            are attached to :attr:`CircularDependencyError.cycle_nodes`.
        """
        # ---- 1. Check for missing dependencies ----------------------------
        known_ids: set[str] = set(self._nodes)
        missing: dict[str, set[str]] = {
            nid: node.dependencies - known_ids
            for nid, node in self._nodes.items()
            if node.dependencies - known_ids
        }
        if missing:
            flat: set[str] = {d for deps in missing.values() for d in deps}
            raise MissingDependencyError(
                f"{len(flat)} unknown dependency/ies referenced by "
                f"{len(missing)} node(s): {sorted(flat)}",
                missing=missing,
            )

        # ---- 2. Kahn's algorithm -------------------------------------------
        adjacency: dict[str, set[str]]
        in_degree: dict[str, int]
        adjacency, in_degree = self._build_graph()

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        sorted_order: list[str] = []

        while queue:
            nid: str = queue.popleft()
            sorted_order.append(nid)

            for successor in adjacency.get(nid, set()):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(sorted_order) != len(self._nodes):
            remaining: set[str] = set(self._nodes) - set(sorted_order)
            raise CircularDependencyError(
                f"Circular dependency detected among {len(remaining)} "
                f"node(s): {sorted(remaining)}",
                cycle_nodes=remaining,
            )

        return sorted_order

    # -- read-only accessors ------------------------------------------------

    @property
    def nodes(self) -> dict[str, TaskNode]:
        """Return a shallow copy of the node registry."""
        return dict(self._nodes)

    def successors(self, node_id: str) -> set[str]:
        """Return the set of direct dependents of *node_id*."""
        adjacency: dict[str, set[str]]
        in_degree: dict[str, int]
        adjacency, _ = self._build_graph()
        return set(adjacency.get(node_id, set()))


# ---------------------------------------------------------------------------
# Parallel DAG runner
# ---------------------------------------------------------------------------

class ParallelDAGRunner:
    """Execute a validated DAG with bounded thread-level parallelism.

    Nodes whose dependencies are all :attr:`NodeStatus.COMPLETED` are
    submitted to a :class:`~concurrent.futures.ThreadPoolExecutor` as soon
    as they become ready.  When a node fails, all **transitive downstream**
    dependents are marked :attr:`NodeStatus.CANCELLED` while unrelated
    branches continue executing independently.

    Parameters
    ----------
    dag_manager:
        A fully populated :class:`DAGManager`.  Call
        :meth:`DAGManager.validate_and_sort` before passing it here to
        catch structural errors early.
    max_workers:
        Upper bound on concurrent threads in the pool.
    """

    def __init__(
        self,
        dag_manager: DAGManager,
        max_workers: int = 5,
    ) -> None:
        self._dag: DAGManager = dag_manager
        self._max_workers: int = max_workers
        self._lock: threading.Lock = threading.Lock()
        self._results: dict[str, Any] = {}
        self._futures: dict[str, Future[Any]] = {}

    # -- internal helpers ---------------------------------------------------

    def _is_ready(self, node: TaskNode) -> bool:
        """Return ``True`` if every dependency is COMPLETED."""
        return all(
            self._dag.nodes[dep].status == NodeStatus.COMPLETED
            for dep in node.dependencies
        )

    def _has_failed_dependency(self, node: TaskNode) -> bool:
        """Return ``True`` if any dependency is FAILED or CANCELLED."""
        return any(
            self._dag.nodes[dep].status
            in (NodeStatus.FAILED, NodeStatus.CANCELLED)
            for dep in node.dependencies
        )

    def _cancel_downstream(self, failed_node_id: str) -> None:
        """Recursively mark all transitive dependents as CANCELLED.

        Acquires :attr:`_lock` per-node to remain safe under concurrent
        resolution callbacks.
        """
        queue: deque[str] = deque(self._dag.successors(failed_node_id))
        visited: set[str] = set()

        while queue:
            nid: str = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)

            with self._lock:
                target: TaskNode = self._dag.nodes[nid]
                if target.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    target.status = NodeStatus.CANCELLED
                    self._results[nid] = RuntimeError(
                        f"Cancelled: upstream node '{failed_node_id}' failed."
                    )

            for child in self._dag.successors(nid):
                if child not in visited:
                    queue.append(child)

    # -- public API ---------------------------------------------------------

    def execute_graph(
        self,
        task_execution_callback: Callable[[TaskNode], Any],
    ) -> dict[str, Any]:
        """Execute the full DAG and return per-node results.

        Parameters
        ----------
        task_execution_callback:
            A callable that receives a :class:`TaskNode` and returns a
            result.  If it raises, the node is marked FAILED and all
            transitive downstream dependents are CANCELLED.

        Returns
        -------
        dict[str, Any]
            Mapping of ``node_id`` → result value or exception instance for
            every node in the graph.
        """
        self._results.clear()
        self._futures.clear()

        # Reset all nodes to PENDING for a clean run.
        for node in self._dag.nodes.values():
            node.status = NodeStatus.PENDING

        # Seed with nodes that have zero dependencies.
        ready_nodes: list[TaskNode] = [
            n for n in self._dag.nodes.values() if len(n.dependencies) == 0
        ]

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit the first wave.
            for node in ready_nodes:
                with self._lock:
                    node.status = NodeStatus.RUNNING
                future: Future[Any] = executor.submit(
                    task_execution_callback, node,
                )
                self._futures[node.node_id] = future

            # Event loop: drain futures and schedule newly-ready nodes.
            while self._futures:
                # Non-blocking scan for already-resolved futures.
                done_ids: list[str] = [
                    nid for nid, fut in self._futures.items() if fut.done()
                ]

                # If nothing is ready yet, block on the first to complete.
                if not done_ids:
                    try:
                        first_done: Future[Any] = next(
                            as_completed(self._futures.values()),
                        )
                        for nid, fut in self._futures.items():
                            if fut is first_done:
                                done_ids.append(nid)
                                break
                    except StopIteration:
                        break

                # Process each completed future.
                for nid in done_ids:
                    future = self._futures.pop(nid)
                    node: TaskNode = self._dag.nodes[nid]

                    try:
                        result: Any = future.result()
                        with self._lock:
                            node.status = NodeStatus.COMPLETED
                            self._results[nid] = result
                    except Exception as exc:
                        with self._lock:
                            node.status = NodeStatus.FAILED
                            self._results[nid] = exc
                        self._cancel_downstream(nid)

                    # Check successors for newly-ready or failed nodes.
                    for successor_id in self._dag.successors(nid):
                        s_node: TaskNode = self._dag.nodes[successor_id]
                        if s_node.status != NodeStatus.PENDING:
                            continue

                        if self._has_failed_dependency(s_node):
                            with self._lock:
                                s_node.status = NodeStatus.CANCELLED
                                self._results[successor_id] = RuntimeError(
                                    f"Cancelled: upstream node '{nid}' failed."
                                )
                            self._cancel_downstream(successor_id)
                            continue

                        if self._is_ready(s_node):
                            with self._lock:
                                s_node.status = NodeStatus.RUNNING
                            sf: Future[Any] = executor.submit(
                                task_execution_callback, s_node,
                            )
                            self._futures[successor_id] = sf

        # Defensive: ensure every node has a result entry.
        for nid, node in self._dag.nodes.items():
            if nid not in self._results:
                self._results[nid] = RuntimeError(
                    f"Node '{nid}' ended in state {node.status.value}"
                )

        logger.info(
            "DAG execution finished — %d nodes, %d completed, %d failed/cancelled.",
            len(self._dag.nodes),
            sum(
                1
                for n in self._dag.nodes.values()
                if n.status == NodeStatus.COMPLETED
            ),
            sum(
                1
                for n in self._dag.nodes.values()
                if n.status in (NodeStatus.FAILED, NodeStatus.CANCELLED)
            ),
        )

        return dict(self._results)

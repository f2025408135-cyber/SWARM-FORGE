"""MetaOrchestrator — master controller that wires all eight Swarm-Forge modules.

Ingests a natural-language enterprise problem, gates it through the zero-trust
firewall, plans a DAG via the Anthropic API, executes it in parallel sandboxed
subprocesses, verifies each node semantically with the reward-swarm judge, and
persists terminal state through an OS-level mutex store.

Execution flow:
  1. AgentFirewall gates the raw input problem.
  2. dag_planner produces a validated DAG.
  3. Initial state is written to .swarmforge_state.json via SynchronizedJSONStore.
  4. ParallelDAGRunner drives node execution through SandboxExecutor.
  5. RewardSwarmJudge verifies stdout genuinely proves the task was solved.
  6. DriftDetector checks each result; branch is aborted on anomaly.
  7. HPFELogger records all failures as structured OTel events.
  8. Final state is persisted and a summary dict is returned.

Example:
    >>> orchestrator = MetaOrchestrator(max_workers=4)
    >>> result = orchestrator.run("Decompose and execute our Q2 migration plan.")
    >>> result["status"]
    'completed'

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .ast_context_compressor import ASTContextCompressor
from .dag_execution_engine import DAGManager, ParallelDAGRunner
from .dag_planner import plan_dag
from .drift_metrics import DriftDetector
from .execution_sandbox import SandboxExecutor
from .memory_system import SynapticGarbageCollector
from .mutex_storage import SynchronizedJSONStore
from .otel_telemetry_logger import HPFELogger
from .reward_judge import RewardSwarmJudge
from .skill_synthesis import SkillSynthesisEngine
from .zero_trust_firewall import AgentFirewall

logger: logging.Logger = logging.getLogger(__name__)

STATE_FILE: str = ".swarmforge_state.json"
DEFAULT_MAX_WORKERS: int = 4
DEFAULT_NODE_TIMEOUT_SEC: int = 120
PROBLEM_TRUNCATE_LEN: int = 500
PROBLEM_LOG_TRUNCATE_LEN: int = 200

STATUS_RUNNING: str = "running"
STATUS_COMPLETED: str = "completed"
STATUS_PARTIAL: str = "partial"
STATUS_FAILED: str = "failed"
STATUS_BLOCKED: str = "blocked"
STATUS_PLANNING_FAILED: str = "planning_failed"


class MetaOrchestrator:
    """Top-level controller wiring firewall, planner, executor, judge, and logger.

    Thread-safe: shared state is protected by OS-level file locking through
    :class:`SynchronizedJSONStore`, and the DAG runner confines mutation of
    scheduling state to a single enqueue coroutine.
    """

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        """Initialise all eight subsystems.

        Args:
            max_workers: Maximum number of DAG nodes to execute in parallel.
        """
        self._firewall: AgentFirewall = AgentFirewall()
        self._store: SynchronizedJSONStore = SynchronizedJSONStore(STATE_FILE)
        self._otel: HPFELogger = HPFELogger()
        self._sandbox: SandboxExecutor = SandboxExecutor()
        self._drift: DriftDetector = DriftDetector()
        self._compressor: ASTContextCompressor = ASTContextCompressor()
        self._max_workers: int = max_workers
        self._reward_judge: RewardSwarmJudge = RewardSwarmJudge(use_opus=False)
        self._sgc: SynapticGarbageCollector = SynapticGarbageCollector()
        self._skill_engine: SkillSynthesisEngine = SkillSynthesisEngine(
            sandbox=self._sandbox
        )

    # ── public ─────────────────────────────────────────────────────────────

    def run(self, problem: str) -> dict[str, Any]:
        """Run end-to-end orchestration on a natural-language problem.

        Args:
            problem: Free-text enterprise problem to decompose and execute.

        Returns:
            A status dict with keys ``status``, ``nodes_completed``,
            ``nodes_failed``, and ``execution_time_sec``. Failure modes
            return additional ``reason`` or ``error`` keys.
        """
        start: float = time.monotonic()

        ok, reason = self._firewall.validate_input(problem)
        if not ok:
            self._otel.log_event("input_blocked", {"reason": reason})
            return self._result(
                STATUS_BLOCKED,
                nodes_completed=[],
                nodes_failed=[],
                elapsed=time.monotonic() - start,
                extra={"reason": reason},
            )

        try:
            dag: dict[str, Any] = plan_dag(problem)
        except (RuntimeError, EnvironmentError, ValueError) as exc:
            logger.exception("DAG planning failed")
            self._otel.log_failure(
                "dag_planner", exc, {"problem": problem[:PROBLEM_LOG_TRUNCATE_LEN]}
            )
            return self._result(
                STATUS_PLANNING_FAILED,
                nodes_completed=[],
                nodes_failed=[],
                elapsed=time.monotonic() - start,
                extra={"error": self._compressor.compress_error(exc)},
            )

        node_ids: list[str] = [n["node_id"] for n in dag["nodes"]]

        self._store.write(
            {
                "status": STATUS_RUNNING,
                "problem": problem[:PROBLEM_TRUNCATE_LEN],
                "dag": dag,
                "nodes_completed": [],
                "nodes_failed": [],
                "started_at": time.time(),
            }
        )

        dag_manager: DAGManager = DAGManager(dag)
        runner: ParallelDAGRunner = ParallelDAGRunner(
            dag_manager,
            executor_fn=lambda node: self._execute_node(node, dag),
            max_workers=self._max_workers,
        )
        runner.run()

        statuses: dict[str, str] = dag_manager.get_statuses()
        nodes_completed: list[str] = [
            nid for nid in node_ids if statuses.get(nid) == "success"
        ]
        nodes_failed: list[str] = [
            nid for nid in node_ids if statuses.get(nid) in ("failed", "error")
        ]
        nodes_skipped: list[str] = [
            nid for nid in node_ids if statuses.get(nid) == "skipped"
        ]

        overall: str = (
            STATUS_COMPLETED
            if not nodes_failed and not nodes_skipped
            else STATUS_PARTIAL
            if nodes_completed
            else STATUS_FAILED
        )
        elapsed: float = time.monotonic() - start

        self._store.update(
            {
                "status": overall,
                "nodes_completed": nodes_completed,
                "nodes_failed": nodes_failed,
                "nodes_skipped": nodes_skipped,
                "execution_time_sec": round(elapsed, 3),
                "finished_at": time.time(),
            }
        )

        self._otel.log_event(
            "orchestration_complete",
            {
                "status": overall,
                "nodes_total": len(node_ids),
                "nodes_completed": len(nodes_completed),
                "nodes_failed": len(nodes_failed),
                "nodes_skipped": len(nodes_skipped),
                "execution_time_sec": round(elapsed, 3),
            },
        )

        return self._result(
            overall,
            nodes_completed=nodes_completed,
            nodes_failed=nodes_failed,
            elapsed=elapsed,
        )

    # ── private ────────────────────────────────────────────────────────────

    def _execute_node(
        self, node: dict[str, Any], dag: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a single DAG node with firewall, sandbox, and reward-judge gating.

        Re-validates the generated task description through the firewall, runs
        the sandboxed subprocess with a metadata-derived timeout, then submits
        stdout to :class:`RewardSwarmJudge` for semantic verification. A
        failure signal from any gate demotes the node to ``error`` status and
        emits an OTel failure event plus an immunity lesson to ``LESSON.md``.

        Args:
            node: DAG node dict with ``node_id``, ``task_description``, and
                optional ``metadata`` keys.
            dag: Full DAG dict, passed through to the sandbox as context.

        Returns:
            A dict with ``status``, ``output``, and ``error`` keys matching the
            :class:`SandboxExecutor` contract.
        """
        node_id: str = node["node_id"]
        task_description: str = node["task_description"]

        ok, reason = self._firewall.validate_input(task_description)
        if not ok:
            self._otel.log_event(
                "node_blocked", {"node_id": node_id, "reason": reason}
            )
            return {"status": "error", "error": f"firewall_blocked: {reason}"}

        metadata: dict[str, Any] = node.get("metadata", {})
        timeout_sec: int = int(
            metadata.get("expected_duration")
            or metadata.get("complexity")
            or DEFAULT_NODE_TIMEOUT_SEC
        )

        try:
            result: dict[str, Any] = self._sandbox.execute(
                node_id,
                task_description,
                {"dag_metadata": dag.get("metadata", {})},
                timeout_sec=timeout_sec,
            )
            if result.get("status") == "success":
                passed, critique = self._reward_judge.judge(
                    stdout=result.get("output", ""),
                    task_description=task_description,
                )
                if not passed:
                    result["status"] = "error"
                    existing_error: str = result.get("error") or ""
                    result["error"] = (
                        f"[SEMANTIC FAILURE] {critique}\n{existing_error}"
                    )
        except (OSError, RuntimeError, ValueError) as exc:
            compressed: str = self._compressor.compress_error(exc)
            logger.exception("Unhandled sandbox error on node %s", node_id)
            self._otel.log_failure(node_id, exc, {"node": node, "trace": compressed})
            return {"status": "error", "error": compressed}

        self._drift.record_node_result(node_id, result)
        if self._drift.loop_anomaly(node_id):
            self._otel.log_event(
                "drift_abort", {"node_id": node_id, "result": result}
            )
            logger.warning(
                "Drift loop anomaly detected on node %s — branch aborted", node_id
            )
            return {"status": "error", "error": "drift_loop_anomaly"}

        if result.get("status") != "success":
            analysis: str = self._compressor.compress_error(
                RuntimeError(result.get("error", "unknown"))
            )
            self._write_immunity_lesson(node_id, task_description, "SYNTACTIC", analysis)
            self._otel.log_failure(
                node_id,
                RuntimeError(result.get("error", "unknown")),
                {"result": result},
            )

            # === TEST-TIME TOOL EVOLUTION (HERMES PARADIGM) ===
            missing_capability: str = node.get("metadata", {}).get(
                "missing_capability", ""
            )
            if missing_capability:
                logger.info(
                    "_execute_node: triggering SkillSynthesisEngine for "
                    "node=%s capability=%r",
                    node_id,
                    missing_capability,
                )
                synth_success, skill_path, synth_error = asyncio.run(
                    self._skill_engine.synthesize_on_demand(
                        task_objective=missing_capability,
                        node_id=node_id,
                    )
                )
                if synth_success:
                    logger.info(
                        "_execute_node: skill synthesized at %s — "
                        "retrying node %s",
                        skill_path,
                        node_id,
                    )
                    self._skill_engine.load_skill(skill_path)
                    result["synthesized_skill"] = skill_path
                    result["status"] = "retry_with_skill"
                else:
                    logger.warning(
                        "_execute_node: skill synthesis failed for "
                        "node=%s: %s",
                        node_id,
                        synth_error,
                    )
            return result

        return result

    def _write_immunity_lesson(
        self,
        node_id: str,
        task_description: str,
        failure_type: str,
        ast_analysis: str,
    ) -> None:
        """Persist a structured failure lesson via the Synaptic Garbage Collector.

        Delegates all file I/O and compression logic to :class:`SynapticGarbageCollector`.
        The SGC appends the formatted trace to its managed memory file and triggers
        a Sawtooth Collapse if the file has exceeded its token budget.

        Args:
            node_id: Identifier of the failing DAG node.
            task_description: Verbatim task description that failed.
            failure_type: Either ``"SYNTACTIC"`` or ``"SEMANTIC"``.
            ast_analysis: Compressed AST/traceback excerpt for future triage.
        """
        error_trace: str = (
            f"Task: {task_description}\n"
            f"Failure-Type: {failure_type}\n"
            f"AST-Analysis: {ast_analysis}\n"
            f"Recorded-At: {datetime.now(timezone.utc).isoformat()}"
        )
        self._sgc.commit_and_prune(node_id, error_trace)
        logger.info(
            "Immunity lesson written via SGC — node=%s failure_type=%s",
            node_id,
            failure_type,
        )

    @staticmethod
    def _result(
        status: str,
        *,
        nodes_completed: list[str],
        nodes_failed: list[str],
        elapsed: float,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the canonical orchestration result dict.

        Args:
            status: Overall run status.
            nodes_completed: Node IDs that reached ``success``.
            nodes_failed: Node IDs that reached ``failed`` or ``error``.
            elapsed: Total wall-clock seconds.
            extra: Optional additional keys merged into the result.

        Returns:
            The canonical result dict for the orchestration run.
        """
        out: dict[str, Any] = {
            "status": status,
            "nodes_completed": nodes_completed,
            "nodes_failed": nodes_failed,
            "execution_time_sec": round(elapsed, 3),
        }
        if extra:
            out.update(extra)
        return out

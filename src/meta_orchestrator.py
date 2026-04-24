"""
MetaOrchestrator — Window 0: master controller that wires all eight modules.

Execution flow:
  1. AgentFirewall gates the raw input problem.
  2. dag_planner produces a validated DAG.
  3. State is written to .swarmforge_state.json via SynchronizedJSONStore.
  4. ParallelDAGRunner drives node execution through SandboxExecutor.
  5. DriftDetector checks each result; branch is aborted on anomaly.
  6. HPFELogger records all failures as structured OTel events.
  7. Final state is persisted and a summary dict is returned.
"""
from __future__ import annotations

import json as _json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from filelock import FileLock

from ast_context_compressor import ASTContextCompressor
from dag_execution_engine import DAGManager, ParallelDAGRunner
from dag_planner import plan_dag
from drift_metrics import DriftDetector
from execution_sandbox import SandboxExecutor
from mutex_storage import SynchronizedJSONStore
from otel_telemetry_logger import HPFELogger
from zero_trust_firewall import AgentFirewall
from src.reward_judge import RewardSwarmJudge

logger = logging.getLogger("swarmforge.orchestrator")

_STATE_FILE = ".swarmforge_state.json"
_LESSON_FILE = Path(__file__).parent.parent / "LESSON.md"


class MetaOrchestrator:
    def __init__(self, max_workers: int = 4) -> None:
        self._firewall = AgentFirewall()
        self._store = SynchronizedJSONStore(_STATE_FILE)
        self._otel = HPFELogger()
        self._sandbox = SandboxExecutor()
        self._drift = DriftDetector()
        self._compressor = ASTContextCompressor()
        self._max_workers = max_workers
        self._reward_judge = RewardSwarmJudge(use_opus=False)

    # ── public ─────────────────────────────────────────────────────────────

    def run(self, problem: str) -> dict[str, Any]:
        start = time.monotonic()

        # 1. Firewall: validate raw input before touching any external resource.
        ok, reason = self._firewall.validate_input(problem)
        if not ok:
            self._otel.log_event("input_blocked", {"reason": reason})
            return self._result(
                "blocked",
                nodes_completed=[],
                nodes_failed=[],
                elapsed=time.monotonic() - start,
                extra={"reason": reason},
            )

        # 2. Plan the DAG (Opus 4.7 with Haiku fallback, handled inside dag_planner).
        try:
            dag = plan_dag(problem)
        except Exception as exc:
            self._otel.log_failure(
                "dag_planner", exc, {"problem": problem[:200]}
            )
            return self._result(
                "planning_failed",
                nodes_completed=[],
                nodes_failed=[],
                elapsed=time.monotonic() - start,
                extra={"error": self._compressor.compress_error(exc)},
            )

        node_ids: list[str] = [n["node_id"] for n in dag["nodes"]]

        # 3. Persist initial run state.
        self._store.write(
            {
                "status": "running",
                "problem": problem[:500],
                "dag": dag,
                "nodes_completed": [],
                "nodes_failed": [],
                "started_at": time.time(),
            }
        )

        # 4. Wire execution engine and run.
        dag_manager = DAGManager(dag)
        runner = ParallelDAGRunner(
            dag_manager,
            executor_fn=lambda node: self._execute_node(node, dag),
            max_workers=self._max_workers,
        )
        runner.run()  # results embedded in dag_manager statuses

        # 5. Aggregate terminal statuses.
        statuses = dag_manager.get_statuses()
        nodes_completed = [nid for nid in node_ids if statuses.get(nid) == "success"]
        nodes_failed = [
            nid for nid in node_ids if statuses.get(nid) in ("failed", "error")
        ]
        nodes_skipped = [nid for nid in node_ids if statuses.get(nid) == "skipped"]

        overall = (
            "completed"
            if not nodes_failed and not nodes_skipped
            else "partial"
            if nodes_completed
            else "failed"
        )
        elapsed = time.monotonic() - start

        # 6. Persist final state.
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
        node_id: str = node["node_id"]
        task_description: str = node["task_description"]

        # Firewall: re-validate the generated task description before executing.
        ok, reason = self._firewall.validate_input(task_description)
        if not ok:
            self._otel.log_event(
                "node_blocked", {"node_id": node_id, "reason": reason}
            )
            return {"status": "error", "error": f"firewall_blocked: {reason}"}

        # Derive timeout from expected_duration or complexity metadata; default 120s.
        metadata = node.get("metadata", {})
        timeout_sec: int = int(
            metadata.get("expected_duration")
            or metadata.get("complexity")
            or 120
        )

        try:
            result = self._sandbox.execute(
                node_id,
                task_description,
                {"dag_metadata": dag.get("metadata", {})},
                timeout_sec=timeout_sec,
            )
            # === SEMANTIC REWARD JUDGE ===
            if result.get("status") == "success":
                passed, critique = self._reward_judge.judge(
                    stdout=result.get("output", ""),
                    task_description=node.get("task_description", ""),
                )
                if not passed:
                    result["status"] = "error"
                    result["error"] = f"[SEMANTIC FAILURE] {critique}\n" + result.get("error", "")
        except Exception as exc:
            compressed = self._compressor.compress_error(exc)
            self._otel.log_failure(node_id, exc, {"node": node, "trace": compressed})
            return {"status": "error", "error": compressed}

        # Drift detection: record outcome, abort branch on repeated anomalies.
        self._drift.record_node_result(node_id, result)
        if self._drift.loop_anomaly(node_id):
            self._otel.log_event(
                "drift_abort", {"node_id": node_id, "result": result}
            )
            logger.warning(
                "Drift loop anomaly detected on node %s — branch aborted", node_id
            )
            return {"status": "error", "error": "drift_loop_anomaly"}

        # Syntactic failure: subprocess exited non-zero or timed out.
        if result.get("status") != "success":
            analysis = self._compressor.compress_error(
                RuntimeError(result.get("error", "unknown"))
            )
            self._write_immunity_lesson(node_id, task_description, "SYNTACTIC", analysis)
            self._otel.log_failure(
                node_id,
                RuntimeError(result.get("error", "unknown")),
                {"result": result},
            )
            return result

        # Semantic validation: ensure output actually satisfies the task intent.
        stdout = result.get("output", "")
        semantic_score = self._semantic_reward_judge(stdout, task_description)
        if semantic_score == 0:
            analysis = self._compressor.compress_error(
                RuntimeError(
                    f"Semantic judge rejected output for task: {task_description[:120]}"
                )
            )
            self._write_immunity_lesson(node_id, task_description, "SEMANTIC", analysis)
            logger.warning(
                "Node %s passed syntactically but failed semantic judge", node_id
            )
            failed_result: dict[str, Any] = {
                "status": "error",
                "error": "semantic_judge_failed",
            }
            self._otel.log_failure(
                node_id,
                RuntimeError("semantic_judge_failed"),
                {"result": failed_result},
            )
            return failed_result

        return result

    def _semantic_reward_judge(self, stdout: str, task_description: str) -> int:
        """Returns 1 if stdout satisfies task_description, 0 if not. Fail-open on any exception."""
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=256,
                system=[
                    {
                        "type": "text",
                        "text": (
                            "You are a semantic verification judge. Your ONLY job is to evaluate "
                            "if the provided output actually solves the given task. Respond with "
                            "ONLY the digit 1 if the output solves the task, or ONLY the digit 0 "
                            "if it does not."
                        ),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"TASK: {task_description}\n\nOUTPUT:\n{stdout}",
                    }
                ],
            )
            text = response.content[0].text
            return 1 if "1" in text else 0
        except Exception:
            return 1

    def _write_immunity_lesson(
        self,
        node_id: str,
        task_description: str,
        failure_type: str,
        ast_analysis: str,
    ) -> None:
        lesson = (
            f"## IMMUNITY LESSON\n"
            f"- Node: {node_id}\n"
            f"- Task: {task_description}\n"
            f"- Failure Type: {failure_type}\n"
            f"- AST Analysis: {ast_analysis}\n"
            f"- Timestamp: {datetime.utcnow().isoformat()}\n"
        )
        lock_path = str(_LESSON_FILE) + ".lock"
        with FileLock(lock_path):
            with open(_LESSON_FILE, "a", encoding="utf-8") as fh:
                fh.write(lesson)
        logger.info(
            "Immunity lesson written — node=%s failure_type=%s", node_id, failure_type
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
        out: dict[str, Any] = {
            "status": status,
            "nodes_completed": nodes_completed,
            "nodes_failed": nodes_failed,
            "execution_time_sec": round(elapsed, 3),
        }
        if extra:
            out.update(extra)
        return out

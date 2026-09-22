# Swarm-Forge Orchestrator — Claude Code Constitution

## Project Identity
Swarm-Forge is a Meta-Agent orchestrator that ingests a natural-language enterprise problem, produces a validated DAG topology via the Anthropic API, and drives sandboxed multi-agent child swarms with zero-trust input validation, semantic reward judging, Boardroom HITL governance, and synaptic immunity memory.

## Stack
- Python 3.12 (strict type hints everywhere, `from __future__ import annotations`)
- FastMCP for MCP server generation (stdio transport)
- anthropic SDK: Opus 4.7 for planning, Sonnet 4.5 for reward judging, Haiku 4.5 for routing / planner fallback
- filelock for OS-level mutex state
- pydantic v2 for all schemas
- jinja2 for template hydration
- Subprocess-isolated sandbox execution (no Docker runtime dependency)

## Module Map — FINAL V2
All modules live in `src/` and are exported via `src/__init__.py`.

- `src/meta_orchestrator.py` — `MetaOrchestrator` wires all subsystems end-to-end.
- `src/dag_planner.py` — `plan_dag` emits a validated `DagPlan` via Opus 4.7 (Haiku fallback).
- `src/dag_execution_engine.py` — `DAGManager` + `ParallelDAGRunner` (DFS cycle check, Kahn bookkeeping, `ThreadPoolExecutor`).
- `src/execution_sandbox.py` — `SandboxExecutor` runs nodes in bounded-timeout subprocesses.
- `src/reward_judge.py` — `RewardSwarmJudge` adversarially verifies stdout against task_description.
- `src/zero_trust_firewall.py` — `AgentFirewall` compiled-regex blocklist for inputs and tool calls.
- `src/drift_metrics.py` — `DriftDetector` flags loop anomalies after N identical non-success outcomes.
- `src/ast_context_compressor.py` — `ASTContextCompressor` reduces tracebacks to the essential signal.
- `src/mutex_storage.py` — `SynchronizedJSONStore` (filelock-backed JSON persistence).
- `src/otel_telemetry_logger.py` — `HPFELogger` emits structured OTel-style records.
- `src/fastmcp_server.py` — FastMCP server exposing `plan_swarm`, `get_dag_status`, `validate_safety`.

Auxiliary modules at the repo root (`template_hydrator.py`, etc.) remain unchanged and are consumed by `demo.py`.

## Rules
- `ThreadPoolExecutor` is the sanctioned concurrency primitive for parallel DAG execution. Shared state must be protected by `filelock` or `threading.Lock`.
- NEVER hardcode API keys — always read from `os.environ["ANTHROPIC_API_KEY"]`.
- All file writes to shared state must go through `SynchronizedJSONStore` (or the `LESSON.md` lock in `MetaOrchestrator`).
- All tool calls must pass through `AgentFirewall.evaluate_tool_call()` before dispatch.
- Model routing: Opus 4.7 for DAG planning; Sonnet 4.5 for the reward judge; Haiku 4.5 for routing and planner fallback.
- Use prompt caching (`cache_control: {"type": "ephemeral"}`) on every static system prompt.
- Max tokens: 4096 for Opus calls, 2048 for planner, 1024 for Haiku routing, 512 for the reward judge.

## Professional-Grade Standards (enforced)
- Every module starts with a triple-quoted docstring: one-line summary, 2–3-sentence role, example, and the Swarm-Forge author line.
- Every public function/method carries complete Python 3.12 type hints (`list[str]`, `dict[str, Any]`) and a Google-style docstring.
- No `print()` calls in `src/`; every module uses `logging.getLogger(__name__)`. `demo.py` is the sole exception (user-facing ANSI output).
- No bare `except Exception`; every handler logs before handling.
- Magic numbers and model IDs live in `SCREAMING_SNAKE_CASE` module constants.
- Imports sorted into stdlib / third-party / local groups with blank-line separation.
- Package imports are relative (`from .reward_judge import ...`) inside `src/`.

## Commands
- Run demo: `python demo.py`
- Run import/wiring self-test: `python demo.py --test`
- Run tests: `pytest tests/ -v`
- Start MCP server: `python src/fastmcp_server.py`

## Never
- Do not rewrite existing module files unless fixing a bug or applying the professional-grade standards above.
- Do not add unnecessary dependencies. Every entry in `requirements.txt` must be pinned and justified by an inline comment.
- Do not use asyncio unless FastMCP requires it at a transport boundary.
- Do not reintroduce the legacy `_semantic_reward_judge` method on `MetaOrchestrator`. `RewardSwarmJudge` is the sole semantic verification mechanism.

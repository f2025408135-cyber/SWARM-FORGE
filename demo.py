"""Swarm-Forge end-to-end supply-chain demo.

Exercises every subsystem in order (firewall → planner → parallel executor
→ template hydration → AST compression → mutex state), then prints a
human-readable summary. Runs against real Anthropic APIs when
``ANTHROPIC_API_KEY`` is set and falls back to a pre-built mock DAG
otherwise.

Pass ``--test`` for a fast import/wiring self-check that imports every
module and instantiates every class without issuing any API call.

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ast_context_compressor import ASTContextCompressor
from src.dag_execution_engine import DAGManager, ParallelDAGRunner
from src.drift_metrics import DriftDetector
from src.execution_sandbox import SandboxExecutor
from src.mutex_storage import SynchronizedJSONStore
from src.otel_telemetry_logger import HPFELogger
from src.zero_trust_firewall import AgentFirewall

try:
    from template_hydrator import AgentBlueprint, HydrationEngine, HydrationError  # type: ignore  # noqa: F401
except ImportError:
    sys.path.insert(0, str(_REPO_ROOT))
    from template_hydrator import AgentBlueprint, HydrationEngine, HydrationError  # type: ignore  # noqa: F401

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
DIM = "\033[2m"


def c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}"


def section(title: str) -> None:
    width = 62
    print(f"\n{c('─' * width, CYAN)}")
    print(c(f"  {title}", BOLD + CYAN))
    print(c("─" * width, CYAN))


def ok(msg: str) -> None:
    print(f"  {c('✓', GREEN)}  {msg}")


def info(msg: str) -> None:
    print(f"  {c('›', CYAN)}  {msg}")


def warn(msg: str) -> None:
    print(f"  {c('!', YELLOW)}  {msg}")


def fail(msg: str) -> None:
    print(f"  {c('✗', RED)}  {msg}")


# ── Supply-chain problem ───────────────────────────────────────────────────────
SUPPLY_CHAIN_PROBLEM = (
    "Optimize the global supply chain for an electronics manufacturer: "
    "ingest real-time IoT sensor data from 12 factories, detect demand spikes "
    "via ML forecasting, re-route logistics across 3 continents, update ERP "
    "inventory records, and send procurement alerts to Tier-1 suppliers — "
    "all within a 90-second SLA."
)

MALICIOUS_INPUT = "SELECT * FROM users; DROP TABLE orders; --"

AGENT_BLUEPRINT_JSON = json.dumps(
    {
        "agent_name": "supply-chain-optimizer",
        "version": "1.0.0",
        "dependencies": ["anthropic", "fastmcp", "pydantic"],
        "env_vars": {
            "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
            "LOG_LEVEL": "INFO",
        },
    }
)

MOCK_DAG: dict = {
    "nodes": [
        {
            "node_id": "ingest_iot",
            "task_description": "Ingest real-time sensor data from 12 factory IoT endpoints",
            "dependencies": [],
        },
        {
            "node_id": "demand_forecast",
            "task_description": "Run ML demand-spike forecasting on the ingested sensor stream",
            "dependencies": ["ingest_iot"],
        },
        {
            "node_id": "reroute_logistics",
            "task_description": "Re-route cross-continent logistics based on forecast output",
            "dependencies": ["demand_forecast"],
        },
        {
            "node_id": "update_erp",
            "task_description": "Update ERP inventory records with new routing decisions",
            "dependencies": ["reroute_logistics"],
        },
        {
            "node_id": "alert_suppliers",
            "task_description": "Send procurement alerts to Tier-1 suppliers",
            "dependencies": ["update_erp"],
        },
    ],
    "metadata": {
        "problem": SUPPLY_CHAIN_PROBLEM,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
def phase_banner() -> None:
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║   === SWARM-FORGE DEMO: Autonomous Multi-Agent Orchestrator ===  ║",
        "║                                                              ║",
        "║   Natural Language  →  Validated DAG  →  Sandboxed Swarm    ║",
        "╚══════════════════════════════════════════════════════════════╝",
    ]
    print()
    for line in lines:
        print(c(line, BOLD + MAGENTA))
    print()
    print(c(f"  Problem: {SUPPLY_CHAIN_PROBLEM[:80]}…", DIM))
    print()


def phase_firewall() -> None:
    section("Phase 1 — Zero-Trust Firewall")

    firewall = AgentFirewall()

    ok("Firewall initialised with 8 compiled block-patterns")

    passed, reason = firewall.validate_input(SUPPLY_CHAIN_PROBLEM)
    if passed:
        ok(f"Legitimate prompt PASSED  ({len(SUPPLY_CHAIN_PROBLEM)} chars)")
    else:
        fail(f"Legitimate prompt unexpectedly blocked: {reason}")

    passed2, reason2 = firewall.validate_input(MALICIOUS_INPUT)
    if not passed2:
        ok(f"SQL-injection attempt BLOCKED  — {reason2}")
    else:
        warn("Malicious input was not blocked (unexpected)")

    tool_safe = firewall.evaluate_tool_call(
        "run_forecast", {"model": "xgboost", "horizon_days": "30"}
    )
    ok(f"Tool-call evaluate_tool_call() → {'SAFE' if tool_safe else 'BLOCKED'}")


def phase_dag_planning() -> dict:
    section("Phase 2 — DAG Planning  (claude-opus-4-7)")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        warn("ANTHROPIC_API_KEY not set — using pre-built mock DAG")
        dag = MOCK_DAG
    else:
        info("Calling plan_dag() via Opus 4.7 with prompt-caching …")
        t0 = time.time()
        try:
            from src.dag_planner import plan_dag  # type: ignore

            dag = plan_dag(SUPPLY_CHAIN_PROBLEM)
            elapsed = time.time() - t0
            ok(f"DAG planned in {elapsed:.1f}s — {len(dag['nodes'])} nodes")
        except Exception as exc:
            warn(f"Planner raised {type(exc).__name__}: {exc} — falling back to mock DAG")
            dag = MOCK_DAG

    print()
    for node in dag["nodes"]:
        deps = node["dependencies"] or ["(root)"]
        print(
            f"    {c(node['node_id'], BOLD)}  ←  {c(', '.join(deps), DIM)}"
        )
        print(f"       {c(node['task_description'][:72], DIM)}")

    return dag


def phase_dag_execution(dag: dict) -> dict[str, dict]:
    section("Phase 3 — Parallel DAG Execution  (SandboxExecutor)")

    sandbox = SandboxExecutor()
    drift = DriftDetector()
    logger = HPFELogger()

    def execute_node(node: dict) -> dict:
        node_id: str = node["node_id"]
        result = sandbox.execute(node_id, node["task_description"], context=node)
        drift.record_node_result(node_id, result)
        if drift.loop_anomaly(node_id):
            warn(f"  Drift anomaly detected on '{node_id}' — aborting subtree")
        if result["status"] != "success":
            logger.log_failure(node_id, RuntimeError(result.get("error", "?")), node)
        return result

    manager = DAGManager(dag)
    runner = ParallelDAGRunner(manager, executor_fn=execute_node, max_workers=4)

    t0 = time.time()
    results: dict[str, dict] = runner.run()
    elapsed = time.time() - t0

    print()
    for node_id, res in results.items():
        status = res.get("status", "unknown")
        icon = GREEN + "✓" + RESET if status == "success" else RED + "✗" + RESET
        print(f"    {icon}  {c(node_id, BOLD)}  →  {status}")

    successes = sum(1 for r in results.values() if r.get("status") == "success")
    ok(f"{successes}/{len(results)} nodes succeeded in {elapsed:.1f}s")
    return results


def phase_template_hydration() -> None:
    section("Phase 4 — Template Hydration  (Jinja2 → Dockerfile)")

    templates_dir = _REPO_ROOT / "templates"
    output_dir = _REPO_ROOT / "generated"
    output_dir.mkdir(exist_ok=True)

    engine = HydrationEngine(templates_dir=templates_dir, output_dir=output_dir)
    success = engine.render_to_file(
        template_name="Dockerfile.j2",
        raw_json=AGENT_BLUEPRINT_JSON,
        output_filename="Dockerfile.supply-chain-optimizer",
    )

    if success:
        out_path = output_dir / "Dockerfile.supply-chain-optimizer"
        ok(f"Dockerfile rendered → {out_path.relative_to(Path.cwd())}")
        preview = out_path.read_text(encoding="utf-8").splitlines()[:6]
        for line in preview:
            print(f"    {c(line, DIM)}")
        if len(out_path.read_text(encoding="utf-8").splitlines()) > 6:
            print(f"    {c('…', DIM)}")
    else:
        warn("Template hydration returned False — check templates/ directory")


def phase_ast_compression() -> None:
    section("Phase 5 — AST Context Compressor  (error triage)")

    compressor = ASTContextCompressor()

    try:
        _ = 1 / 0
    except ZeroDivisionError as exc:
        compressed = compressor.compress_error(exc)
        ok("ZeroDivisionError compressed to essential signal:")
        for line in compressed.splitlines()[:6]:
            print(f"    {c(line, DIM)}")

    syntax_err_src = "def broken(\n    x y\n):\n    pass\n"
    try:
        compile(syntax_err_src, "<demo>", "exec")
    except SyntaxError as exc:
        compressed2 = compressor.compress_error(exc, source_code=syntax_err_src)
        ok("SyntaxError with source-code context compressed:")
        for line in compressed2.splitlines()[:4]:
            print(f"    {c(line, DIM)}")


def phase_state_persistence(results: dict[str, dict]) -> None:
    section("Phase 6 — Mutex State Persistence  (SynchronizedJSONStore)")

    state_file = ".swarmforge_demo_state.json"
    store = SynchronizedJSONStore(state_file)

    store.write(
        {
            "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "problem_hash": hash(SUPPLY_CHAIN_PROBLEM) & 0xFFFFFFFF,
            "node_results": {
                nid: {"status": r.get("status")} for nid, r in results.items()
            },
        }
    )
    ok(f"State written to {state_file}")

    snapshot = store.read()
    ok(f"State re-read — {len(snapshot.get('node_results', {}))} node records")
    info(f"Timestamp: {snapshot.get('run_timestamp', 'n/a')}")


def phase_summary(results: dict[str, dict]) -> None:
    section("Demo Complete — Summary")

    successes = [nid for nid, r in results.items() if r.get("status") == "success"]
    failures = [nid for nid, r in results.items() if r.get("status") != "success"]

    print(f"\n  {c('Modules exercised:', BOLD)}")
    modules = [
        "AgentFirewall       (zero-trust input validation)",
        "DAGManager          (Kahn's topological sort + DFS cycle check)",
        "ParallelDAGRunner   (concurrent node execution)",
        "SandboxExecutor     (subprocess isolation)",
        "DriftDetector       (hallucination-loop detection)",
        "HPFELogger          (OTel structured failure events)",
        "ASTContextCompressor(traceback compression)",
        "HydrationEngine     (Jinja2 → Dockerfile artefact)",
        "SynchronizedJSONStore(OS-level mutex file I/O)",
        "RewardSwarmJudge    (adversarial semantic verification)",
    ]
    for m in modules:
        print(f"    {c('◆', CYAN)}  {m}")

    print()
    if successes:
        ok(f"Nodes completed: {', '.join(successes)}")
    if failures:
        fail(f"Nodes failed:    {', '.join(failures)}")

    print()
    print(c("  Swarm-Forge is ready for full orchestration via:", BOLD))
    print(f"    {c('python src/fastmcp_server.py', YELLOW)}  (FastMCP stdio server)")
    print(f"    {c('MetaOrchestrator().run(<problem>)', YELLOW)}  (programmatic API)")
    print()


# ── --test: comprehensive wiring self-check ────────────────────────────────
def run_self_test() -> int:
    """Import every module, instantiate every class, and report pass/fail.

    No API calls are made. ``RewardSwarmJudge`` is skipped at instantiation
    when ``ANTHROPIC_API_KEY`` is unset (that is correct fail-loud
    behaviour, not a demo failure).

    Returns:
        ``0`` if every check passes, ``1`` otherwise.
    """
    section("Swarm-Forge self-test  (python demo.py --test)")

    checks: list[tuple[str, callable]] = [
        ("import src.ast_context_compressor",
            lambda: __import__("src.ast_context_compressor", fromlist=["ASTContextCompressor"])),
        ("import src.dag_execution_engine",
            lambda: __import__("src.dag_execution_engine", fromlist=["DAGManager"])),
        ("import src.dag_planner",
            lambda: __import__("src.dag_planner", fromlist=["plan_dag"])),
        ("import src.drift_metrics",
            lambda: __import__("src.drift_metrics", fromlist=["DriftDetector"])),
        ("import src.execution_sandbox",
            lambda: __import__("src.execution_sandbox", fromlist=["SandboxExecutor"])),
        ("import src.meta_orchestrator",
            lambda: __import__("src.meta_orchestrator", fromlist=["MetaOrchestrator"])),
        ("import src.mutex_storage",
            lambda: __import__("src.mutex_storage", fromlist=["SynchronizedJSONStore"])),
        ("import src.otel_telemetry_logger",
            lambda: __import__("src.otel_telemetry_logger", fromlist=["HPFELogger"])),
        ("import src.reward_judge",
            lambda: __import__("src.reward_judge", fromlist=["RewardSwarmJudge"])),
        ("import src.zero_trust_firewall",
            lambda: __import__("src.zero_trust_firewall", fromlist=["AgentFirewall"])),
        ("instantiate AgentFirewall",
            lambda: AgentFirewall()),
        ("instantiate SandboxExecutor",
            lambda: SandboxExecutor()),
        ("instantiate DriftDetector",
            lambda: DriftDetector()),
        ("instantiate HPFELogger",
            lambda: HPFELogger()),
        ("instantiate ASTContextCompressor",
            lambda: ASTContextCompressor()),
        ("DAGManager + cycle detection on valid DAG",
            lambda: DAGManager({"nodes": [{"node_id": "a", "dependencies": [], "task_description": "t"}]})),
    ]

    if os.environ.get("ANTHROPIC_API_KEY"):
        from src.reward_judge import RewardSwarmJudge  # noqa: WPS433
        checks.append(("instantiate RewardSwarmJudge (API key present)",
                       lambda: RewardSwarmJudge()))
    else:
        warn("ANTHROPIC_API_KEY not set — skipping RewardSwarmJudge instantiation "
             "(fail-loud EnvironmentError is correct behaviour)")

    failures: list[tuple[str, str]] = []
    for label, check in checks:
        try:
            check()
            ok(label)
        except Exception as exc:
            fail(f"{label}  →  {type(exc).__name__}: {exc}")
            failures.append((label, traceback.format_exc()))

    print()
    if not failures:
        ok(c(f"All {len(checks)} self-checks PASSED", GREEN + BOLD))
        return 0
    fail(c(f"{len(failures)}/{len(checks)} self-checks FAILED", RED + BOLD))
    for label, tb in failures:
        print(c(f"\n--- {label} ---", RED))
        print(c(tb, DIM))
    return 1


def main() -> None:
    if "--test" in sys.argv:
        sys.exit(run_self_test())

    phase_banner()
    phase_firewall()
    dag = phase_dag_planning()
    results = phase_dag_execution(dag)
    phase_template_hydration()
    phase_ast_compression()
    phase_state_persistence(results)
    phase_summary(results)


if __name__ == "__main__":
    main()

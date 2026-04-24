`Swarm-Forge | Neo-AGI Orchestration | Python 3.12 | Anthropic`

# Swarm-Forge Orchestrator

Self-healing autonomous multi-agent DAG orchestrator — ingests enterprise problems, validates DAG topologies, and drives sandboxed child swarms through the Anthropic API with zero-trust input validation, semantic reward judging, Boardroom HITL governance, and synaptic immunity memory.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MetaOrchestrator                          │
│        (NL Input → Plan → Execute → Judge → Persist)         │
└─────────────────────────┬────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌─────▼─────┐     ┌─────▼─────┐
   │  DAG    │      │  FastMCP  │     │ AgentFire-│
   │ Planner │      │  Server   │     │ wall      │
   │  (Opus) │      │ (stdio)   │     │(Zero-Tru) │
   └────┬────┘      └─────┬─────┘     └─────┬─────┘
        │                 │                 │
   ┌────┴─────────────────┴─────────────────┴────┐
   │         ParallelDAGRunner (DFS + Kahn)      │
   │   + Boardroom HITL governance gate          │
   └────┬──────────────────────────────────┬─────┘
        │                                  │
   ┌────▼──────┐     ┌────────────┐   ┌────▼────────┐
   │ Sandbox   │     │ Reward-    │   │ Drift       │
   │ Executor  │────▶│ SwarmJudge │   │ Detector    │
   │ (subproc) │     │ (Sonnet)   │   │ (loop)      │
   └─────┬─────┘     └─────┬──────┘   └──────┬──────┘
         │                 │                 │
   ┌─────▼─────────────────▼─────────────────▼──────┐
   │ ASTContextCompressor │ SynchronizedJSONStore   │
   │ (traceback compress) │ (OS-level filelock)     │
   └─────────────────────┬────────────────────────┬─┘
                         │                        │
                   ┌─────▼─────┐          ┌───────▼───────┐
                   │ HPFELogger│          │ LESSON.md     │
                   │   (OTel)  │          │ (immunity)    │
                   └───────────┘          └───────────────┘
```

## Features

- **DFS Cycle Detection** — WHITE/GRAY/BLACK three-colour DFS rejects ill-formed DAGs at construction.
- **Parallel Execution** — `ThreadPoolExecutor` with a bounded worker pool drains the DAG at maximum concurrency.
- **Semantic Reward Judging** — `RewardSwarmJudge` invokes Claude Sonnet as an adversarial reviewer over sandbox stdout.
- **Boardroom HITL Governance** — nodes flagged `requires_approval` are gated behind a synchronous human prompt.
- **Synaptic Memory** — every semantic/syntactic failure is appended to `LESSON.md` under a file lock for cross-run immunity.
- **Zero-Trust Firewall** — compiled-regex blocklist vets every user prompt, generated task, and tool-call argument.
- **OS-Level Mutex Storage** — `filelock`-backed JSON store survives concurrent thread and process writers.
- **OTel-Style Telemetry** — structured `HPFELogger` records map directly onto OpenTelemetry log pipelines.

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env           # then edit .env and set ANTHROPIC_API_KEY
```

Python 3.12 is required. The SDK expects `ANTHROPIC_API_KEY` to be present in the environment for planner and reward-judge calls.

## Usage

```bash
# End-to-end supply chain demo (graceful mock-DAG fallback if no API key).
python demo.py

# Comprehensive import / wiring check across every module.
python demo.py --test

# Full test suite.
pytest tests/ -v

# Start the FastMCP stdio server for MCP-capable clients.
python src/fastmcp_server.py
```

Programmatic API:

```python
from src import MetaOrchestrator
result = MetaOrchestrator(max_workers=4).run("Decompose our Q2 migration plan.")
print(result["status"], result["execution_time_sec"])
```

## Module Reference

| Module                        | Purpose                                       | Key Class / Callable                 |
| ----------------------------- | --------------------------------------------- | ------------------------------------ |
| `meta_orchestrator.py`        | Master controller wiring all subsystems       | `MetaOrchestrator`                   |
| `dag_planner.py`              | NL problem → validated DAG JSON (Opus 4.7)    | `plan_dag`, `DagPlan`                |
| `dag_execution_engine.py`     | Kahn + DFS cycle check + parallel runner      | `DAGManager`, `ParallelDAGRunner`    |
| `execution_sandbox.py`        | Subprocess isolation with timeout             | `SandboxExecutor`                    |
| `reward_judge.py`             | Adversarial semantic verification of stdout   | `RewardSwarmJudge`                   |
| `zero_trust_firewall.py`      | Regex blocklist for inputs and tool calls     | `AgentFirewall`                      |
| `drift_metrics.py`            | Hallucination-loop detection                  | `DriftDetector`                      |
| `ast_context_compressor.py`   | Traceback → compressed diagnostic             | `ASTContextCompressor`               |
| `mutex_storage.py`            | OS-level file-locked JSON store               | `SynchronizedJSONStore`              |
| `otel_telemetry_logger.py`    | Structured OTel-style failure/event records   | `HPFELogger`                         |
| `fastmcp_server.py`           | FastMCP stdio server exposing swarm tools     | `plan_swarm`, `get_dag_status`, ...  |

## Model Pricing (per 1M tokens)

| Model      | Input  | Output |
| ---------- | ------ | ------ |
| Haiku 4.5  | $0.80  | $4.00  |
| Sonnet 4.5 | $3.00  | $15.00 |
| Opus 4.7   | $15.00 | $75.00 |

**Routing:** Opus 4.7 for DAG planning only; Sonnet 4.5 for the reward judge; Haiku 4.5 for routing and planner fallback.

## Contributing

1. Fork the repo and create a feature branch off `main`.
2. Run `pytest tests/ -v` and `python demo.py --test` locally before opening a PR.
3. Adhere to the professional-grade standards documented in `CLAUDE.md` (strict typing, Google-style docstrings, logger over `print`, module-level constants).
4. For any behavioural change, add or update a test case in `tests/test_swarm_forge.py`.

## License

MIT License. See the repository root for the full text. Third-party dependencies retain their original licenses as declared in `requirements.txt`.

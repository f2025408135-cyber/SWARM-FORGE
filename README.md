# Swarm-Forge

**Autonomous meta-orchestration engine that compiles natural language
enterprise problems into deployed multi-agent DAG child swarms.**

## Architecture
Natural Language Input
↓
TDAG Engine (Opus 4.7)
↓
DAG Topology + Budget Map
↓
Contract-First Compiler
(Pydantic schemas generated per edge)
↓
Template Hydrator (Jinja2 — zero API cost)
↓
FastMCP Server Generation
↓
Docker Factory → Kubernetes Deploy
↓
Self-Healing Loop (HPFE → RCA → Shadow Branch)
↓
Epistemic Compounding (LESSON.md → immune memory)

## Modules Built
| Module | Purpose |
|--------|---------|
| `mutex_storage.py` | OS-level mutex for 9-process concurrent file I/O |
| `dag_execution_engine.py` | Kahn's algorithm DAG with parallel ThreadPoolExecutor |
| `ast_context_compressor.py` | 6x token compression via AST serialization |
| `template_hydrator.py` | Jinja2 hydration engine (zero API cost code gen) |
| `otel_telemetry_logger.py` | OTel GenAI HPFE logging |
| `schemas.py` | Typed Pydantic contracts (zero natural language handoffs) |
| `circuit_breakers.py` | Fuse/Sentinel/Medic + ComputeAuditor |
| `memory_system.py` | LESSON.md + SKILL.md + Milvus episodic memory |

## Quick Start
```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY
pip install -r requirements.txt
pytest tests/ -v
```

## Hackathon
Built for the Anthropic Hackathon 2026. Core orchestration powered
by Claude Opus 4.6 via Claude Code CLI.

# Swarm-Forge Orchestrator

**Self-healing autonomous multi-agent DAG orchestrator** — Meta-agent system that ingests enterprise problems, validates DAG topologies, and spawns containerized child swarms via Anthropic APIs.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Meta-Orchestrator                      │
│           (NL Input → DAG Planning → Execution)         │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼────┐   ┌───▼────┐   ┌───▼────┐
    │ DAG     │   │FastMCP │   │ Firewall│
    │Planner  │   │ Server │   │ (Zero-  │
    │(Opus)   │   │        │   │ Trust)  │
    └────┬────┘   └───┬────┘   └───┬────┘
         │             │             │
    ┌────┴─────────────┴─────────────┴────┐
    │   DAG Execution Engine (Kahn)      │
    └────┬──────────────────────────────┬─┘
         │                              │
    ┌────▼──────┐  ┌────────────┐  ┌───▼────┐
    │ Sandbox   │  │ AST        │  │Drift   │
    │Executor   │  │Compressor  │  │Metrics │
    └─────┬─────┘  └────┬───────┘  └────┬───┘
          │             │                │
    ┌─────▼─────────────▼────────────────▼────┐
    │  Mutex Storage │ Template Hydrator      │
    │  (File Locking)│ (Jinja2)              │
    └────────────────┬───────────────────────┘
                     │
            ┌────────▼────────┐
            │   OTel Logging  │
            │   (Observability)
            └─────────────────┘
```

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# End-to-end demo
python demo.py

# Run test suite
pytest tests/ -v

# Start FastMCP server
python src/fastmcp_server.py
```

## Model Pricing (Per 1M Tokens)

| Model | Input | Output |
|-------|-------|--------|
| Haiku 4.5 | $0.80 | $4.00 |
| Sonnet 4.6 | $3.00 | $15.00 |
| Opus 4.7 | $15.00 | $75.00 |

**Routing:** Opus for DAG planning only; Haiku for routing/execution.

## Stack
- Python 3.12 + type hints
- FastMCP + Anthropic SDK
- Pydantic v2 schemas
- Jinja2 templates
- Docker sandboxing

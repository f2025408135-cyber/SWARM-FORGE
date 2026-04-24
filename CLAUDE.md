# Swarm-Forge Orchestrator — Claude Code Constitution

## Project Identity
This is Swarm-Forge: a Meta-Agent orchestrator that ingests a natural language 
enterprise problem, generates a validated DAG topology, and autonomously spawns 
containerized multi-agent child swarms using the Anthropic API and FastMCP.

## Stack
- Python 3.12 (strict type hints everywhere)
- FastMCP for MCP server generation
- anthropic SDK (claude-opus-4-7 for orchestration, claude-haiku-4-5 for routing)
- filelock for OS-level mutex
- pydantic v2 for all schemas
- jinja2 for template hydration
- docker for sandboxed execution

## Module Map (already built by prior agent — DO NOT rewrite these)
- src/ast_context_compressor.py — AST-based error context extraction
- src/mutex_storage.py — OS-level file locking for concurrent processes
- src/template_hydrator.py — Jinja2 template engine
- src/dag_execution_engine.py — Kahn's algorithm DAG runner
- src/otel_telemetry_logger.py — OTel failure logging
- src/zero_trust_firewall.py — Path/shell/PII validation
- src/drift_metrics.py — Hallucination loop detection
- src/execution_sandbox.py — Subprocess sandboxing

## What Needs Building
- src/meta_orchestrator.py — Window 0: wires all 8 modules, calls Anthropic API
- src/dag_planner.py — NL prompt → validated DAG JSON using claude-opus-4-7
- src/fastmcp_server.py — FastMCP server exposing swarm tools
- demo.py — End-to-end supply chain demo script
- templates/ — Jinja2 templates for Dockerfile, agent configs
- tests/ — Pytest suite

## Rules
- NEVER use threads. Use OS subprocesses only.
- NEVER hardcode API keys. Use os.environ.
- ALL file writes must go through SynchronizedJSONStore or SynchronizedSkillWriter.
- ALL tool calls must pass through AgentFirewall.evaluate_tool_call() first.
- Model routing: Opus 4.7 for DAG planning only. Haiku 4.5 for everything else.
- Use prompt caching (cache_control ephemeral) on all static system prompts.
- Max tokens for Opus calls: 4096. For Haiku: 1024.

## Commands
- Run demo: python demo.py
- Run tests: pytest tests/ -v
- Start MCP server: python src/fastmcp_server.py

## Never
- Do not rewrite existing module files unless fixing a bug.
- Do not add unnecessary dependencies.
- Do not use asyncio unless FastMCP requires it.

"""
FastMCP server exposing three swarm tools over the MCP protocol (stdio transport).

Tools:
  plan_swarm(problem)   — run MetaOrchestrator end-to-end, return JSON result
  get_dag_status()      — read .swarmforge_state.json, return current state
  validate_safety(payload) — run AgentFirewall checks, return SAFE / UNSAFE + reason
"""
from __future__ import annotations

import json
import os
import sys

# Make src/ importable when server is invoked directly.
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP

from meta_orchestrator import MetaOrchestrator
from mutex_storage import SynchronizedJSONStore
from zero_trust_firewall import AgentFirewall

_STATE_FILE = ".swarmforge_state.json"

mcp: FastMCP = FastMCP("swarm-forge")

_orchestrator = MetaOrchestrator()
_store = SynchronizedJSONStore(_STATE_FILE)
_firewall = AgentFirewall()


@mcp.tool()
def plan_swarm(problem: str) -> str:
    """Run the MetaOrchestrator on a natural-language problem and return the JSON result."""
    result = _orchestrator.run(problem)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_dag_status() -> str:
    """Return the current swarm state from .swarmforge_state.json as JSON."""
    state = _store.read()
    if not state:
        return json.dumps({"status": "no_state", "message": "State file not found or empty."})
    return json.dumps(state, indent=2)


@mcp.tool()
def validate_safety(payload: str) -> str:
    """Run AgentFirewall checks on an arbitrary payload string.

    Returns 'SAFE' or 'UNSAFE: <reason>'.
    """
    ok, reason = _firewall.validate_input(payload)
    if ok:
        return "SAFE"
    return f"UNSAFE: {reason}"


if __name__ == "__main__":
    mcp.run(transport="stdio")

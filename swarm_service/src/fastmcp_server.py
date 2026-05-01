"""FastMCP server — exposes Swarm-Forge tools over the MCP stdio transport.

Registers three tools on a :class:`FastMCP` instance:

  * ``plan_swarm(problem)``     — run MetaOrchestrator end-to-end, return JSON.
  * ``get_dag_status()``        — read ``.swarmforge_state.json``, return JSON.
  * ``validate_safety(payload)``— run AgentFirewall checks, return SAFE/UNSAFE.

When invoked as a script (``python src/fastmcp_server.py``), the server is
started on the stdio transport so that MCP-capable clients (Claude Desktop,
Cursor, etc.) can discover and call these tools directly.

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Final

_REPO_ROOT: Final[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mcp.server.fastmcp import FastMCP

from src.meta_orchestrator import MetaOrchestrator
from src.mutex_storage import SynchronizedJSONStore
from src.zero_trust_firewall import AgentFirewall

logger: logging.Logger = logging.getLogger(__name__)

STATE_FILE: Final[str] = ".swarmforge_state.json"
SERVER_NAME: Final[str] = "swarm-forge"
JSON_INDENT: Final[int] = 2

mcp: FastMCP = FastMCP(SERVER_NAME)

_orchestrator: MetaOrchestrator = MetaOrchestrator()
_store: SynchronizedJSONStore = SynchronizedJSONStore(STATE_FILE)
_firewall: AgentFirewall = AgentFirewall()


@mcp.tool()
def plan_swarm(problem: str) -> str:
    """Run the MetaOrchestrator on a natural-language problem.

    Args:
        problem: Free-text enterprise problem to decompose and execute.

    Returns:
        JSON-encoded orchestration result, indented for readability.
    """
    result: dict[str, object] = _orchestrator.run(problem)
    return json.dumps(result, indent=JSON_INDENT)


@mcp.tool()
def get_dag_status() -> str:
    """Return the current swarm state as JSON.

    Returns:
        JSON-encoded state from ``.swarmforge_state.json``, or a
        ``{"status": "no_state"}`` marker when the file is missing/empty.
    """
    state: dict[str, object] = _store.read()
    if not state:
        return json.dumps(
            {"status": "no_state", "message": "State file not found or empty."}
        )
    return json.dumps(state, indent=JSON_INDENT)


@mcp.tool()
def validate_safety(payload: str) -> str:
    """Run AgentFirewall checks on an arbitrary payload string.

    Args:
        payload: Arbitrary text to screen.

    Returns:
        The literal string ``"SAFE"`` on pass, or ``"UNSAFE: <reason>"``
        otherwise.
    """
    ok, reason = _firewall.validate_input(payload)
    if ok:
        return "SAFE"
    return f"UNSAFE: {reason}"


if __name__ == "__main__":
    mcp.run(transport="stdio")

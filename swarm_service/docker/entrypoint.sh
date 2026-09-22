#!/usr/bin/env bash
# Swarm-Forge container entrypoint — role dispatcher.
#
# Selects between the orchestrator demo, the FastMCP stdio server, or pytest
# based on the first positional argument (falling back to $SWARMFORGE_ROLE,
# defaulting to "orchestrator").

set -euo pipefail

ROLE="${1:-${SWARMFORGE_ROLE:-orchestrator}}"

case "${ROLE}" in
  orchestrator)
    exec python demo.py
    ;;
  mcp|fastmcp)
    exec python -m src.fastmcp_server
    ;;
  test|pytest)
    exec python -m pytest tests/ -v --tb=short
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "Unknown role: ${ROLE}" >&2
    echo "Usage: orchestrator | mcp | test | shell" >&2
    exit 64
    ;;
esac

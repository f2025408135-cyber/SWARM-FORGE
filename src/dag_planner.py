"""
DAG Planner: natural language enterprise problem → validated DAG JSON.
Uses claude-opus-4-7 for planning; claude-haiku-4-5-20251001 as fallback.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_OPUS_MODEL = "claude-opus-4-7"
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 2048

_SYSTEM_PROMPT = """\
You are a DAG planning engine for enterprise workflow orchestration.
Given a natural language problem description, output ONLY valid JSON — \
no markdown fences, no explanation, no prose before or after.

Required schema:
{
  "nodes": [
    {
      "node_id": "<unique snake_case string>",
      "task_description": "<what this node does, at least 10 characters>",
      "dependencies": ["<node_id of an upstream node, or empty list for root nodes>"]
    }
  ],
  "metadata": {
    "problem": "<original problem string verbatim>",
    "timestamp": "<ISO 8601 UTC timestamp>"
  }
}

Constraints:
- node_id values must be unique, lowercase snake_case identifiers.
- dependencies must only reference node_ids defined in the same nodes array.
- Root nodes (no predecessors) must have an empty dependencies list [].
- The graph MUST be acyclic (no dependency cycles allowed).
- Output ONLY the JSON object. Nothing else.
"""


# ── Pydantic validation models ─────────────────────────────────────────────

class DagNode(BaseModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    task_description: str = Field(min_length=10)
    dependencies: list[str] = Field(default_factory=list)


class DagMetadata(BaseModel):
    problem: str
    timestamp: str


class DagPlan(BaseModel):
    nodes: list[DagNode]
    metadata: DagMetadata

    @field_validator("nodes")
    @classmethod
    def _validate_dag_structure(cls, nodes: list[DagNode]) -> list[DagNode]:
        if not nodes:
            raise ValueError("DAG must contain at least one node")

        node_ids = {n.node_id for n in nodes}

        for node in nodes:
            for dep in node.dependencies:
                if dep not in node_ids:
                    raise ValueError(
                        f"Node '{node.node_id}' declares unknown dependency '{dep}'"
                    )

        # Cycle detection via Kahn's topological sort
        in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}
        adjacency: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for node in nodes:
            for dep in node.dependencies:
                adjacency[dep].append(node.node_id)
                in_degree[node.node_id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            nid = queue.pop()
            visited += 1
            for child in adjacency[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if visited != len(nodes):
            raise ValueError("DAG contains a cycle — dependency graph is not acyclic")

        return nodes


# ── Internal helpers ───────────────────────────────────────────────────────

def _build_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _call_model(client: anthropic.Anthropic, model: str, user_content: str) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def _parse_and_validate(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    # Strip accidental markdown fences if the model ignores the no-fence instruction
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0].strip()

    data = json.loads(stripped)
    plan = DagPlan.model_validate(data)
    return plan.model_dump()


# ── Public API ─────────────────────────────────────────────────────────────

def plan_dag(problem: str) -> dict[str, Any]:
    """Convert a natural language enterprise problem into a validated DAG dict.

    Retries once (with error context) if JSON parse/validation fails.
    Falls back to Haiku if the Opus API call itself raises an error.
    """
    client = _build_client()
    user_msg = f"Enterprise problem to decompose into a DAG:\n\n{problem}"

    using_fallback = False
    raw: str

    # Primary: Opus 4.7
    try:
        raw = _call_model(client, _OPUS_MODEL, user_msg)
    except anthropic.APIError as exc:
        logger.warning("Opus call failed (%s); falling back to Haiku", exc)
        using_fallback = True
        raw = _call_model(client, _HAIKU_MODEL, user_msg)

    # Parse + validate, with one retry on failure
    try:
        return _parse_and_validate(raw)
    except (json.JSONDecodeError, ValueError) as first_err:
        logger.warning("Parse/validation failed on first attempt: %s — retrying", first_err)

        retry_msg = (
            f"{user_msg}\n\n"
            f"Your previous response could not be parsed. Error: {first_err}\n"
            f"Rejected response was:\n{raw}\n\n"
            "Output ONLY valid JSON matching the required schema. "
            "No markdown fences, no prose, no explanation."
        )
        active_model = _HAIKU_MODEL if using_fallback else _OPUS_MODEL
        try:
            raw = _call_model(client, active_model, retry_msg)
            return _parse_and_validate(raw)
        except (json.JSONDecodeError, ValueError) as second_err:
            raise RuntimeError(
                f"DAG planning failed after retry.\n"
                f"Validation error: {second_err}\n"
                f"Last raw response:\n{raw}"
            ) from second_err

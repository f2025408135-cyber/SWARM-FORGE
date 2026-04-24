"""DAG planner — natural language enterprise problem to validated DAG JSON.

Calls the Anthropic API with a strict JSON-only system prompt, parses the
response against a Pydantic schema that enforces unique snake_case node
IDs, resolvable dependencies, and an acyclic graph (via Kahn's algorithm),
and returns a plain Python dict. Uses ``claude-opus-4-7`` as the primary
planner and falls back to ``claude-haiku-4-5-20251001`` if Opus itself
raises an API error. A single parse/validation retry is performed with
the rejected response fed back as error context.

Example:
    >>> dag = plan_dag("Parallelise our 6-step ETL across 3 warehouses.")
    >>> [n["node_id"] for n in dag["nodes"]]
    ['extract_salesforce', 'extract_stripe', ...]

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Final

import anthropic
from pydantic import BaseModel, Field, field_validator

logger: logging.Logger = logging.getLogger(__name__)

MODEL_OPUS: Final[str] = "claude-opus-4-7"
MODEL_HAIKU: Final[str] = "claude-haiku-4-5-20251001"
MAX_TOKENS: Final[int] = 2048
MIN_TASK_DESCRIPTION_LEN: Final[int] = 10
NODE_ID_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*$"
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"

_SYSTEM_PROMPT: Final[str] = """\
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


class DagNode(BaseModel):
    """A single node in a planned DAG.

    Attributes:
        node_id: Unique lowercase snake_case identifier.
        task_description: Human-readable task, at least 10 characters.
        dependencies: Upstream node_ids that must succeed before this node
            is eligible to execute.
    """

    node_id: str = Field(pattern=NODE_ID_PATTERN)
    task_description: str = Field(min_length=MIN_TASK_DESCRIPTION_LEN)
    dependencies: list[str] = Field(default_factory=list)


class DagMetadata(BaseModel):
    """Planner-emitted metadata describing the planning call.

    Attributes:
        problem: Verbatim copy of the original problem string.
        timestamp: ISO 8601 UTC timestamp of plan creation.
    """

    problem: str
    timestamp: str


class DagPlan(BaseModel):
    """Root schema for a validated DAG plan.

    Attributes:
        nodes: List of :class:`DagNode` entries forming the DAG.
        metadata: :class:`DagMetadata` for auditability.
    """

    nodes: list[DagNode]
    metadata: DagMetadata

    @field_validator("nodes")
    @classmethod
    def _validate_dag_structure(cls, nodes: list[DagNode]) -> list[DagNode]:
        """Enforce non-emptiness, dependency resolvability, and acyclicity.

        Args:
            nodes: Parsed node list to validate.

        Returns:
            The same node list if validation succeeds.

        Raises:
            ValueError: If the DAG is empty, references an unknown
                dependency, or contains a cycle.
        """
        if not nodes:
            raise ValueError("DAG must contain at least one node")

        node_ids: set[str] = {n.node_id for n in nodes}

        for node in nodes:
            for dep in node.dependencies:
                if dep not in node_ids:
                    raise ValueError(
                        f"Node '{node.node_id}' declares unknown dependency '{dep}'"
                    )

        in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}
        adjacency: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for node in nodes:
            for dep in node.dependencies:
                adjacency[dep].append(node.node_id)
                in_degree[node.node_id] += 1

        queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        visited: int = 0
        while queue:
            nid: str = queue.pop()
            visited += 1
            for child in adjacency[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if visited != len(nodes):
            raise ValueError(
                "DAG contains a cycle — dependency graph is not acyclic"
            )

        return nodes


def _build_client() -> anthropic.Anthropic:
    """Construct an authenticated Anthropic client from the environment.

    Returns:
        A ready-to-use :class:`anthropic.Anthropic` instance.

    Raises:
        EnvironmentError: If ``ANTHROPIC_API_KEY`` is not set.
    """
    api_key: str | None = os.environ.get(ENV_API_KEY)
    if not api_key:
        raise EnvironmentError(
            f"{ENV_API_KEY} environment variable is not set"
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_model(
    client: anthropic.Anthropic, model: str, user_content: str
) -> str:
    """Issue a single ``messages.create`` call and return the text response.

    Args:
        client: Authenticated Anthropic client.
        model: Model ID to route to.
        user_content: User message content.

    Returns:
        The first text block of the response.
    """
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
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
    """Strip markdown fences, parse JSON, and run Pydantic validation.

    Args:
        raw: Raw model response text.

    Returns:
        A plain dict representation of the validated DAG plan.

    Raises:
        json.JSONDecodeError: If the stripped payload is not valid JSON.
        ValueError: If the parsed data fails Pydantic validation.
    """
    stripped: str = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0].strip()

    data: Any = json.loads(stripped)
    plan: DagPlan = DagPlan.model_validate(data)
    return plan.model_dump()


def plan_dag(problem: str) -> dict[str, Any]:
    """Convert a natural language enterprise problem into a validated DAG dict.

    Retries once with error context if JSON parse/validation fails; falls
    back to Haiku if the Opus API call itself raises an error.

    Args:
        problem: Free-text enterprise problem description.

    Returns:
        A validated DAG dict with ``nodes`` and ``metadata`` keys.

    Raises:
        EnvironmentError: If ``ANTHROPIC_API_KEY`` is not set.
        RuntimeError: If planning fails even after the retry.
    """
    client: anthropic.Anthropic = _build_client()
    user_msg: str = f"Enterprise problem to decompose into a DAG:\n\n{problem}"

    using_fallback: bool = False
    raw: str

    try:
        raw = _call_model(client, MODEL_OPUS, user_msg)
    except anthropic.APIError as exc:
        logger.warning("Opus call failed (%s); falling back to Haiku", exc)
        using_fallback = True
        raw = _call_model(client, MODEL_HAIKU, user_msg)

    try:
        return _parse_and_validate(raw)
    except (json.JSONDecodeError, ValueError) as first_err:
        logger.warning(
            "Parse/validation failed on first attempt: %s — retrying", first_err
        )

        retry_msg: str = (
            f"{user_msg}\n\n"
            f"Your previous response could not be parsed. Error: {first_err}\n"
            f"Rejected response was:\n{raw}\n\n"
            "Output ONLY valid JSON matching the required schema. "
            "No markdown fences, no prose, no explanation."
        )
        active_model: str = MODEL_HAIKU if using_fallback else MODEL_OPUS
        try:
            raw = _call_model(client, active_model, retry_msg)
            return _parse_and_validate(raw)
        except (json.JSONDecodeError, ValueError) as second_err:
            logger.error("DAG planning failed after retry: %s", second_err)
            raise RuntimeError(
                f"DAG planning failed after retry.\n"
                f"Validation error: {second_err}\n"
                f"Last raw response:\n{raw}"
            ) from second_err

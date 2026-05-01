"""Base agent primitive for the SWARM-FORGE multi-agent orchestration system.

Provides a thin, retry-hardened wrapper around the Anthropic Messages API.
Each ``BaseAgent`` instance represents a single role-bound node inside the
execution DAG, carrying its own system prompt, context window, and model
selector.  The ``AgentResult`` dataclass offers a serialisable record of
every invocation suitable for downstream telemetry consumers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic

logger: logging.Logger = logging.getLogger(__name__)

_DEFAULT_MODEL: str = "claude-sonnet-4-5"
_MAX_TOKENS: int = 2048
_RETRY_ATTEMPTS: int = 3
_RETRY_BACKOFF: float = 2.0


# ---------------------------------------------------------------------------
# Serialisable result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentResult:
    """Immutable snapshot of a single agent invocation.

    Attributes
    ----------
    node_id:
        Unique identifier of the agent inside the DAG topology.
    role:
        Human-readable role string (e.g. ``"code-reviewer"``).
    task:
        The task prompt that was submitted to the LLM.
    output:
        Raw text returned by the model on success, or an empty string on
        failure.
    success:
        ``True`` when the API call completed without raising an exception.
    error_message:
        ``None`` on success; a human-readable error description on failure.
    execution_time_seconds:
        Wall-clock duration of the entire ``run()`` cycle, including retries.
    """

    node_id: str
    role: str
    task: str
    output: str
    success: bool
    error_message: str | None
    execution_time_seconds: float


# ---------------------------------------------------------------------------
# Core agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Single-node agent backed by the Anthropic Messages API.

    Parameters
    ----------
    node_id:
        Unique identifier for this agent within the orchestration graph.
    role:
        Functional role description injected into the system prompt.
    task:
        Primary task instruction forwarded to the language model.
    context:
        Optional key-value pairs rendered into a readable context block
        before the task prompt.
    model:
        Anthropic model identifier.  Defaults to ``claude-sonnet-4-5``.
    """

    def __init__(
        self,
        node_id: str,
        role: str,
        task: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> None:
        self.node_id: str = node_id
        self.role: str = role
        self.task: str = task
        self.context: dict[str, Any] = context if context is not None else {}
        self.model: str = model if model is not None else _DEFAULT_MODEL

    # -- prompt construction -------------------------------------------------

    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent.

        Returns
        -------
        str
            Formatted as ``"You are a {role} agent. Task: {task}. Be concise
            and structured."``
        """
        return f"You are a {self.role} agent. Task: {self.task}. Be concise and structured."

    def format_context(self) -> str:
        """Render ``self.context`` into a human-readable multi-line string.

        Each key-value pair is formatted as ``"<key>: <value>"`` on its own
        line.  An empty context dict yields an empty string.

        Returns
        -------
        str
            Newline-separated ``"key: value"`` pairs, or ``""`` when the
            context is empty.
        """
        if not self.context:
            return ""

        lines: list[str] = []
        for key, value in self.context.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    # -- execution -----------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Call the Anthropic Messages API with retry logic.

        The request is constructed with:

        * ``model`` set to ``self.model``
        * ``max_tokens`` set to ``2048``
        * ``system`` from :meth:`get_system_prompt`
        * ``messages`` containing a single ``user`` message composed of the
          formatted context (if any) followed by the task text.
        * No ``temperature``, ``top_p``, or ``top_k`` parameters are sent.

        Retries
        -------
        On any ``Exception`` the call is retried up to 3 total attempts with
        a fixed 2-second sleep between attempts.

        Returns
        -------
        dict
            ``{"success": bool, "output": str, "error": str | None,
            "execution_time": float}``
        """
        start_time: float = time.monotonic()

        system_prompt: str = self.get_system_prompt()
        context_block: str = self.format_context()

        # Build the user message: optional context preamble + task
        if context_block:
            user_content: str = f"{context_block}\n\n{self.task}"
        else:
            user_content = self.task

        last_error: str | None = None
        output: str = ""

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                client: anthropic.Anthropic = anthropic.Anthropic()
                response = client.messages.create(
                    model=self.model,
                    max_tokens=_MAX_TOKENS,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_content},
                    ],
                )

                # Extract text from the first content block
                if response.content and isinstance(response.content, list):
                    text_blocks: list[str] = [
                        block.text
                        for block in response.content
                        if block.type == "text"
                    ]
                    output = "\n".join(text_blocks)
                elif isinstance(response.content, str):
                    output = response.content

                elapsed: float = time.monotonic() - start_time
                logger.info(
                    "Agent '%s' (%s) completed in %.3fs on attempt %d",
                    self.node_id,
                    self.role,
                    elapsed,
                    attempt,
                )
                return {
                    "success": True,
                    "output": output,
                    "error": None,
                    "execution_time": elapsed,
                }

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Agent '%s' attempt %d/%d failed: %s",
                    self.node_id,
                    attempt,
                    _RETRY_ATTEMPTS,
                    last_error,
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_BACKOFF)

        elapsed = time.monotonic() - start_time
        logger.error(
            "Agent '%s' (%s) exhausted all %d attempts in %.3fs",
            self.node_id,
            self.role,
            _RETRY_ATTEMPTS,
            elapsed,
        )
        return {
            "success": False,
            "output": output,
            "error": last_error,
            "execution_time": elapsed,
        }

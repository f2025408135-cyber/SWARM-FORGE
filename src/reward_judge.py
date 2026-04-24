"""Semantic reward judge — adversarial verification of sandbox stdout.

Provides :class:`RewardSwarmJudge`, which evaluates whether the stdout
produced by a DAG node genuinely proves that the associated task
description was solved. The judge is intentionally strict: it treats
syntactic success (exit code 0, non-empty stdout) as insufficient and
demands observable evidence of the intended outcome in the stdout text.

Scoring protocol:
    The judge returns a tuple ``(passed: bool, critique: str)``.

    * ``passed=True, critique=""``        — stdout proves the task is solved.
    * ``passed=False, critique="<why>"``  — stdout does NOT prove the task
      is solved; the critique explains the specific gap.

    Under the hood the adversarial reviewer returns strict JSON of the form
    ``{"score": 0|1, "critique": "..."}`` which is parsed back into the
    public tuple shape.

Fail-open policy:
    Transient Anthropic API errors, network failures, and other unexpected
    exceptions deliberately fail *open* (return ``(True, "")``) so that
    transient judge unavailability cannot block an otherwise-healthy
    orchestration run. JSON parse failures fail *closed* because an
    unparseable verdict is evidence of judge misbehaviour that the caller
    should investigate. See :meth:`judge` for the full matrix.

Example:
    >>> judge = RewardSwarmJudge()
    >>> passed, critique = judge.judge(
    ...     stdout="Computed 12 invoices; total = $143,200.",
    ...     task_description="Compute the total of every invoice in Q1.",
    ... )

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Final

import anthropic

logger: logging.Logger = logging.getLogger(__name__)

MODEL_OPUS: Final[str] = "claude-opus-4-7"
MODEL_SONNET: Final[str] = "claude-sonnet-4-5"
MAX_TOKENS: Final[int] = 512
CRITIQUE_PREVIEW_LEN: Final[int] = 200
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"

_SYSTEM_PROMPT: Final[str] = (
    "You are a ruthless Adversarial Code Reviewer. Your job is to evaluate "
    "whether the provided stdout output genuinely proves that the given "
    "task_description was solved. Be strict. Output ONLY valid JSON with no "
    "markdown, no code blocks, no explanation outside JSON. Format: "
    '{"score": 1, "critique": ""} for pass, or '
    '{"score": 0, "critique": "detailed reason for failure"} for failure.'
)


class RewardSwarmJudge:
    """Adversarial semantic verifier for sandbox stdout.

    The judge calls an Anthropic Claude model with a strict adversarial
    system prompt and parses the resulting JSON verdict. It is designed to
    be invoked *after* syntactic success (exit code 0) to catch the
    "hollow-success" failure mode where a subprocess exits cleanly without
    actually solving the task.

    Attributes:
        _client: Authenticated Anthropic client.
        _model: Model ID to route judgement calls to.
    """

    def __init__(self, use_opus: bool = False) -> None:
        """Initialise the judge and verify API credentials at construction time.

        Performs an early warmup check on ``ANTHROPIC_API_KEY`` so that a
        missing key fails loudly at orchestrator startup rather than on the
        first node completion deep inside a DAG run.

        Args:
            use_opus: When True, route judgement calls to Opus 4.7 (higher
                quality, higher cost). When False, route to Sonnet 4.5
                (balanced default).

        Raises:
            EnvironmentError: If ``ANTHROPIC_API_KEY`` is not set.
        """
        api_key: str | None = os.environ.get(ENV_API_KEY)
        if not api_key:
            raise EnvironmentError(
                f"{ENV_API_KEY} environment variable is not set"
            )
        self._client: anthropic.Anthropic = anthropic.Anthropic(api_key=api_key)
        self._model: str = MODEL_OPUS if use_opus else MODEL_SONNET
        logger.debug("RewardSwarmJudge initialised with model=%s", self._model)

    def judge(self, stdout: str, task_description: str) -> tuple[bool, str]:
        """Evaluate whether *stdout* proves *task_description* was solved.

        Fail-open policy matrix:
            * Success + valid JSON  → return the verdict verbatim.
            * Unparseable JSON      → fail *closed* ``(False, "<preview>")``.
            * Anthropic APIError    → fail *open* ``(True, "")``.
            * Any other Exception   → fail *open* ``(True, "")``.

        Rationale: judge unavailability must not cascade-fail healthy runs,
        but a judge that replies with garbage is a correctness signal the
        caller should surface.

        Args:
            stdout: The stdout text captured from the sandbox subprocess.
            task_description: Human-readable task the node was meant to solve.

        Returns:
            A tuple ``(passed, critique)`` where ``passed`` is True when the
            stdout is judged to prove the task was solved, and ``critique``
            is a human-readable explanation of any gap (empty string on pass).
        """
        response_text: str = ""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"TASK DESCRIPTION:\n{task_description}\n\n"
                            f"SANDBOX STDOUT:\n{stdout}"
                        ),
                    }
                ],
            )
            response_text = response.content[0].text.strip()
            data: dict[str, object] = json.loads(response_text)
            passed: bool = bool(data.get("score", 0) == 1)
            critique: str = str(data.get("critique", ""))
            return passed, critique
        except json.JSONDecodeError as exc:
            logger.warning(
                "Reward judge returned unparseable JSON (%s): %s",
                exc,
                response_text[:CRITIQUE_PREVIEW_LEN],
            )
            return False, (
                f"Judge returned unparseable response: "
                f"{response_text[:CRITIQUE_PREVIEW_LEN]}"
            )
        except anthropic.APIError as exc:
            logger.warning("Reward judge API error — failing open: %s", exc)
            return True, ""
        except Exception as exc:
            logger.warning(
                "Reward judge unexpected error — failing open: %s", exc
            )
            return True, ""

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

Fail-closed policy:
    Transient Anthropic API errors and rate limits trigger exponential-backoff
    retry (up to 3 attempts). If retries are exhausted, or any other
    unexpected exception occurs, the judge fails *closed* — returning
    ``(False, <reason>)`` — so broken or unverifiable code never bypasses
    semantic verification. JSON parse failures also fail closed. See
    :meth:`judge` for the full matrix.

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
import time
from typing import Final

import anthropic

logger: logging.Logger = logging.getLogger(__name__)

MODEL_OPUS: Final[str] = "claude-opus-4-7"
MODEL_SONNET: Final[str] = "claude-sonnet-4-5"
MAX_TOKENS: Final[int] = 512
CRITIQUE_PREVIEW_LEN: Final[int] = 200
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"
JUDGE_MAX_ATTEMPTS: Final[int] = 3

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

        Fail-closed policy matrix:
            * Success + valid JSON           → return the verdict verbatim.
            * Anthropic APIError / RateLimit → exponential-backoff retry
              (``2 ** attempt`` seconds) up to ``JUDGE_MAX_ATTEMPTS`` times;
              on exhaustion return ``(False, "API unavailable ...")``.
            * Unparseable JSON               → fail closed with the preview.
            * Any other Exception            → fail closed.

        Rationale: Zero-Trust security requires that judge unavailability
        NEVER lets unverified code through. Under no exception branch does
        this method return ``(True, "")``.

        Args:
            stdout: The stdout text captured from the sandbox subprocess.
            task_description: Human-readable task the node was meant to solve.

        Returns:
            A tuple ``(passed, critique)`` where ``passed`` is True when the
            stdout is judged to prove the task was solved, and ``critique``
            is a human-readable explanation of any gap (empty string on pass).
        """
        response_text: str = ""
        for attempt in range(JUDGE_MAX_ATTEMPTS):
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
                parse_text = response_text
                if parse_text.startswith("```"):
                    parse_text = parse_text.split("\n", 1)[1]
                    parse_text = parse_text.rsplit("```", 1)[0].strip()
                data: dict[str, object] = json.loads(parse_text)
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
            except (anthropic.APIError, anthropic.RateLimitError) as exc:
                backoff: int = 2 ** attempt
                logger.warning(
                    "Reward judge API error (attempt %d/%d) — retrying in %ds: %s",
                    attempt + 1,
                    JUDGE_MAX_ATTEMPTS,
                    backoff,
                    exc,
                )
                time.sleep(backoff)
                continue
            except Exception as exc:
                logger.error(
                    "Reward judge unexpected error — failing closed: %s", exc
                )
                return False, (
                    "Unexpected error in judge. Failing closed for "
                    "Zero-Trust security."
                )

        logger.error(
            "Reward judge API unavailable after %d attempts — failing closed.",
            JUDGE_MAX_ATTEMPTS,
        )
        return False, (
            f"API unavailable after {JUDGE_MAX_ATTEMPTS} retries. "
            f"Failing closed for Zero-Trust security."
        )

"""Zero-trust firewall — the unified AgentGuard entrypoint for input triage.

Screens every free-text string entering the orchestrator (user prompts,
planner-emitted task descriptions, tool-call string arguments) through
a four-stage pipeline:

* Length guard: reject inputs over :data:`INPUT_MAX_LEN` characters.
* Layer 0 (regex blocklist): compiled-regex patterns for destructive shell,
  SQL injection, and code-execution signatures — the fast-path rejection.
* Layer 2 (:class:`CognitiveFirewall`): deterministic memory-taint heuristics
  (unicode smuggling, imperative overrides, Base64 exfil, etc.).
* Layer 3 (:class:`ActionFirewallVisitor`): AST capability-dropping — only
  invoked when the input parses as Python *and* contains imports or defs
  (the heuristic avoids false positives on prose that happens to parse).

Layer 1 (:class:`GeometricDOMSanitizer`) is not invoked here because it is
async, Playwright-backed, and returns a *transformed* HTML string rather
than a pass/fail verdict. Callers with HTML payloads should apply Layer 1
at the scraper boundary before handing content to :meth:`validate_input`.

Example:
    >>> AgentFirewall().validate_input("rm -rf /")
    (False, "input matches blocked pattern: 'rm\\\\s+-rf'")

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import ast
import logging
import re
from typing import Any, Final

from .agent_guard import CognitiveFirewall, verify_agent_action

logger: logging.Logger = logging.getLogger(__name__)

INPUT_MAX_LEN: Final[int] = 10_000

_BLOCKED_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\beval\s*\("),
    re.compile(r"__import__\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"subprocess\.(?:call|Popen|run)\s*\(\s*['\"]"),
    re.compile(r"curl\s+.*\|\s*(?:sh|bash)", re.IGNORECASE),
]

_CODE_LIKE_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


class AgentFirewall:
    """Unified zero-trust middleware calling Layer 0 / 2 / 3 in sequence.

    Stateless from the caller's perspective; internally holds a pre-compiled
    :class:`CognitiveFirewall`. Safe to share across threads.
    """

    def __init__(self) -> None:
        """Pre-compile the Layer-2 :class:`CognitiveFirewall` automata."""
        self._cognitive: CognitiveFirewall = CognitiveFirewall()

    def validate_input(self, text: str) -> tuple[bool, str]:
        """Run the full four-stage pipeline on *text*.

        Args:
            text: Arbitrary free-text input to screen.

        Returns:
            Tuple ``(ok, reason)`` where ``ok`` is True when the text
            passes every stage. On rejection, ``reason`` is a stable
            machine-readable description prefixed with the stage that
            rejected the payload.
        """
        if len(text) > INPUT_MAX_LEN:
            return False, f"input exceeds maximum length ({INPUT_MAX_LEN})"

        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                return False, f"input matches blocked pattern: {pattern.pattern!r}"

        tainted, reason = self._cognitive.is_tainted(text)
        if tainted:
            logger.warning("AgentFirewall: Layer-2 rejection — %s", reason)
            return False, f"cognitive_firewall: {reason}"

        if self._looks_like_python(text):
            safe, reason = verify_agent_action(text)
            if not safe:
                logger.warning("AgentFirewall: Layer-3 rejection — %s", reason)
                return False, f"action_firewall: {reason}"

        return True, ""

    def evaluate_tool_call(
        self, tool_name: str, args: dict[str, Any]
    ) -> bool:
        """Screen every string-valued argument of a tool call.

        Args:
            tool_name: Name of the tool being invoked (for logging hooks).
            args: Mapping of argument names to values; non-string values
                are skipped.

        Returns:
            True if every string argument passes :meth:`validate_input`.
        """
        for value in args.values():
            if isinstance(value, str):
                ok, reason = self.validate_input(value)
                if not ok:
                    logger.warning(
                        "Tool call %s blocked by firewall: %s", tool_name, reason
                    )
                    return False
        return True

    @staticmethod
    def _looks_like_python(text: str) -> bool:
        """Heuristically decide whether *text* is Python source code.

        The heuristic is intentionally conservative: we only treat *text*
        as code when it parses cleanly AND contains at least one Import,
        FunctionDef, or ClassDef node. Bare expressions (``"hello"``) and
        prose that accidentally parses are NOT routed through Layer 3 to
        prevent false positives on task-description inputs.

        Args:
            text: Candidate input string.

        Returns:
            True when Layer 3 enforcement should run on *text*.
        """
        try:
            tree: ast.AST = ast.parse(text, mode="exec")
        except (SyntaxError, ValueError):
            return False
        return any(isinstance(node, _CODE_LIKE_NODES) for node in ast.walk(tree))

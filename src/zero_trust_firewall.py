"""Zero-trust firewall — screens inputs and tool calls against an allowlist-free blocklist.

Every free-text string entering the orchestrator (user prompt, generated
task description, tool-call string argument) is checked against a set of
compiled regex patterns that flag destructive shell, SQL-injection, and
code-execution signatures. A match returns a structured ``(False, reason)``
tuple so that callers can log the rejection deterministically.

Example:
    >>> AgentFirewall().validate_input("rm -rf /")
    (False, "input matches blocked pattern: 'rm\\\\s+-rf'")

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Final

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


class AgentFirewall:
    """Compiled-regex blocklist for untrusted text and tool-call arguments.

    Stateless. Safe to share across threads.
    """

    def validate_input(self, text: str) -> tuple[bool, str]:
        """Check *text* against length and pattern blocklists.

        Args:
            text: Arbitrary free-text input to screen.

        Returns:
            Tuple ``(ok, reason)`` where ``ok`` is True when the text
            passes every check. On rejection, ``reason`` is a stable
            machine-readable description.
        """
        if len(text) > INPUT_MAX_LEN:
            return False, f"input exceeds maximum length ({INPUT_MAX_LEN})"
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                return False, f"input matches blocked pattern: {pattern.pattern!r}"
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

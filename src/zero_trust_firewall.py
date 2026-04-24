"""
Zero-trust firewall: validates inputs, paths, and tool calls against blocklists.
"""
from __future__ import annotations

import re
from typing import Any

_INPUT_MAX_LEN = 10_000

_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
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
    def validate_input(self, text: str) -> tuple[bool, str]:
        if len(text) > _INPUT_MAX_LEN:
            return False, f"input exceeds maximum length ({_INPUT_MAX_LEN})"
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                return False, f"input matches blocked pattern: {pattern.pattern!r}"
        return True, ""

    def evaluate_tool_call(self, tool_name: str, args: dict[str, Any]) -> bool:
        for value in args.values():
            if isinstance(value, str):
                ok, _ = self.validate_input(value)
                if not ok:
                    return False
        return True

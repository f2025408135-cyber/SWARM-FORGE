"""Zero-Trust Firewall middleware for autonomous AI agent orchestration.

Intercepts all intended agent actions (file I/O, shell execution, arbitrary
tool calls) and evaluates them against strict security heuristics before
execution.  Destructive commands, directory-traversal escapes, and PII
leaks are blocked deterministically without relying on any external SDK.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class SecurityViolationError(Exception):
    """Raised when an agent action violates the zero-trust policy.

    Attributes
    ----------
    reason:
        Human-readable description of the specific violation.
    tool_name:
        The tool / action that was evaluated.
    """

    def __init__(self, reason: str, tool_name: str = "") -> None:
        self.reason: str = reason
        self.tool_name: str = tool_name
        super().__init__(f"[SECURITY BLOCK] tool='{tool_name}' — {reason}")


# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------

class AgentFirewall:
    """Deterministic, rule-based security gate for AI agent actions.

    Every call to :meth:`evaluate_tool_call` runs the request through
    path-traversal, destructive-command, and PII-detection checks.
    Any failure immediately raises :class:`SecurityViolationError`.

    Parameters
    ----------
    allowed_directories:
        **Absolute** paths the agent is permitted to read from or write
        to.  All file-path arguments are resolved and checked against this
        allow-list.
    """

    # -- Regex patterns (compiled once at class level) ----------------------

    # Destructive shell commands
    _RE_RM_RF: re.Pattern[str] = re.compile(
        r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*[a-zA-Z]f)\b",
        re.IGNORECASE,
    )
    _RE_MKFS: re.Pattern[str] = re.compile(r"\bmkfs\b", re.IGNORECASE)
    _RE_CHMOD_777: re.Pattern[str] = re.compile(
        r"\bchmod\s+777\b", re.IGNORECASE,
    )
    _RE_CHOWN: re.Pattern[str] = re.compile(r"\bchown\b", re.IGNORECASE)
    _RE_DD: re.Pattern[str] = re.compile(
        r"\bdd\s+(?:if|of|bs|count|skip|seek)\s*=",
        re.IGNORECASE,
    )
    _RE_REDIR_OUT: re.Pattern[str] = re.compile(
        r"(?:^|\s|\||;|&&|\|\|)\s*(?:>|>>)\s",
    )
    _RE_PIPE_BASH: re.Pattern[str] = re.compile(
        r"(?:curl|wget)\b.*\|\s*(?:ba)?sh\b",
        re.IGNORECASE,
    )
    _RE_KILL_PROCESS: re.Pattern[str] = re.compile(
        r"\b(?:kill\s+-9|pkill|xkill|killall)\b",
        re.IGNORECASE,
    )
    _RE_SHUTDOWN: re.Pattern[str] = re.compile(
        r"\b(?:shutdown|reboot|halt|poweroff|init\s+[06])\b",
        re.IGNORECASE,
    )
    _RE_CRONTAB: re.Pattern[str] = re.compile(r"\bcrontab\b", re.IGNORECASE)
    _RE_IPTABLES: re.Pattern[str] = re.compile(
        r"\biptables\b", re.IGNORECASE,
    )
    _RE_SUDO_RM: re.Pattern[str] = re.compile(
        r"\bsudo\s+.*\brm\b", re.IGNORECASE,
    )
    _RE_PASSWD: re.Pattern[str] = re.compile(
        r"\b(?:passwd|shadow|group)\b",
        re.IGNORECASE,
    )

    # PII detection
    _RE_CREDIT_CARD: re.Pattern[str] = re.compile(
        r"\b(?:\d[ -]*?){13,16}\b",
    )
    _RE_SSN: re.Pattern[str] = re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b",
    )

    # Sensitive path fragments (checked after resolve)
    _SENSITIVE_FRAGMENTS: frozenset[str] = frozenset({
        ".env",
        ".ssh",
        ".gnupg",
        ".aws",
        ".docker",
        ".kube",
        ".config",
        "shadow",
        "passwd",
    })

    # Tool names that trigger path checks
    _FILE_TOOLS: frozenset[str] = frozenset({
        "read_file",
        "write_file",
        "create_file",
        "delete_file",
        "move_file",
        "copy_file",
        "list_directory",
        "file_read",
        "file_write",
    })

    # Tool names that trigger bash checks
    _BASH_TOOLS: frozenset[str] = frozenset({
        "bash",
        "shell",
        "execute_command",
        "run_command",
        "terminal",
        "system_exec",
    })

    # -- init ---------------------------------------------------------------

    def __init__(self, allowed_directories: list[str]) -> None:
        self._allowed: list[Path] = [
            Path(d).resolve() for d in allowed_directories
        ]
        logger.info(
            "Firewall initialised with %d allowed directory/ies.",
            len(self._allowed),
        )

    # -- internal checks ----------------------------------------------------

    def _check_path_traversal(self, target_path: str) -> bool:
        """Verify that *target_path* resolves inside an allowed directory.

        Parameters
        ----------
        target_path:
            Raw path string supplied by the agent.

        Returns
        -------
        bool
            ``True`` if the path is safe.

        Raises
        ------
        SecurityViolationError
            If the resolved path escapes the allow-list or touches a
            sensitive system directory.
        """
        try:
            resolved: Path = Path(target_path).resolve()
        except (OSError, ValueError) as exc:
            raise SecurityViolationError(
                f"Cannot resolve path '{target_path}': {exc}",
            ) from exc

        # Check against sensitive path fragments.
        resolved_str: str = str(resolved)
        for part in self._SENSITIVE_FRAGMENTS:
            if f"/{part}" in resolved_str or resolved_str.endswith(f"/{part}"):
                raise SecurityViolationError(
                    f"Path targets sensitive location '{part}': {resolved}",
                )

        # On POSIX, check if the path tries to reach system dirs.
        # resolved.parts for "/etc/passwd" → ('/', 'etc', 'passwd')
        resolved_parts: list[str] = resolved.parts
        if (
            len(resolved_parts) >= 2
            and resolved_parts[0] == "/"
            and resolved_parts[1] in ("etc", "var", "sys", "proc", "usr", "bin", "sbin", "boot", "dev", "lib", "run", "snap", "root")
        ):
            raise SecurityViolationError(
                f"Path targets system directory '/{resolved_parts[1]}/': {resolved}",
            )

        # Verify the path is under at least one allowed root.
        is_allowed: bool = any(
            self._is_subpath(resolved, allowed_root)
            for allowed_root in self._allowed
        )
        if not is_allowed:
            raise SecurityViolationError(
                f"Path '{resolved}' escapes allowed directories: "
                f"{[str(p) for p in self._allowed]}",
            )

        return True

    @staticmethod
    def _is_subpath(child: Path, parent: Path) -> bool:
        """Return ``True`` if *child* is *parent* or a descendant of it."""
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def _check_destructive_bash(self, command: str) -> bool:
        """Scan *command* for destructive or unauthorized patterns.

        Returns
        -------
        bool
            ``True`` if the command is safe.

        Raises
        ------
        SecurityViolationError
            If a destructive pattern is detected.
        """
        patterns: list[tuple[re.Pattern[str], str]] = [
            (self._RE_RM_RF, "Destructive 'rm -rf' detected"),
            (self._RE_MKFS, "Filesystem format command 'mkfs' detected"),
            (self._RE_CHMOD_777, "Insecure 'chmod 777' detected"),
            (self._RE_CHOWN, "Ownership change command 'chown' detected"),
            (self._RE_DD, "Low-level disk write command 'dd' detected"),
            (self._RE_REDIR_OUT, "Shell redirection '>' / '>>' detected"),
            (self._RE_PIPE_BASH, "Unsafe 'curl | bash' or 'wget | bash' detected"),
            (self._RE_KILL_PROCESS, "Process kill command detected"),
            (self._RE_SHUTDOWN, "System shutdown/reboot command detected"),
            (self._RE_CRONTAB, "Cron manipulation command detected"),
            (self._RE_IPTABLES, "Firewall manipulation 'iptables' detected"),
            (self._RE_SUDO_RM, "Privilege-escalated 'sudo rm' detected"),
            (self._RE_PASSWD, "System credential file access detected"),
        ]

        for pattern, reason in patterns:
            if pattern.search(command):
                raise SecurityViolationError(reason)

        return True

    def _detect_pii(self, payload: str) -> bool:
        """Scan *payload* for Personally Identifiable Information.

        Checks for credit-card-like digit sequences and SSN patterns.

        Returns
        -------
        bool
            ``True`` if no PII is detected.

        Raises
        ------
        SecurityViolationError
            If a PII pattern is found.
        """
        if self._RE_SSN.search(payload):
            raise SecurityViolationError(
                "SSN pattern (XXX-XX-XXXX) detected in payload",
            )

        if self._RE_CREDIT_CARD.search(payload):
            raise SecurityViolationError(
                "Potential credit-card number detected in payload",
            )

        return True

    # -- public entry point -------------------------------------------------

    def evaluate_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """Evaluate an agent tool call against the zero-trust policy.

        The evaluation pipeline:

        1. **Path traversal** — if *tool_name* involves file operations,
           every path found in *arguments* is resolved and checked against
           the allow-list.
        2. **Destructive bash** — if *tool_name* involves shell execution,
           the command string is scanned for dangerous patterns.
        3. **PII leak** — regardless of tool, *arguments* are serialised
           and scanned for PII.

        Parameters
        ----------
        tool_name:
            Identifier of the tool the agent wants to invoke.
        arguments:
            Keyword arguments for the tool call.

        Returns
        -------
        bool
            ``True`` if all checks pass.

        Raises
        ------
        SecurityViolationError
            On the **first** violation detected.
        """
        # 1. Path traversal checks for file tools.
        if tool_name in self._FILE_TOOLS:
            path_keys: list[str] = [
                k for k in arguments
                if any(hint in k.lower() for hint in ("path", "file", "dir", "location"))
            ]
            for key in path_keys:
                value: Any = arguments[key]
                if isinstance(value, str):
                    self._check_path_traversal(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            self._check_path_traversal(item)

        # 2. Destructive command checks for shell tools.
        if tool_name in self._BASH_TOOLS:
            cmd_keys: list[str] = [
                k for k in arguments
                if any(hint in k.lower() for hint in ("command", "cmd", "script", "bash"))
            ]
            for key in cmd_keys:
                value = arguments[key]
                if isinstance(value, str):
                    self._check_destructive_bash(value)

        # 3. PII detection on serialised arguments (all tools).
        try:
            serialised: str = json.dumps(arguments, default=str)
        except (TypeError, ValueError):
            serialised = str(arguments)
        self._detect_pii(serialised)

        logger.debug("Tool call '%s' passed zero-trust evaluation.", tool_name)
        return True

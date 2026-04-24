"""AST context compressor — compresses tracebacks to their essential signal.

Truncates exception tracebacks to the last N frames and augments the
signal with an AST parse of any supplied source code so that syntax
errors are surfaced with line numbers. The compressed string is intended
for logging, for inclusion in LESSON.md immunity entries, and for
feedback prompts on planner retries.

Example:
    >>> try:
    ...     json.loads("{")
    ... except Exception as e:
    ...     print(ASTContextCompressor().compress_error(e))

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import ast
import logging
import traceback
from typing import Final

logger: logging.Logger = logging.getLogger(__name__)

MAX_FRAMES: Final[int] = 10


class ASTContextCompressor:
    """Compresses raw Python exceptions into a short diagnostic string.

    Stateless. Safe to share across threads.
    """

    def compress_error(self, error: Exception, source_code: str = "") -> str:
        """Render *error* as a compressed diagnostic string.

        Args:
            error: The exception instance to compress.
            source_code: Optional source text to parse with :mod:`ast`.
                When supplied and unparseable, a ``SyntaxError at line N``
                line is appended to the output.

        Returns:
            Compressed multi-line string: ``type: message`` followed by
            the last :data:`MAX_FRAMES` traceback lines and optionally a
            ``SyntaxError`` hint.
        """
        parts: list[str] = [f"{type(error).__name__}: {error}"]

        tb_lines: list[str] = traceback.format_exception(
            type(error), error, error.__traceback__
        )
        if tb_lines:
            all_lines: list[str] = "".join(tb_lines).splitlines()
            parts.append("\n".join(all_lines[-MAX_FRAMES:]))

        if source_code:
            try:
                ast.parse(source_code)
            except SyntaxError as se:
                parts.append(f"SyntaxError at line {se.lineno}: {se.msg}")

        return "\n".join(parts)

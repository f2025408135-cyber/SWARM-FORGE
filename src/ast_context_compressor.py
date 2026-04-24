"""
AST-based error context extractor: compresses tracebacks to their essential signal.
"""
from __future__ import annotations

import ast
import traceback


class ASTContextCompressor:
    _MAX_FRAMES = 10

    def compress_error(self, error: Exception, source_code: str = "") -> str:
        parts: list[str] = [f"{type(error).__name__}: {error}"]

        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        if tb_lines:
            all_lines = "".join(tb_lines).splitlines()
            parts.append("\n".join(all_lines[-self._MAX_FRAMES:]))

        if source_code:
            try:
                ast.parse(source_code)
            except SyntaxError as se:
                parts.append(f"SyntaxError at line {se.lineno}: {se.msg}")

        return "\n".join(parts)

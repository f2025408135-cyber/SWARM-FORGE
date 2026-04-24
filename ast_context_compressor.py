"""AST Context Compressor for self-healing CI/CD pipelines.

Parses Python tracebacks to locate the exact failure site, then uses AST
analysis to extract only the enclosing function/class block — minimising
context sent to an LLM for debugging.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TracebackTarget(NamedTuple):
    """Parsed terminal traceback information."""
    file_path: str
    line_no: int
    exception_msg: str


# ---------------------------------------------------------------------------
# Traceback parser
# ---------------------------------------------------------------------------

_TRACEBACK_FILE_RE = re.compile(
    r'File "(?P<path>.+)", line (?P<lineno>\d+)',
    re.MULTILINE,
)
_TRACEBACK_EXCEPTION_RE = re.compile(
    r'^(?P<exc>\w+(?:\.\w+)*: .+)$',
    re.MULTILINE,
)


def parse_traceback_for_target(
    stderr_string: str,
) -> TracebackTarget | None:
    """Parse a standard Python traceback and return the terminal failure site.

    Extracts the **last** ``File`` entry (the innermost frame), its line
    number, and the trailing exception message.

    Parameters
    ----------
    stderr_string:
        Raw standard-error output containing a Python traceback.

    Returns
    -------
    TracebackTarget | None
        A named-tuple with ``file_path``, ``line_no``, and
        ``exception_msg``, or ``None`` when the input cannot be parsed.
    """
    if not stderr_string or not stderr_string.strip():
        return None

    # Collect every (path, lineno) pair from the traceback.
    file_matches: list[tuple[str, int]] = [
        (m.group("path"), int(m.group("lineno")))
        for m in _TRACEBACK_FILE_RE.finditer(stderr_string)
    ]
    if not file_matches:
        return None

    # The terminal (last) file entry is the crash site.
    file_path, line_no = file_matches[-1]

    # Extract the exception message — the last line matching the pattern.
    exc_matches: list[str] = _TRACEBACK_EXCEPTION_RE.findall(stderr_string)
    exception_msg: str = exc_matches[-1].strip() if exc_matches else "UnknownError"

    return TracebackTarget(file_path=file_path, line_no=line_no, exception_msg=exception_msg)


# ---------------------------------------------------------------------------
# AST node visitor
# ---------------------------------------------------------------------------

_ENCLOSING_NODE_TYPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


class EnclosingNodeVisitor(ast.NodeVisitor):
    """Walk the AST and find the tightest enclosing block for a target line.

    The visitor records every :class:`ast.FunctionDef`,
    :class:`ast.AsyncFunctionDef`, and :class:`ast.ClassDef` whose source
    range spans *target_line*.  Among those, the node with the smallest span
    (most deeply nested) is kept as the best match.

    Parameters
    ----------
    target_line:
        The 1-based line number where the error occurred.
    """

    def __init__(self, target_line: int) -> None:
        self.target_line: int = target_line
        self.best_node: ast.AST | None = None
        self.best_span: int = 0  # node line range; smaller ⇒ tighter

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._consider(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._consider(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._consider(node)
        self.generic_visit(node)

    # -- private helpers ----------------------------------------------------

    def _consider(self, node: ast.AST) -> None:
        """Register *node* if it encloses the target line more tightly."""
        node_start: int = node.lineno  # type: ignore[attr-defined]
        node_end: int = node.end_lineno if node.end_lineno is not None else node_start  # type: ignore[attr-defined]

        if node_start <= self.target_line <= node_end:
            span: int = node_end - node_start
            if self.best_node is None or span < self.best_span:
                self.best_node = node
                self.best_span = span


# ---------------------------------------------------------------------------
# Context extractor (main entry point)
# ---------------------------------------------------------------------------

_FALLBACK_RADIUS: int = 5


def extract_healing_context(
    file_path: str,
    target_line: int,
) -> str:
    """Extract the minimal enclosing code block for a given failure line.

    Reads *file_path*, parses its AST, and returns only the source lines of
    the tightest enclosing ``def``, ``async def``, or ``class`` block that
    contains *target_line*.

    **Fail-safe:** If the file cannot be parsed due to a :class:`SyntaxError`,
    the function falls back to returning a 10-line window centred on the
    target line (5 above, 5 below) obtained via basic string splitting.

    Parameters
    ----------
    file_path:
        Path to the Python source file.
    target_line:
        The 1-based line number where the error occurred.

    Returns
    -------
    str
        The extracted source-code block (with a trailing newline), or the
        fallback window when AST parsing is not possible.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    raw_source: str = path.read_text(encoding="utf-8")
    source_lines: list[str] = raw_source.splitlines()

    # ---- AST-based extraction --------------------------------------------
    try:
        tree: ast.Module = ast.parse(raw_source, filename=str(path))
    except SyntaxError:
        # Graceful degradation — return a raw line window.
        return _fallback_window(source_lines, target_line)

    visitor = EnclosingNodeVisitor(target_line)
    visitor.visit(tree)

    if visitor.best_node is not None:
        start: int = visitor.best_node.lineno  # type: ignore[attr-defined]
        end: int = (  # type: ignore[attr-defined]
            visitor.best_node.end_lineno  # type: ignore[attr-defined]
            if visitor.best_node.end_lineno is not None  # type: ignore[attr-defined]
            else start
        )
        extracted: list[str] = source_lines[start - 1 : end]
        return "\n".join(extracted) + "\n"

    # Edge case: error is in module-level global scope.
    return _fallback_window(source_lines, target_line)


def _fallback_window(
    source_lines: list[str],
    target_line: int,
) -> str:
    """Return a *2 × FALLBACK_RADIUS + 1* line window around *target_line*."""
    lo: int = max(0, target_line - _FALLBACK_RADIUS - 1)
    hi: int = min(len(source_lines), target_line + _FALLBACK_RADIUS)
    window: list[str] = source_lines[lo:hi]
    return "\n".join(window) + "\n"


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

def main() -> None:
    """Minimal CLI for ad-hoc testing."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Extract the AST context block for a failing line.",
    )
    parser.add_argument("file", help="Path to the Python source file.")
    parser.add_argument(
        "line", type=int, help="1-based line number of the failure.",
    )
    parser.add_argument(
        "--traceback", "-t",
        metavar="STDERR",
        default=None,
        help="Raw stderr string (parsed automatically for file + line).",
    )
    args = parser.parse_args()

    if args.traceback:
        target = parse_traceback_for_target(args.traceback)
        if target is None:
            sys.stderr.write("ERROR: could not parse the provided traceback.\n")
            sys.exit(1)
        file_path, target_line = target.file_path, target.line_no
        print(f"[*] Parsed traceback → {file_path}:{target_line}  ({target.exception_msg})")
    else:
        file_path, target_line = args.file, args.line

    try:
        context = extract_healing_context(file_path, target_line)
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)

    print(context, end="")


if __name__ == "__main__":
    main()

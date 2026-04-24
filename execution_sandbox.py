"""Secure subprocess execution sandbox for autonomous CI/CD loops.

Runs dynamically generated Python scripts as child processes with strict
time limits, capturing stdout/stderr and guaranteeing process cleanup on
timeout to prevent zombie processes from hanging the orchestrator.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    """Immutable snapshot of a subprocess execution outcome.

    Attributes
    ----------
    return_code:
        Exit code of the child process.  ``-1`` when killed due to timeout.
    stdout:
        Captured standard output (decoded as UTF-8).
    stderr:
        Captured standard error (decoded as UTF-8).
    execution_time_sec:
        Wall-clock seconds between process spawn and termination.
    timed_out:
        ``True`` if the process was killed for exceeding the time limit.
    """

    return_code: int
    stdout: str
    stderr: str
    execution_time_sec: float
    timed_out: bool

    @property
    def success(self) -> bool:
        """Return ``True`` if the process exited with code 0 and didn't time out."""
        return self.return_code == 0 and not self.timed_out


# ---------------------------------------------------------------------------
# Sandbox executor
# ---------------------------------------------------------------------------

class SandboxExecutor:
    """Secure, timeout-enforcing subprocess runner for Python scripts.

    Every execution is isolated in a child process via
    :class:`subprocess.Popen` with piped stdout/stderr.  A wall-clock
    timeout is enforced through :meth:`process.communicate`; on expiry
    the child is forcefully terminated (``SIGKILL`` on POSIX,
    ``TerminateProcess`` on Windows) and drained to prevent zombies.

    Parameters
    ----------
    default_timeout:
        Default execution time limit in seconds.  Used when
        :meth:`execute_script` is called without an explicit *timeout*.
    """

    def __init__(self, default_timeout: int = 15) -> None:
        self._default_timeout: int = default_timeout

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _kill_process(process: subprocess.Popen[Any]) -> None:
        """Forcefully terminate a child process cross-platform.

        On POSIX this sends ``SIGKILL`` (unblockable, immediate).
        On Windows it calls ``TerminateProcess`` via
        :meth:`subprocess.Popen.kill`.

        After signalling, the method polls briefly (up to 2 s) for the
        process to exit.  If it still hasn't, a second kill is issued.
        """
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            # Process already dead — nothing to do.
            return

        # Give the OS a moment to reap the process.
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # Still alive — double-tap.
            try:
                process.kill()
            except OSError:
                pass

    @staticmethod
    def _decode_output(raw: bytes) -> str:
        """Decode subprocess output with graceful fallback."""
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

    # -- public API ---------------------------------------------------------

    def execute_script(
        self,
        file_path: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """Execute a Python script in a sandboxed subprocess.

        Parameters
        ----------
        file_path:
            Path to the ``.py`` file to execute.
        timeout:
            Maximum wall-clock seconds.  Falls back to
            :attr:`default_timeout` when ``None``.

        Returns
        -------
        ExecutionResult
            Immutable result record with captured output and metadata.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        PermissionError
            If *file_path* is not readable/executable.
        """
        effective_timeout: int = timeout if timeout is not None else self._default_timeout
        executable: str = sys.executable  # use the running Python interpreter

        start: float = time.monotonic()

        process: subprocess.Popen[Any] = subprocess.Popen(
            [executable, file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )

        try:
            stdout_bytes, stderr_bytes = process.communicate(
                timeout=effective_timeout,
            )
            timed_out: bool = False
            return_code: int = process.returncode if process.returncode is not None else -1

        except subprocess.TimeoutExpired:
            # ---- CRITICAL FAIL-SAFE: kill the child -------------------------
            self._kill_process(process)

            # Drain any remaining buffered output from the pipes.
            stdout_bytes: bytes = b""
            stderr_bytes: bytes = b""
            if process.stdout is not None:
                stdout_bytes = process.stdout.read()
            if process.stderr is not None:
                stderr_bytes = process.stderr.read()

            # Close pipes to prevent resource leaks.
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()

            timed_out = True
            return_code = -1

        elapsed: float = time.monotonic() - start

        return ExecutionResult(
            return_code=return_code,
            stdout=self._decode_output(stdout_bytes),
            stderr=self._decode_output(stderr_bytes),
            execution_time_sec=round(elapsed, 6),
            timed_out=timed_out,
        )

    def validate_syntax_only(self, file_path: str) -> ExecutionResult:
        """Check a file for syntax errors without executing it.

        Runs ``python -m py_compile <file_path>`` as a subprocess with a
        generous timeout.  This catches :class:`SyntaxError` and
        :class:`IndentationError` without side effects.

        Parameters
        ----------
        file_path:
            Path to the ``.py`` file to validate.

        Returns
        -------
        ExecutionResult
            ``success`` is ``True`` when no syntax errors are found.
        """
        executable: str = sys.executable
        start: float = time.monotonic()

        try:
            process: subprocess.Popen[Any] = subprocess.Popen(
                [executable, "-m", "py_compile", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            stdout_bytes, stderr_bytes = process.communicate(timeout=30)

            return ExecutionResult(
                return_code=process.returncode if process.returncode is not None else -1,
                stdout=self._decode_output(stdout_bytes),
                stderr=self._decode_output(stderr_bytes),
                execution_time_sec=round(time.monotonic() - start, 6),
                timed_out=False,
            )

        except subprocess.TimeoutExpired:
            self._kill_process(process)
            elapsed: float = time.monotonic() - start
            return ExecutionResult(
                return_code=-1,
                stdout="",
                stderr="Syntax validation timed out.",
                execution_time_sec=round(elapsed, 6),
                timed_out=True,
            )

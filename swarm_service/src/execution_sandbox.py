"""Execution sandbox — runs generated node scripts in isolated subprocesses.

Builds a self-contained Python script for each DAG node, writes it to a
temp file, and executes it via :func:`subprocess.run` with a bounded
timeout. The parent process captures stdout/stderr and converts every
outcome (success, timeout, non-zero exit, unexpected exception) into the
canonical ``{"status", "output", "error"}`` result shape used by the DAG
runner.

Example:
    >>> SandboxExecutor().execute("n1", "print hello", {})
    {'status': 'success', 'output': '...', 'error': None}

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import Any, Final

from .agent_guard import verify_agent_action

logger: logging.Logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC: Final[int] = 120
TEMP_SCRIPT_SUFFIX: Final[str] = ".py"
TEMP_SCRIPT_FILENAME: Final[str] = "node_script.py"
TEMP_DIR_PREFIX: Final[str] = "swarmforge_sandbox_"
STATUS_SUCCESS: Final[str] = "success"
STATUS_ERROR: Final[str] = "error"
STATUS_BLOCKED: Final[str] = "blocked"


class SandboxExecutor:
    """Runs a task_description inside a bounded-timeout Python subprocess.

    Stateless by design — the parent process captures stdout/stderr on
    every invocation and converts every subprocess outcome to the canonical
    result schema. The temp-file script is always unlinked, even on
    timeout or exception.
    """

    def execute(
        self,
        node_id: str,
        task_description: str,
        context: dict[str, Any],
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        """Run *task_description* for *node_id* in an isolated subprocess.

        Args:
            node_id: Unique identifier of the DAG node being executed.
            task_description: Human-readable task passed into the generated
                script.
            context: Arbitrary key/value pairs made available to the script.
            timeout_sec: Seconds to wait before killing the subprocess.

        Returns:
            A dict with keys ``status``, ``output``, and ``error``.
        """
        script: str = self._build_script(node_id, task_description, context)

        is_safe, reason = verify_agent_action(script)
        if not is_safe:
            logger.warning(
                "Node %s blocked by AgentGuard Layer 3: %s", node_id, reason
            )
            return {
                "status": STATUS_BLOCKED,
                "output": f"AgentGuard Layer 3 blocked: {reason}",
                "error": reason,
                "returncode": -1,
            }

        try:
            stdout: str = self._run_subprocess(script, timeout_sec)
            return {"status": STATUS_SUCCESS, "output": stdout, "error": None}
        except subprocess.TimeoutExpired:
            logger.warning("Node %s timed out after %ds", node_id, timeout_sec)
            return {
                "status": STATUS_ERROR,
                "output": "",
                "error": "execution_timeout",
            }
        except subprocess.CalledProcessError as exc:
            logger.warning("Node %s exited non-zero: %s", node_id, exc.stderr)
            return {
                "status": STATUS_ERROR,
                "output": exc.stdout or "",
                "error": (exc.stderr or str(exc)).strip(),
            }
        except OSError as exc:
            logger.exception("OS error while sandboxing node %s", node_id)
            return {"status": STATUS_ERROR, "output": "", "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected sandbox error for node %s", node_id)
            return {"status": STATUS_ERROR, "output": "", "error": str(exc)}

    def _build_script(
        self,
        node_id: str,
        task_description: str,
        context: dict[str, Any],
    ) -> str:
        """Render a self-contained Python script that echoes the node metadata.

        Args:
            node_id: ID of the DAG node.
            task_description: Task text to embed in the script.
            context: Arbitrary JSON-serialisable context.

        Returns:
            Source code for the temporary script.
        """
        # IMPORTANT: context may contain Python booleans / None. json.dumps
        # produces JSON literals ``true``/``false``/``null`` which are NOT
        # valid Python when spliced into source code. ``repr`` on a
        # JSON-serialisable dict round-trips through a json.loads() call so
        # the generated script is always syntactically valid Python.
        context_json: str = json.dumps(context)
        return textwrap.dedent(f"""\
            import json, sys
            node_id = {json.dumps(node_id)}
            task = {json.dumps(task_description)}
            context = json.loads({json.dumps(context_json)})
            result = {{
                "node_id": node_id,
                "task": task,
                "status": "executed",
            }}
            print(json.dumps(result))
        """)

    def _run_subprocess(self, script: str, timeout_sec: int) -> str:
        """Write *script* to a temp file, execute it, and return stripped stdout.

        Uses :func:`tempfile.mkdtemp` + :func:`shutil.rmtree` so that the
        entire scratch directory is torn down even if individual files (a
        ``.pyc`` cache, a stray temp file written by the child) resist a
        single ``os.unlink`` call. This prevents disk accumulation across
        hundreds of parallel runs.

        Args:
            script: Python source to execute.
            timeout_sec: Maximum wall-clock seconds before termination.

        Returns:
            The subprocess stdout, stripped of trailing whitespace.

        Raises:
            subprocess.CalledProcessError: If the subprocess exits non-zero.
            subprocess.TimeoutExpired: If the subprocess exceeds the timeout.
        """
        tmp_dir: str = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
        tmp_path: str = os.path.join(tmp_dir, TEMP_SCRIPT_FILENAME)
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, proc.args, proc.stdout, proc.stderr
                )
            return proc.stdout.strip()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

"""
Subprocess-sandboxed execution: runs generated node scripts in isolated processes.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
from typing import Any

logger = logging.getLogger("swarmforge.sandbox")

_TIMEOUT_SEC = 30


class SandboxExecutor:
    def execute(
        self,
        node_id: str,
        task_description: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        script = self._build_script(node_id, task_description, context)
        try:
            stdout = self._run_subprocess(script)
            return {"status": "success", "output": stdout, "error": None}
        except subprocess.TimeoutExpired:
            logger.warning("Node %s timed out after %ds", node_id, _TIMEOUT_SEC)
            return {"status": "error", "output": "", "error": "execution_timeout"}
        except subprocess.CalledProcessError as exc:
            logger.warning("Node %s exited non-zero: %s", node_id, exc.stderr)
            return {
                "status": "error",
                "output": exc.stdout or "",
                "error": (exc.stderr or str(exc)).strip(),
            }
        except Exception as exc:
            logger.exception("Unexpected sandbox error for node %s", node_id)
            return {"status": "error", "output": "", "error": str(exc)}

    # ── private ────────────────────────────────────────────────────────────

    def _build_script(
        self,
        node_id: str,
        task_description: str,
        context: dict[str, Any],
    ) -> str:
        return textwrap.dedent(f"""\
            import json, sys
            node_id = {json.dumps(node_id)}
            task = {json.dumps(task_description)}
            context = {json.dumps(context)}
            result = {{
                "node_id": node_id,
                "task": task,
                "status": "executed",
            }}
            print(json.dumps(result))
        """)

    def _run_subprocess(self, script: str) -> str:
        fd, tmp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(script)
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SEC,
            )
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, proc.args, proc.stdout, proc.stderr
                )
            return proc.stdout.strip()
        finally:
            os.unlink(tmp_path)

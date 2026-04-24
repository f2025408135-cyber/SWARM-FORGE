"""OpenTelemetry-style telemetry logger for distributed multi-agent systems.

Captures unhandled exceptions from sub-processes and formats them as
**High-Priority Failure Events** (HPFE) adhering to OTel GenAI Semantic
Conventions.  Each event is serialised as a single JSON line and appended
to a ``.jsonl`` file for asynchronous consumption by a parent process.
"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)

_HPFE_FILENAME: str = "hpfe_traces.jsonl"


# ---------------------------------------------------------------------------
# Custom JSON encoder — graceful non-serializable fallback
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that converts non-serializable objects to their string
    representation instead of raising :class:`TypeError`."""

    def default(self, o: Any) -> Any:
        """Convert non-serializable objects to their string representation."""
        return str(o)


# ---------------------------------------------------------------------------
# HPFE logger
# ---------------------------------------------------------------------------

class HPFELogger:
    """Append-only ``.jsonl`` logger for High-Priority Failure Events.

    Each call to :meth:`log_failure` produces a single JSON line conforming
    to the OpenTelemetry GenAI Semantic Convention vocabulary, enriched with
    project-specific context fields.

    Parameters
    ----------
    log_dir:
        Directory where ``hpfe_traces.jsonl`` is created / appended.
        Created automatically when it does not exist.
    """

    def __init__(self, log_dir: str = "./logs") -> None:
        self._log_dir: Path = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._file_path: Path = self._log_dir / _HPFE_FILENAME

    # -- private helpers ---------------------------------------------------

    @staticmethod
    def _generate_trace_id() -> str:
        """Return a standard UUID4 trace identifier string."""
        return str(uuid.uuid4())

    @staticmethod
    def _extract_traceback(error: BaseException) -> str:
        """Return the formatted traceback string for *error*.

        Uses :func:`traceback.format_exception` for maximum fidelity
        (includes chained ``__cause__`` / ``__context__`` when present).
        """
        tb_lines: list[str] = traceback.format_exception(
            type(error),
            error,
            error.__traceback__,
        )
        return "".join(tb_lines).rstrip()

    # -- public API ---------------------------------------------------------

    def log_failure(
        self,
        agent_name: str,
        operation_name: str,
        error: Exception,
        context_payload: dict[str, Any],
    ) -> str:
        """Record a failure event to the JSONL trace file.

        Parameters
        ----------
        agent_name:
            Identifier of the agent that raised the exception.
        operation_name:
            Name of the operation that was executing (e.g.
            ``"execute_tool"``, ``"parse_response"``).
        error:
            The caught :class:`Exception` instance.
        context_payload:
            Arbitrary dict of local variables / state to attach to the
            event for debugging context.

        Returns
        -------
        str
            The ``trace_id`` assigned to this event (useful for
            correlation in downstream consumers).
        """
        trace_id: str = self._generate_trace_id()
        tb_string: str = self._extract_traceback(error)

        event: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "gen_ai.operation.name": operation_name,
            "gen_ai.agent.name": agent_name,
            "error.type": type(error).__name__,
            "error.traceback": tb_string,
            "swarm_forge.context_snapshot": context_payload,
        }

        line: str = json.dumps(event, cls=_SafeEncoder, ensure_ascii=False)

        try:
            with self._file_path.open(mode="a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            logger.critical(
                "Failed to append HPFE to %s: %s",
                self._file_path,
                exc,
            )

        logger.info(
            "HPFE recorded — trace_id=%s agent=%s op=%s error=%s",
            trace_id,
            agent_name,
            operation_name,
            type(error).__name__,
        )

        return trace_id

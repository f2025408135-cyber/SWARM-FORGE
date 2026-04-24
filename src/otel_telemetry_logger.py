"""OTel-style telemetry logger — structured failure and lifecycle records.

Emits JSON-serialised structured records on the ``swarmforge.otel``
logger at ``INFO`` for lifecycle events and ``ERROR`` for node failures.
Records are schema-compatible with OTel log-record conventions (event
name, severity, attributes, timestamp) so that downstream collectors can
map them directly onto OpenTelemetry log pipelines.

Example:
    >>> HPFELogger().log_event("orchestration_complete", {"nodes": 5})

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Final

logger: logging.Logger = logging.getLogger(__name__)

SEVERITY_INFO: Final[str] = "INFO"
SEVERITY_ERROR: Final[str] = "ERROR"
EVENT_NODE_FAILURE: Final[str] = "node_failure"


class HPFELogger:
    """High-Performance Failure Events — structured OTel-style record emitter.

    Stateless. Safe to share across threads.
    """

    def log_failure(
        self,
        node_id: str,
        error: Exception,
        context: dict[str, Any],
    ) -> None:
        """Emit a structured ``ERROR`` record for a node failure.

        Args:
            node_id: Identifier of the failing DAG node.
            error: Exception instance raised during node execution.
            context: Arbitrary attributes to attach (e.g. the node dict
                and a compressed traceback).
        """
        record: dict[str, Any] = {
            "severity": SEVERITY_ERROR,
            "event": EVENT_NODE_FAILURE,
            "node_id": node_id,
            "error_type": type(error).__name__,
            "error_msg": str(error),
            "context": context,
            "timestamp": time.time(),
        }
        logger.error(json.dumps(record, default=str))

    def log_event(self, event_name: str, attributes: dict[str, Any]) -> None:
        """Emit a structured ``INFO`` lifecycle record.

        Args:
            event_name: Short event identifier (e.g. ``"input_blocked"``).
            attributes: Arbitrary JSON-serialisable attributes.
        """
        record: dict[str, Any] = {
            "severity": SEVERITY_INFO,
            "event": event_name,
            "attributes": attributes,
            "timestamp": time.time(),
        }
        logger.info(json.dumps(record, default=str))

"""
OTel-style failure logger: structured records for node failures and lifecycle events.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("swarmforge.otel")


class HPFELogger:
    def log_failure(
        self,
        node_id: str,
        error: Exception,
        context: dict[str, Any],
    ) -> None:
        record = {
            "severity": "ERROR",
            "event": "node_failure",
            "node_id": node_id,
            "error_type": type(error).__name__,
            "error_msg": str(error),
            "context": context,
            "timestamp": time.time(),
        }
        logger.error(json.dumps(record))

    def log_event(self, event_name: str, attributes: dict[str, Any]) -> None:
        record = {
            "severity": "INFO",
            "event": event_name,
            "attributes": attributes,
            "timestamp": time.time(),
        }
        logger.info(json.dumps(record))

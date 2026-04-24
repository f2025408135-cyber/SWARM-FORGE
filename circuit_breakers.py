"""
Swarm-Forge Circuit Breakers and Budget Enforcement
Prevents runaway token loops and hardware damage.
"""

from __future__ import annotations
import hashlib
import time
import sqlite3
import os
import subprocess
import logging
from functools import wraps
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── Fuse: Loop Detection ────────────────────────────────────────────────────

@dataclass
class FuseState:
    node_id: str
    input_hashes: list[str] = field(default_factory=list)
    max_repetitions: int = 3
    blown: bool = False

    def check(self, input_data: dict) -> bool:
        """Returns True if the fuse has blown (loop detected)."""
        h = hashlib.sha256(str(sorted(input_data.items())).encode()).hexdigest()
        self.input_hashes.append(h)
        if len(self.input_hashes) >= self.max_repetitions:
            last_n = self.input_hashes[-self.max_repetitions:]
            if len(set(last_n)) == 1:
                self.blown = True
                logger.error(
                    f"FUSE BLOWN: Node {self.node_id} detected identical "
                    f"inputs {self.max_repetitions} times consecutively. "
                    f"Halting to prevent infinite loop."
                )
        return self.blown


_fuse_registry: dict[str, FuseState] = {}

def fuse(max_repetitions: int = 3):
    """Decorator: blows if the same input hash appears N times in a row."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            node_id = kwargs.get("node_id", func.__name__)
            if node_id not in _fuse_registry:
                _fuse_registry[node_id] = FuseState(
                    node_id=node_id,
                    max_repetitions=max_repetitions
                )
            state = _fuse_registry[node_id]
            input_snapshot = {"args": str(args), "kwargs": str(kwargs)}
            if state.check(input_snapshot):
                raise RuntimeError(
                    f"Fuse blown on {node_id}: infinite loop detected. "
                    f"Escalating to Opus for conflict resolution."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ── Sentinel: Output Validation ─────────────────────────────────────────────

def sentinel(schema_class):
    """Decorator: validates LLM output against Pydantic schema before passing downstream."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                validated = schema_class.model_validate(result)
                return validated
            elif isinstance(result, str):
                import json
                try:
                    data = json.loads(result)
                    validated = schema_class.model_validate(data)
                    return validated
                except (json.JSONDecodeError, Exception) as e:
                    raise ValueError(
                        f"Sentinel: Output failed schema validation for "
                        f"{schema_class.__name__}: {e}. "
                        f"Routing to Medic for repair."
                    ) from e
            return result
        return wrapper
    return decorator


# ── Medic: Auto-Repair via Haiku ────────────────────────────────────────────

def medic_repair(malformed_json: str, target_schema_name: str) -> str:
    """
    Routes malformed JSON to Haiku 4.5 for low-cost structural repair.
    Returns corrected JSON string or raises on repeated failure.
    """
    from anthropic import Anthropic
    client = Anthropic()

    repair_prompt = (
        f"The following JSON is malformed or missing required fields. "
        f"Fix it to match the {target_schema_name} schema. "
        f"Return ONLY valid JSON, no markdown, no explanation.\n\n"
        f"Malformed input:\n{malformed_json}"
    )

    for attempt in range(3):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": repair_prompt}]
        )
        repaired = response.content[0].text.strip()
        if repaired.startswith("{") or repaired.startswith("["):
            logger.info(f"Medic repaired JSON on attempt {attempt + 1}")
            return repaired
        time.sleep(1)

    raise ValueError(f"Medic failed to repair JSON after 3 attempts for {target_schema_name}")


# ── ComputeAuditor ──────────────────────────────────────────────────────────

class ComputeAuditor:
    """
    Hardware and financial fail-safe for autonomous MLOps pipelines.
    Monitors GPU temperature and API token expenditure.
    """

    def __init__(
        self,
        max_safe_temp_c: int = 80,
        daily_token_budget: int = 5_000_000,
        db_path: str = "./logs/swarm_metrics.sqlite"
    ):
        self.max_temp = max_safe_temp_c
        self.token_budget = daily_token_budget
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self.nvml_active = False
        self.gpu_handle = None
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.nvml_active = True
            except Exception:
                pass

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT DEFAULT (date('now')),
                    agent_name TEXT,
                    model TEXT,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record_tokens(
        self, agent_name: str, model: str,
        prompt_tokens: int, completion_tokens: int
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agent_messages "
                "(agent_name, model, prompt_tokens, completion_tokens) "
                "VALUES (?, ?, ?, ?)",
                (agent_name, model, prompt_tokens, completion_tokens)
            )
            conn.commit()

    def query_gpu_temperature(self) -> int:
        if self.nvml_active and self.gpu_handle:
            return pynvml.nvmlDeviceGetTemperature(
                self.gpu_handle, pynvml.NVML_TEMPERATURE_GPU
            )
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            return int(result.stdout.strip())
        except Exception:
            return 0

    def audit_token_expenditure(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT SUM(prompt_tokens + completion_tokens) "
                "FROM agent_messages WHERE session_date = date('now')"
            ).fetchone()
            return row[0] or 0

    def execute_gate_check(self) -> dict[str, Any]:
        temp = self.query_gpu_temperature()
        tokens = self.audit_token_expenditure()
        thermal_violation = temp >= self.max_temp and temp > 0
        budget_violation = tokens >= self.token_budget
        authorized = not thermal_violation and not budget_violation

        if thermal_violation:
            logger.critical(
                f"THERMAL VIOLATION: GPU at {temp}°C >= {self.max_temp}°C limit. "
                f"Pipeline HALTED."
            )
        if budget_violation:
            logger.critical(
                f"BUDGET VIOLATION: {tokens:,} tokens >= {self.token_budget:,} limit. "
                f"Pipeline HALTED."
            )

        return {
            "temperature_celsius": temp,
            "tokens_utilized": tokens,
            "token_budget": self.token_budget,
            "thermal_violation": thermal_violation,
            "budget_violation": budget_violation,
            "pipeline_authorized": authorized,
        }

    def __del__(self):
        if self.nvml_active:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

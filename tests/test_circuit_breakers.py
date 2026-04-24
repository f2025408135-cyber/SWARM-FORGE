"""Tests for Swarm-Forge circuit breakers — Fuse, Sentinel, Medic, ComputeAuditor."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from circuit_breakers import (
    ComputeAuditor,
    FuseState,
    _fuse_registry,
    fuse,
    medic_repair,
    sentinel,
)


# ── FuseState ───────────────────────────────────────────────────────────────


class TestFuseState:
    """Verify the Fuse loop-detection state machine."""

    def setup_method(self) -> None:
        """Clear fuse registry before each test."""
        _fuse_registry.clear()

    def test_no_blow_on_unique_inputs(self) -> None:
        state = FuseState(node_id="n1", max_repetitions=3)
        for i in range(5):
            result = state.check({"iteration": i, "data": f"payload-{i}"})
        assert state.blown is False
        assert result is False

    def test_blow_after_three_identical_inputs(self) -> None:
        state = FuseState(node_id="n2", max_repetitions=3)
        same_input = {"key": "value", "stable": True}

        # First two calls: no blow
        assert state.check(same_input) is False
        assert state.check(same_input) is False

        # Third identical call: fuse blows
        assert state.check(same_input) is True
        assert state.blown is True

    def test_blow_remains_persistent(self) -> None:
        state = FuseState(node_id="n3", max_repetitions=3)
        same = {"x": 1}
        for _ in range(5):
            state.check(same)
        assert state.blown is True
        # Even a different input after blow stays blown
        state.check({"different": True})
        assert state.blown is True

    def test_custom_max_repetitions(self) -> None:
        state = FuseState(node_id="n4", max_repetitions=5)
        same = {"a": "b"}
        for _ in range(4):
            assert state.check(same) is False
        assert state.check(same) is True

    def test_fuse_decorator_blow_raises(self) -> None:
        _fuse_registry.clear()

        @fuse(max_repetitions=3)
        def process(node_id: str = "decorated-node", **kwargs) -> str:
            return "ok"

        # Two calls should pass
        assert process(node_id="decorated-node") == "ok"
        assert process(node_id="decorated-node") == "ok"

        # Third should raise RuntimeError
        with pytest.raises(RuntimeError, match="Fuse blown"):
            process(node_id="decorated-node")

    def test_fuse_decorator_uses_func_name_as_node_id(self) -> None:
        _fuse_registry.clear()

        @fuse(max_repetitions=2)
        def my_agent(**kwargs) -> str:
            return "result"

        assert my_agent() == "result"
        with pytest.raises(RuntimeError, match="my_agent"):
            my_agent()


# ── Sentinel ────────────────────────────────────────────────────────────────


class _TestOutput(BaseModel):
    """Minimal Pydantic model for sentinel validation tests."""
    result: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)


class TestSentinel:
    """Verify the Sentinel output-validation decorator."""

    def test_valid_dict_passes(self) -> None:
        @sentinel(_TestOutput)
        def produce_output() -> dict:
            return {"result": "success", "score": 85}

        validated = produce_output()
        assert isinstance(validated, _TestOutput)
        assert validated.result == "success"
        assert validated.score == 85

    def test_valid_json_string_passes(self) -> None:
        @sentinel(_TestOutput)
        def produce_json_string() -> str:
            return json.dumps({"result": "works", "score": 42})

        validated = produce_json_string()
        assert isinstance(validated, _TestOutput)
        assert validated.result == "works"

    def test_malformed_json_string_raises(self) -> None:
        @sentinel(_TestOutput)
        def produce_bad_json() -> str:
            return "this is not json at all"

        with pytest.raises(ValueError, match="Sentinel: Output failed schema validation"):
            produce_bad_json()

    def test_invalid_dict_fields_raises(self) -> None:
        @sentinel(_TestOutput)
        def produce_invalid_dict() -> dict:
            return {"result": "", "score": 200}  # empty string + score > 100

        with pytest.raises(Exception):
            produce_invalid_dict()

    def test_missing_required_field_raises(self) -> None:
        @sentinel(_TestOutput)
        def produce_missing_field() -> dict:
            return {"result": "ok"}  # missing 'score'

        with pytest.raises(Exception):
            produce_missing_field()

    def test_non_dict_non_string_passthrough(self) -> None:
        """Non-dict, non-string results pass through unchanged."""

        @sentinel(_TestOutput)
        def produce_object():
            return _TestOutput(result="passthrough", score=50)

        result = produce_object()
        assert isinstance(result, _TestOutput)
        assert result.score == 50


# ── ComputeAuditor ──────────────────────────────────────────────────────────


class TestComputeAuditor:
    """Verify the ComputeAuditor hardware and budget fail-safe."""

    @pytest.fixture()
    def auditor(self, tmp_path: Path) -> ComputeAuditor:
        db = str(tmp_path / "swarm_metrics.sqlite")
        return ComputeAuditor(
            max_safe_temp_c=80,
            daily_token_budget=1_000_000,
            db_path=db,
        )

    def test_init_creates_database_table(self, auditor: ComputeAuditor, tmp_path: Path) -> None:
        db_file = tmp_path / "swarm_metrics.sqlite"
        assert db_file.exists()
        conn = sqlite3.connect(str(db_file))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        conn.close()
        assert "agent_messages" in table_names

    def test_record_tokens_persists(self, auditor: ComputeAuditor) -> None:
        auditor.record_tokens("researcher", "claude-sonnet-4-6", 500, 200)
        auditor.record_tokens("executor", "claude-haiku-4-5-20251001", 1000, 300)

        conn = sqlite3.connect(str(auditor.db_path))
        rows = conn.execute(
            "SELECT agent_name, model, prompt_tokens, completion_tokens "
            "FROM agent_messages ORDER BY id"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0] == ("researcher", "claude-sonnet-4-6", 500, 200)
        assert rows[1] == ("executor", "claude-haiku-4-5-20251001", 1000, 300)

    def test_audit_token_expenditure_sums_today(self, auditor: ComputeAuditor) -> None:
        auditor.record_tokens("agent-a", "sonnet", 10_000, 5_000)
        auditor.record_tokens("agent-b", "haiku", 20_000, 8_000)

        total = auditor.audit_token_expenditure()
        assert total == 43_000

    def test_audit_empty_database(self, auditor: ComputeAuditor) -> None:
        total = auditor.audit_token_expenditure()
        assert total == 0

    def test_execute_gate_check_no_violations(self, auditor: ComputeAuditor) -> None:
        auditor.record_tokens("agent", "haiku", 100, 50)

        gate = auditor.execute_gate_check()
        assert gate["pipeline_authorized"] is True
        assert gate["thermal_violation"] is False
        assert gate["budget_violation"] is False
        assert gate["tokens_utilized"] == 150

    def test_execute_gate_check_budget_violation(self, tmp_path: Path) -> None:
        auditor = ComputeAuditor(
            max_safe_temp_c=80,
            daily_token_budget=100,
            db_path=str(tmp_path / "budget_test.sqlite"),
        )
        auditor.record_tokens("agent", "opus", 50, 60)

        gate = auditor.execute_gate_check()
        assert gate["budget_violation"] is True
        assert gate["pipeline_authorized"] is False
        assert gate["tokens_utilized"] == 110

    def test_execute_gate_check_thermal_violation_zero_temp_ignored(
        self, auditor: ComputeAuditor
    ) -> None:
        """GPU temp of 0 (no GPU) should NOT trigger thermal violation."""
        gate = auditor.execute_gate_check()
        assert gate["temperature_celsius"] == 0
        # 0 >= 80 is True but 0 > 0 is False, so thermal_violation = False
        assert gate["thermal_violation"] is False

    def test_gpu_temperature_fallback_returns_zero(self, auditor: ComputeAuditor) -> None:
        """When no GPU is available, temperature returns 0 (no crash)."""
        temp = auditor.query_gpu_temperature()
        assert isinstance(temp, int)
        assert temp >= 0


# ── Medic ───────────────────────────────────────────────────────────────────


class TestMedicRepair:
    """Verify medic_repair attempts Haiku-based JSON repair."""

    def test_medic_repair_no_api_key_raises(self) -> None:
        """Without an API key, medic_repair should fail after 3 attempts."""
        with pytest.raises(Exception):
            medic_repair("{broken json", "TestSchema")

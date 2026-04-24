"""Pytest suite for stateful healing in :class:`MetaOrchestrator`.

Covers the HEALING path: a failing node routes through ``SkillSynthesisEngine``,
retries the sandbox, and surfaces ``heal_status`` = ``healed`` or
``failed_after_heal``. We exercise this without any live Anthropic calls by
stubbing the skill engine and sandbox, and redirecting the SGC memory file
to a per-test temp path so we do not pollute ``templates/agent_config.j2``.

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.memory_system import SynapticGarbageCollector
from src.meta_orchestrator import (
    STATUS_FAILED_AFTER_HEAL,
    STATUS_HEALED,
    MetaOrchestrator,
)


def _make_node(node_id: str = "n1") -> dict[str, Any]:
    return {
        "node_id": node_id,
        "task_description": "emit structured status output",
        "dependencies": [],
        "metadata": {"expected_duration": 5},
    }


def _dag_stub() -> dict[str, Any]:
    return {"metadata": {"problem": "test"}, "nodes": []}


@pytest.fixture
def isolated_sgc(tmp_path: Path) -> str:
    """Redirect SGC writes to a per-test temp file so we never touch the real
    ``templates/agent_config.j2``. Returns the tmp path as a string."""
    return str(tmp_path / "agent_config.j2")


@pytest.mark.unit
class TestStatefulHealing:
    """HEALING path exercised via stubbed skill engine / sandbox."""

    def _build_orchestrator(self, sgc_path: str) -> MetaOrchestrator:
        os.environ["SWARMFORGE_ENABLE_HEALING"] = "1"
        orch = MetaOrchestrator(max_workers=1)
        # Don't make real Anthropic calls from the reward judge either.
        orch._reward_judge = MagicMock()
        orch._reward_judge.judge = MagicMock(return_value=(True, ""))
        # Redirect the Synaptic Garbage Collector to a tmp file so we do not
        # pollute the committed ``templates/agent_config.j2`` with test data.
        orch._sgc = SynapticGarbageCollector(template_path=sgc_path)
        return orch

    def test_successful_path_no_healing(self, isolated_sgc: str) -> None:
        """A node that succeeds first-shot never enters the healing branch."""
        orch = self._build_orchestrator(isolated_sgc)
        orch._sandbox = MagicMock()
        orch._sandbox.execute = MagicMock(
            return_value={"status": "success", "output": "ok", "error": None}
        )

        result = orch._execute_node(_make_node(), _dag_stub())

        assert result["status"] == "success"
        assert "heal_status" not in result
        assert "heal_attempted" not in result

    def test_healing_success_sets_healed_status(self, isolated_sgc: str) -> None:
        """Sandbox fails once, synthesis succeeds, retry succeeds → healed."""
        orch = self._build_orchestrator(isolated_sgc)
        orch._sandbox = MagicMock()
        orch._sandbox.execute = MagicMock(
            side_effect=[
                {"status": "error", "output": "", "error": "first_failure"},
                {"status": "success", "output": "recovered", "error": None},
            ]
        )

        async def fake_synth(**_: Any) -> tuple[bool, str, str]:
            return True, "/tmp/fake_skill.py", ""

        orch._skill_engine.synthesize_on_demand = fake_synth  # type: ignore[method-assign]
        orch._skill_engine.load_skill = MagicMock(return_value=None)

        result = orch._execute_node(_make_node(), _dag_stub())

        assert result["status"] == "success"
        assert result.get("heal_status") == STATUS_HEALED
        assert result.get("heal_attempted") is True
        assert result.get("synthesized_skill") == "/tmp/fake_skill.py"
        assert orch._sandbox.execute.call_count == 2

    def test_healing_failed_retry_marks_failed_after_heal(
        self, isolated_sgc: str
    ) -> None:
        """Synthesis ok but retry still fails → failed_after_heal."""
        orch = self._build_orchestrator(isolated_sgc)
        orch._sandbox = MagicMock()
        orch._sandbox.execute = MagicMock(
            side_effect=[
                {"status": "error", "output": "", "error": "first_failure"},
                {"status": "error", "output": "", "error": "still_broken"},
            ]
        )

        async def fake_synth(**_: Any) -> tuple[bool, str, str]:
            return True, "/tmp/fake_skill.py", ""

        orch._skill_engine.synthesize_on_demand = fake_synth  # type: ignore[method-assign]
        orch._skill_engine.load_skill = MagicMock(return_value=None)

        result = orch._execute_node(_make_node(), _dag_stub())

        assert result["status"] != "success"
        assert result.get("heal_status") == STATUS_FAILED_AFTER_HEAL
        assert result.get("heal_attempted") is True
        assert "retry_failed" in result.get("heal_reason", "")

    def test_synthesis_failure_preserves_original_error(
        self, isolated_sgc: str
    ) -> None:
        """If synthesis fails, primary error and failed_after_heal both set."""
        orch = self._build_orchestrator(isolated_sgc)
        orch._sandbox = MagicMock()
        orch._sandbox.execute = MagicMock(
            return_value={
                "status": "error",
                "output": "",
                "error": "primary_error",
            }
        )

        async def fake_synth(**_: Any) -> tuple[bool, str, str]:
            return False, "", "LLM quota exhausted"

        orch._skill_engine.synthesize_on_demand = fake_synth  # type: ignore[method-assign]

        result = orch._execute_node(_make_node(), _dag_stub())

        assert result.get("heal_status") == STATUS_FAILED_AFTER_HEAL
        assert result.get("heal_attempted") is True
        assert "synthesis_failed" in result.get("heal_reason", "")
        assert result.get("error") == "primary_error"

    def test_healing_disabled_via_env_skips_branch(
        self, isolated_sgc: str
    ) -> None:
        """SWARMFORGE_ENABLE_HEALING=0 disables the whole HEALING path."""
        os.environ["SWARMFORGE_ENABLE_HEALING"] = "0"
        try:
            orch = MetaOrchestrator(max_workers=1)
            orch._reward_judge = MagicMock()
            orch._reward_judge.judge = MagicMock(return_value=(True, ""))
            orch._sgc = SynapticGarbageCollector(template_path=isolated_sgc)
            orch._sandbox = MagicMock()
            orch._sandbox.execute = MagicMock(
                return_value={
                    "status": "error",
                    "output": "",
                    "error": "boom",
                }
            )
            orch._skill_engine.synthesize_on_demand = MagicMock()  # type: ignore[method-assign]

            result = orch._execute_node(_make_node(), _dag_stub())

            assert result.get("heal_attempted") is False
            assert result.get("heal_reason") == "healing_disabled"
            orch._skill_engine.synthesize_on_demand.assert_not_called()
        finally:
            os.environ["SWARMFORGE_ENABLE_HEALING"] = "1"

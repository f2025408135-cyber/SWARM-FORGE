"""Tests for Swarm-Forge memory system — LESSON.md, SKILL.md, ExperienceLibrary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from schemas import AgentRole, LessonEntry, ExperienceVector


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_memory_dir(tmp_path: Path, monkeypatch):
    """Redirect MEMORY_DIR to a temp directory for every test."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEMORY_DIR", str(memory_dir))

    # Force re-evaluation of module-level constants by reimporting
    import memory_system
    memory_system.MEMORY_DIR = memory_dir
    memory_system.LESSON_FILE = memory_dir / "LESSON.md"
    memory_system.SKILL_FILE = memory_dir / "SKILL.md"
    memory_system.EXPERIENCE_FILE = memory_dir / "experiences.jsonl"

    yield

    # Cleanup: ensure no stale references leak between tests
    memory_system.MEMORY_DIR = Path(os.environ.get("MEMORY_DIR", "./memory"))
    memory_system.LESSON_FILE = memory_system.MEMORY_DIR / "LESSON.md"
    memory_system.SKILL_FILE = memory_system.MEMORY_DIR / "SKILL.md"
    memory_system.EXPERIENCE_FILE = memory_system.MEMORY_DIR / "experiences.jsonl"


@pytest.fixture()
def lesson_manager(tmp_path: Path, monkeypatch) -> "memory_system.LessonManager":
    from memory_system import LessonManager, MEMORY_DIR
    return LessonManager()


@pytest.fixture()
def skill_manager(tmp_path: Path, monkeypatch) -> "memory_system.SkillManager":
    from memory_system import SkillManager
    return SkillManager()


@pytest.fixture()
def experience_lib(tmp_path: Path, monkeypatch) -> "memory_system.ExperienceLibrary":
    from memory_system import ExperienceLibrary, MEMORY_DIR
    return ExperienceLibrary()


# ── LessonManager ───────────────────────────────────────────────────────────


class TestLessonManager:
    """Verify LESSON.md episodic memory read/write."""

    def test_creates_lesson_file_on_init(
        self, lesson_manager, tmp_path: Path, monkeypatch
    ) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        lesson_file = memory_dir / "LESSON.md"
        assert lesson_file.exists()
        content = lesson_file.read_text()
        assert "Swarm-Forge LESSON.md" in content
        assert "Operational Heuristics" in content

    def test_append_lesson_writes_content(
        self, lesson_manager, tmp_path: Path, monkeypatch
    ) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        lesson_file = memory_dir / "LESSON.md"

        entry = LessonEntry(
            failure_pattern="Agent retries identical prompt in a loop",
            root_cause="Missing input hash deduplication check",
            generalized_heuristic="Always hash prompt inputs before retry",
            applicable_agent_roles=[AgentRole.EXECUTOR],
            domain_tags=["retry", "dedup"],
        )
        lesson_manager.append_lesson(entry)

        content = lesson_file.read_text()
        assert "Agent retries identical prompt" in content
        assert "Always hash prompt inputs" in content
        assert "executor" in content
        assert "retry" in content

    def test_load_lessons_filters_by_role(
        self, lesson_manager, tmp_path: Path, monkeypatch
    ) -> None:
        # Append a lesson for EXECUTOR
        entry_executor = LessonEntry(
            failure_pattern="Timeout on long tasks",
            root_cause="No timeout parameter",
            generalized_heuristic="Set timeout on all subprocess calls",
            applicable_agent_roles=[AgentRole.EXECUTOR],
            domain_tags=["timeout"],
        )
        lesson_manager.append_lesson(entry_executor)

        # Append a lesson for RESEARCHER
        entry_researcher = LessonEntry(
            failure_pattern="Web search returns stale results",
            root_cause="Missing cache-bust header",
            generalized_heuristic="Include no-cache header on HTTP requests",
            applicable_agent_roles=[AgentRole.RESEARCHER],
            domain_tags=["search", "cache"],
        )
        lesson_manager.append_lesson(entry_researcher)

        # Loading for EXECUTOR should only return the executor lesson
        executor_context = lesson_manager.load_lessons_for_agent(AgentRole.EXECUTOR)
        assert "Timeout on long tasks" in executor_context
        assert "Set timeout on all subprocess" in executor_context

        # Loading for RESEARCHER should only return the researcher lesson
        researcher_context = lesson_manager.load_lessons_for_agent(AgentRole.RESEARCHER)
        assert "Web search returns stale" in researcher_context
        assert "Include no-cache header" in researcher_context

    def test_load_lessons_returns_empty_for_no_match(self, lesson_manager) -> None:
        entry = LessonEntry(
            failure_pattern="Some pattern",
            root_cause="Some cause",
            generalized_heuristic="Some heuristic",
            applicable_agent_roles=[AgentRole.AUDITOR],
            domain_tags=["audit"],
        )
        lesson_manager.append_lesson(entry)

        result = lesson_manager.load_lessons_for_agent(AgentRole.ARCHITECT)
        assert result == ""

    def test_get_full_lesson_context(self, lesson_manager) -> None:
        entry = LessonEntry(
            failure_pattern="Full context test pattern",
            root_cause="Full context test cause",
            generalized_heuristic="Full context test heuristic",
            applicable_agent_roles=[AgentRole.ORCHESTRATOR],
            domain_tags=["test"],
        )
        lesson_manager.append_lesson(entry)

        full = lesson_manager.get_full_lesson_context()
        assert "Swarm-Forge LESSON.md" in full
        assert "Full context test pattern" in full


# ── SkillManager ────────────────────────────────────────────────────────────


class TestSkillManager:
    """Verify SKILL.md reusable pattern library."""

    def test_creates_skill_file_on_init(
        self, skill_manager, tmp_path: Path, monkeypatch
    ) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        skill_file = memory_dir / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "Swarm-Forge SKILL.md" in content

    def test_append_skill_writes_content(self, skill_manager) -> None:
        skill_manager.append_skill(
            skill_name="retry_with_exponential_backoff",
            description="Exponential backoff retry pattern for transient failures",
            code_pattern="time.sleep(2 ** attempt)\nresponse = client.request()",
            applicable_roles=[AgentRole.EXECUTOR, AgentRole.RESEARCHER],
            tags=["retry", "resilience"],
        )

        from memory_system import SKILL_FILE
        content = SKILL_FILE.read_text()
        assert "retry_with_exponential_backoff" in content
        assert "Exponential backoff retry" in content
        assert "executor" in content
        assert "researcher" in content
        assert "```python" in content

    def test_load_skills_no_tags_returns_all(self, skill_manager) -> None:
        skill_manager.append_skill(
            skill_name="skill_a",
            description="First skill",
            code_pattern="pass",
            applicable_roles=[AgentRole.EXECUTOR],
            tags=["alpha"],
        )
        skill_manager.append_skill(
            skill_name="skill_b",
            description="Second skill",
            code_pattern="pass",
            applicable_roles=[AgentRole.AUDITOR],
            tags=["beta"],
        )

        from memory_system import SKILL_FILE
        result = skill_manager.load_skills_for_agent(AgentRole.EXECUTOR, tags=None)
        assert "skill_a" in result
        assert "skill_b" in result

    def test_load_skills_filters_by_tag(self, skill_manager) -> None:
        skill_manager.append_skill(
            skill_name="search_skill",
            description="Search pattern",
            code_pattern="client.search()",
            applicable_roles=[AgentRole.RESEARCHER],
            tags=["search", "http"],
        )
        skill_manager.append_skill(
            skill_name="deploy_skill",
            description="Deploy pattern",
            code_pattern="kubectl.apply()",
            applicable_roles=[AgentRole.EXECUTOR],
            tags=["deploy", "k8s"],
        )

        result = skill_manager.load_skills_for_agent(
            AgentRole.RESEARCHER, tags=["search"]
        )
        assert "search_skill" in result
        assert "deploy_skill" not in result


# ── ExperienceLibrary ───────────────────────────────────────────────────────


class TestExperienceLibrary:
    """Verify experience vector store with JSONL fallback."""

    def test_init_with_jsonl_fallback(self, experience_lib) -> None:
        """Without Milvus, should fall back gracefully to JSONL."""
        assert experience_lib.milvus_available is False

    def test_store_falls_back_to_jsonl(
        self, experience_lib, tmp_path: Path, monkeypatch
    ) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        exp_file = memory_dir / "experiences.jsonl"

        exp = ExperienceVector(
            task_description="Analyse pricing data for Q4",
            agent_role=AgentRole.RESEARCHER,
            success=True,
            key_actions=["search", "aggregate", "report"],
            outcome_summary="Generated comprehensive pricing matrix",
        )
        experience_lib.store(exp)

        assert exp_file.exists()
        lines = exp_file.read_text().strip().split("\n")
        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["task_description"] == "Analyse pricing data for Q4"
        assert parsed["success"] is True
        assert parsed["agent_role"] == "researcher"

    def test_store_multiple_experiences(self, experience_lib) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        exp_file = memory_dir / "experiences.jsonl"

        for i in range(4):
            exp = ExperienceVector(
                task_description=f"Task number {i}",
                agent_role=AgentRole.EXECUTOR,
                success=(i % 2 == 0),
                key_actions=[f"step_{i}"],
                outcome_summary=f"Result {i}",
            )
            experience_lib.store(exp)

        lines = exp_file.read_text().strip().split("\n")
        assert len(lines) == 4

    def test_retrieve_similar_returns_last_n(self, experience_lib) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        exp_file = memory_dir / "experiences.jsonl"

        for i in range(8):
            exp = ExperienceVector(
                task_description=f"Batch task {i}",
                agent_role=AgentRole.EXECUTOR,
                success=True,
                key_actions=[],
                outcome_summary=f"Completed {i}",
            )
            experience_lib.store(exp)

        results = experience_lib.retrieve_similar("query", top_k=3)
        assert len(results) == 3
        # JSONL fallback returns last N — should be entries 5, 6, 7
        assert results[-1]["task_description"] == "Batch task 7"

    def test_retrieve_similar_success_only(self, experience_lib) -> None:
        memory_dir = Path(os.getenv("MEMORY_DIR"))
        exp_file = memory_dir / "experiences.jsonl"

        # 3 successful, 2 failed
        for i in range(3):
            exp = ExperienceVector(
                task_description=f"Good task {i}",
                agent_role=AgentRole.EXECUTOR,
                success=True,
                key_actions=[],
                outcome_summary="Worked",
            )
            experience_lib.store(exp)

        for i in range(2):
            exp = ExperienceVector(
                task_description=f"Bad task {i}",
                agent_role=AgentRole.EXECUTOR,
                success=False,
                key_actions=[],
                outcome_summary="Failed",
            )
            experience_lib.store(exp)

        results = experience_lib.retrieve_similar("query", top_k=10, success_only=True)
        assert len(results) == 3
        for r in results:
            assert r["success"] is True

    def test_retrieve_empty_file(self, experience_lib) -> None:
        results = experience_lib.retrieve_similar("nothing here")
        assert results == []

    def test_embed_returns_deterministic_vector(self, experience_lib) -> None:
        v1 = experience_lib._embed("test query")
        v2 = experience_lib._embed("test query")
        assert len(v1) == 1536
        assert len(v2) == 1536
        assert v1 == v2  # Same input → same hash seed → same vector

    def test_embed_different_inputs_differ(self, experience_lib) -> None:
        v1 = experience_lib._embed("alpha")
        v2 = experience_lib._embed("beta")
        assert v1 != v2

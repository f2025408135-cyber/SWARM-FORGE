"""Tests for Swarm-Forge inter-agent contract schemas."""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from schemas import (
    AgentRole,
    BudgetMapContract,
    FailureCategory,
    MCPToolDefinition,
    ModelTier,
    NodeInputContract,
    NodeOutputContract,
    NodeTokenEstimate,
    TaskComplexity,
    TOONSchema,
    DAGTopologyContract,
    FastMCPServerBlueprint,
    HPFEContract,
    RCAContract,
    LessonEntry,
    ExperienceVector,
)


# ── NodeInputContract ───────────────────────────────────────────────────────


class TestNodeInputContract:
    """Validate the strictly typed DAG node input payload."""

    def test_valid_minimal_contract(self) -> None:
        contract = NodeInputContract(
            node_id="node-001",
            task_description="Analyse the data pipeline throughput",
        )
        assert contract.node_id == "node-001"
        assert contract.task_description == "Analyse the data pipeline throughput"
        assert contract.session_id != ""
        assert contract.complexity == TaskComplexity.STANDARD
        assert contract.model_tier == ModelTier.SONNET
        assert contract.token_budget == 50000
        assert contract.input_data == {}
        assert contract.upstream_ast_summaries == {}

    def test_valid_full_contract(self) -> None:
        contract = NodeInputContract(
            node_id="node-002",
            task_description="Research competitor pricing strategies in SaaS",
            input_data={"market": "B2B SaaS"},
            upstream_ast_summaries={"node-001": "class PricingSurvey ..."},
            complexity=TaskComplexity.COMPLEX,
            token_budget=120000,
            model_tier=ModelTier.OPUS,
        )
        assert contract.complexity == TaskComplexity.COMPLEX
        assert contract.model_tier == ModelTier.OPUS
        assert contract.token_budget == 120000

    def test_task_description_min_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NodeInputContract(node_id="n", task_description="Too short")
        errors = exc_info.value.errors()
        assert any("at least 10 characters" in str(e) for e in errors)

    def test_task_description_max_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NodeInputContract(
                node_id="n",
                task_description="x" * 2001,
            )
        errors = exc_info.value.errors()
        assert any("at most 2000 characters" in str(e) for e in errors)

    def test_forbidden_phrase_write_the_code(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NodeInputContract(
                node_id="n",
                task_description="Please write the code for the API endpoint",
            )
        errors = exc_info.value.errors()
        assert any("write the code" in str(e) for e in errors)

    def test_forbidden_phrase_implement_this(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NodeInputContract(
                node_id="n",
                task_description="implement this feature for user auth",
            )
        errors = exc_info.value.errors()
        assert any("implement this" in str(e) for e in errors)

    def test_forbidden_phrase_create_a_script(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            NodeInputContract(
                node_id="n",
                task_description="create a script that migrates the database",
            )
        errors = exc_info.value.errors()
        assert any("create a script" in str(e) for e in errors)

    def test_token_budget_minimum(self) -> None:
        with pytest.raises(ValidationError):
            NodeInputContract(
                node_id="n",
                task_description="Validate minimum token budget constraint",
                token_budget=500,
            )

    def test_token_budget_maximum(self) -> None:
        with pytest.raises(ValidationError):
            NodeInputContract(
                node_id="n",
                task_description="Validate maximum token budget constraint test",
                token_budget=600000,
            )

    def test_case_insensitive_forbidden_phrase(self) -> None:
        with pytest.raises(ValidationError):
            NodeInputContract(
                node_id="n",
                task_description="WRITE THE CODE for the integration test suite",
            )

    def test_session_id_is_uuid(self) -> None:
        contract = NodeInputContract(
            node_id="n",
            task_description="Verify session ID is a valid UUID format",
        )
        # Should not raise — valid UUID
        uuid.UUID(contract.session_id)

    def test_valid_task_with_code_keywords_allowed(self) -> None:
        """Phrases like 'analyse', 'review', 'evaluate' must pass."""
        contract = NodeInputContract(
            node_id="n",
            task_description="Evaluate the error handling patterns in module X",
        )
        assert contract.task_description.startswith("Evaluate")


# ── NodeTokenEstimate ───────────────────────────────────────────────────────


class TestNodeTokenEstimate:
    """Validate per-node token budget estimation."""

    def test_worst_case_calculation(self) -> None:
        estimate = NodeTokenEstimate(
            node_id="est-001",
            role=AgentRole.EXECUTOR,
            estimated_input_tokens=4000,
            estimated_output_tokens=2000,
            tool_calls_expected=3,
            avg_tokens_per_tool_result=500,
        )
        expected_base = 4000 + 2000 + (3 * 500)  # 7500
        assert estimate.worst_case_tokens == int(expected_base * 2.5)

    def test_zero_tool_calls(self) -> None:
        estimate = NodeTokenEstimate(
            node_id="est-002",
            role=AgentRole.REVIEWER,
            estimated_input_tokens=3000,
            estimated_output_tokens=1000,
            tool_calls_expected=0,
            avg_tokens_per_tool_result=0,
        )
        assert estimate.worst_case_tokens == int((3000 + 1000) * 2.5)

    def test_large_estimates(self) -> None:
        estimate = NodeTokenEstimate(
            node_id="est-003",
            role=AgentRole.ORCHESTRATOR,
            estimated_input_tokens=50000,
            estimated_output_tokens=10000,
            tool_calls_expected=10,
            avg_tokens_per_tool_result=2000,
        )
        base = 50000 + 10000 + (10 * 2000)  # 80000
        assert estimate.worst_case_tokens == int(base * 2.5)


# ── BudgetMapContract ───────────────────────────────────────────────────────


class TestBudgetMapContract:
    """Validate the full swarm budget mapper contract."""

    def _make_estimate(self, node_id: str, input_t: int, output_t: int) -> NodeTokenEstimate:
        return NodeTokenEstimate(
            node_id=node_id,
            role=AgentRole.EXECUTOR,
            estimated_input_tokens=input_t,
            estimated_output_tokens=output_t,
            tool_calls_expected=2,
            avg_tokens_per_tool_result=500,
        )

    def test_total_worst_case_summed(self) -> None:
        e1 = self._make_estimate("n1", 4000, 2000)
        e2 = self._make_estimate("n2", 6000, 3000)
        budget = BudgetMapContract(
            session_id="sess-1",
            task_prompt="Build microservice mesh",
            node_estimates=[e1, e2],
        )
        assert budget.total_worst_case_tokens == e1.worst_case_tokens + e2.worst_case_tokens

    def test_no_partitioning_when_under_limit(self) -> None:
        estimates = [self._make_estimate("n1", 100, 50)]
        budget = BudgetMapContract(
            session_id="sess-2",
            task_prompt="Small task",
            node_estimates=estimates,
        )
        assert budget.requires_partitioning is False
        assert budget.recommended_partitions == 1

    def test_partitioning_triggered_when_over_limit(self) -> None:
        # Force over the default 900k context limit
        estimates = [
            NodeTokenEstimate(
                node_id="big-1",
                role=AgentRole.ORCHESTRATOR,
                estimated_input_tokens=500_000,
                estimated_output_tokens=100_000,
                tool_calls_expected=10,
                avg_tokens_per_tool_result=10_000,
            ),
        ]
        budget = BudgetMapContract(
            session_id="sess-3",
            task_prompt="Massive task exceeding context limit",
            node_estimates=estimates,
        )
        assert budget.requires_partitioning is True
        assert budget.recommended_partitions >= 2

    def test_recommended_partitions_calculation(self) -> None:
        # Two nodes that together exceed 900k but each under
        estimates = [
            NodeTokenEstimate(
                node_id="big-a",
                role=AgentRole.RESEARCHER,
                estimated_input_tokens=400_000,
                estimated_output_tokens=80_000,
                tool_calls_expected=5,
                avg_tokens_per_tool_result=5000,
            ),
            NodeTokenEstimate(
                node_id="big-b",
                role=AgentRole.SYNTHESIZER,
                estimated_input_tokens=400_000,
                estimated_output_tokens=80_000,
                tool_calls_expected=5,
                avg_tokens_per_tool_result=5000,
            ),
        ]
        budget = BudgetMapContract(
            session_id="sess-4",
            task_prompt="Dual heavy task",
            node_estimates=estimates,
        )
        if budget.requires_partitioning:
            expected_parts = budget.total_worst_case_tokens // 900_000 + 1
            assert budget.recommended_partitions == expected_parts

    def test_empty_estimates(self) -> None:
        budget = BudgetMapContract(
            session_id="sess-5",
            task_prompt="No nodes yet",
            node_estimates=[],
        )
        assert budget.total_worst_case_tokens == 0
        assert budget.requires_partitioning is False
        assert budget.recommended_partitions == 1


# ── Additional Schema Smoke Tests ───────────────────────────────────────────


class TestNodeOutputContract:
    def test_success_output(self) -> None:
        out = NodeOutputContract(
            node_id="n1", session_id="s1", success=True,
            output_data={"result": "ok"},
            tokens_consumed=1234,
            next_node_recommendations=["node-2", "node-3"],
        )
        assert out.success is True
        assert len(out.next_node_recommendations) == 2

    def test_failure_output(self) -> None:
        out = NodeOutputContract(
            node_id="n1", session_id="s1", success=False,
            error_message="Timeout after 30s",
        )
        assert out.success is False
        assert out.error_message == "Timeout after 30s"


class TestTOONSchema:
    def test_to_dict_list(self) -> None:
        toon = TOONSchema(
            headers=["name", "score"],
            rows=[["alice", 95], ["bob", 87]],
        )
        result = toon.to_dict_list()
        assert result == [
            {"name": "alice", "score": 95},
            {"name": "bob", "score": 87},
        ]

    def test_empty_rows(self) -> None:
        toon = TOONSchema(headers=["a"], rows=[])
        assert toon.to_dict_list() == []


class TestMCPToolDefinition:
    def test_valid_tool_name(self) -> None:
        tool = MCPToolDefinition(
            tool_name="search_documents",
            description="Search across indexed document store",
            parameters={"query": "str"},
            return_type="list[dict]",
            endpoint_path="/api/search",
        )
        assert tool.tool_name == "search_documents"

    def test_invalid_tool_name_uppercase(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolDefinition(
                tool_name="SearchDocs",
                description="Invalid tool name with uppercase start",
                parameters={},
                return_type="str",
                endpoint_path="/api/search",
            )

    def test_description_too_short(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolDefinition(
                tool_name="tool_a",
                description="Too short",
                parameters={},
                return_type="str",
                endpoint_path="/api/x",
            )


class TestHPFEContract:
    def test_valid_hpfe(self) -> None:
        hpfe = HPFEContract(
            gen_ai_operation_name="dag.execute",
            gen_ai_agent_name="executor-01",
            gen_ai_conversation_id="conv-123",
            error_type="RuntimeError",
            error_traceback="Traceback (most recent call last)...",
            failure_category=FailureCategory.CODE,
            tokens_at_failure=4200,
        )
        assert hpfe.failure_category == FailureCategory.CODE
        assert hpfe.retry_count == 0


class TestRCAContract:
    def test_valid_rca(self) -> None:
        rca = RCAContract(
            trace_id="t-1",
            failure_category=FailureCategory.PROMPT,
            root_cause_summary="Ambiguous task description caused infinite loop",
            affected_file="executor.py",
            affected_line=142,
            textual_gradient="high",
            remediation_action="mutate_prompt",
            confidence_score=0.92,
        )
        assert rca.remediation_action == "mutate_prompt"
        assert rca.confidence_score == 0.92

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            RCAContract(
                trace_id="t-2",
                failure_category=FailureCategory.TIMEOUT,
                root_cause_summary="Test",
                textual_gradient="low",
                remediation_action="escalate",
                confidence_score=1.5,
            )


class TestLessonEntry:
    def test_valid_lesson(self) -> None:
        lesson = LessonEntry(
            failure_pattern="Agent retries identical prompt",
            root_cause="Missing deduplication check",
            generalized_heuristic="Always hash prompt before retry",
            applicable_agent_roles=[AgentRole.EXECUTOR, AgentRole.RESEARCHER],
            domain_tags=["retry", "dedup"],
        )
        assert len(lesson.applicable_agent_roles) == 2
        assert lesson.verification_count == 1


class TestExperienceVector:
    def test_valid_experience(self) -> None:
        exp = ExperienceVector(
            task_description="Analyse competitor pricing",
            agent_role=AgentRole.RESEARCHER,
            success=True,
            key_actions=["search", "aggregate", "report"],
            outcome_summary="Generated pricing matrix",
        )
        assert exp.success is True
        assert exp.embedding is None

    def test_experience_with_embedding(self) -> None:
        exp = ExperienceVector(
            task_description="Failed deployment rollback",
            agent_role=AgentRole.EXECUTOR,
            success=False,
            key_actions=["deploy", "detect_failure", "rollback"],
            failure_pattern="Missing health check",
            outcome_summary="Rolled back in 12s",
            embedding=[0.1, 0.2, 0.3],
        )
        assert len(exp.embedding) == 3


class TestFastMCPServerBlueprint:
    def test_valid_blueprint(self) -> None:
        blueprint = FastMCPServerBlueprint(
            server_name="research-tools",
            base_url="http://localhost:8001",
            tools=[
                MCPToolDefinition(
                    tool_name="web_search",
                    description="Search the web for recent information",
                    parameters={"query": "str", "limit": "int"},
                    return_type="list[dict]",
                    endpoint_path="/search",
                ),
            ],
        )
        assert blueprint.auth_scheme == "bearer"
        assert blueprint.rate_limit_per_minute == 60
        assert len(blueprint.tools) == 1


class TestDAGTopologyContract:
    def test_valid_topology(self) -> None:
        topo = DAGTopologyContract(
            task_summary="Build data pipeline",
            nodes=[{"id": "n1", "role": "researcher"}],
            edges=[("n1", "n2")],
            critical_path=["n1", "n2", "n3"],
            deployment_topology="distributed",
        )
        assert topo.deployment_topology == "distributed"
        assert len(topo.critical_path) == 3

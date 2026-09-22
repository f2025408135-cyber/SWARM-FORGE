"""
Swarm-Forge Inter-Agent Contract Schemas
All inter-agent communication MUST use these Pydantic models.
Natural language handoffs are PROHIBITED.
"""

from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, Literal, Optional
from datetime import datetime
from enum import Enum
import uuid


# ── Enums ──────────────────────────────────────────────────────────────────

class ModelTier(str, Enum):
    OPUS = "claude-opus-4-7"
    SONNET = "claude-sonnet-4-5"
    HAIKU = "claude-haiku-4-5-20251001"


class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    STANDARD = "standard"
    COMPLEX = "complex"
    FRONTIER = "frontier"


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    SYNTHESIZER = "synthesizer"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    EXECUTOR = "executor"
    ARCHITECT = "architect"


class FailureCategory(str, Enum):
    INFRASTRUCTURE = "infrastructure_change"
    PROMPT = "prompt_misalignment"
    CODE = "code_logic_drift"
    BUDGET = "budget_exhaustion"
    TIMEOUT = "execution_timeout"


# ── Core DAG Contracts ──────────────────────────────────────────────────────

class NodeInputContract(BaseModel):
    """Strictly typed input payload passed to every DAG node."""

    model_config = ConfigDict(protected_namespaces=())

    node_id: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_description: str = Field(min_length=10, max_length=2000)
    input_data: dict[str, Any] = Field(default_factory=dict)
    upstream_ast_summaries: dict[str, str] = Field(default_factory=dict)
    complexity: TaskComplexity = TaskComplexity.STANDARD
    token_budget: int = Field(default=50000, ge=1000, le=500000)
    model_tier: ModelTier = ModelTier.SONNET

    @field_validator("task_description")
    @classmethod
    def no_natural_language_code(cls, v: str) -> str:
        forbidden = ["write the code", "implement this", "create a script"]
        for phrase in forbidden:
            if phrase.lower() in v.lower():
                raise ValueError(
                    f"Task descriptions must specify WHAT not HOW. "
                    f"Remove imperative phrase: '{phrase}'"
                )
        return v


class NodeOutputContract(BaseModel):
    """Strictly typed output payload from every DAG node."""
    node_id: str
    session_id: str
    success: bool
    output_data: dict[str, Any] = Field(default_factory=dict)
    ast_summary: str = ""
    tokens_consumed: int = 0
    execution_duration_ms: float = 0.0
    error_message: Optional[str] = None
    next_node_recommendations: list[str] = Field(default_factory=list)


class DAGTopologyContract(BaseModel):
    """The compiled DAG topology output by the TDAG engine."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_summary: str
    nodes: list[dict[str, Any]]
    edges: list[tuple[str, str]]
    parallel_groups: list[list[str]] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    estimated_total_tokens: int = 0
    worst_case_tokens: int = 0
    recommended_meta_agent_count: int = 1
    deployment_topology: Literal["single", "distributed"] = "single"


# ── Budget Mapper Contracts ─────────────────────────────────────────────────

class NodeTokenEstimate(BaseModel):
    """Pre-deployment token budget estimate for a single DAG node."""
    node_id: str
    role: AgentRole
    estimated_input_tokens: int
    estimated_output_tokens: int
    tool_calls_expected: int
    avg_tokens_per_tool_result: int
    worst_case_tokens: int = 0

    def model_post_init(self, __context: Any) -> None:
        base = (
            self.estimated_input_tokens
            + self.estimated_output_tokens
            + (self.tool_calls_expected * self.avg_tokens_per_tool_result)
        )
        self.worst_case_tokens = int(base * 2.5)


class BudgetMapContract(BaseModel):
    """Complete pre-deployment token budget map for the entire swarm."""
    session_id: str
    task_prompt: str
    node_estimates: list[NodeTokenEstimate]
    total_worst_case_tokens: int = 0
    context_limit: int = 900_000
    requires_partitioning: bool = False
    recommended_partitions: int = 1

    def model_post_init(self, __context: Any) -> None:
        self.total_worst_case_tokens = sum(
            n.worst_case_tokens for n in self.node_estimates
        )
        self.requires_partitioning = (
            self.total_worst_case_tokens > self.context_limit
        )
        if self.requires_partitioning:
            self.recommended_partitions = (
                self.total_worst_case_tokens // self.context_limit + 1
            )


# ── FastMCP Generation Contracts ────────────────────────────────────────────

class TOONSchema(BaseModel):
    """Token-Oriented Object Notation — compressed LLM output format."""
    headers: list[str]
    rows: list[list[Any]]
    schema_version: str = "1.0"

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [dict(zip(self.headers, row)) for row in self.rows]


class MCPToolDefinition(BaseModel):
    """Definition for a single FastMCP tool to be generated."""
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=20)
    parameters: dict[str, str]
    return_type: str
    endpoint_path: str
    http_method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    requires_auth: bool = True


class FastMCPServerBlueprint(BaseModel):
    """Complete blueprint for a generated FastMCP server."""
    server_name: str
    base_url: str
    tools: list[MCPToolDefinition]
    auth_scheme: Literal["bearer", "api_key", "none"] = "bearer"
    rate_limit_per_minute: int = 60


# ── Self-Healing Contracts ──────────────────────────────────────────────────

class HPFEContract(BaseModel):
    """High-Priority Failure Event payload (OTel GenAI compliant)."""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    gen_ai_operation_name: str
    gen_ai_agent_name: str
    gen_ai_conversation_id: str
    error_type: str
    error_traceback: str
    failure_category: FailureCategory
    tokens_at_failure: int = 0
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0


class RCAContract(BaseModel):
    """Root Cause Analysis output from Delta Debugging."""
    trace_id: str
    failure_category: FailureCategory
    root_cause_summary: str
    affected_file: Optional[str] = None
    affected_line: Optional[int] = None
    textual_gradient: str
    remediation_action: Literal["rewrite_code", "mutate_prompt", "update_mcp", "escalate"]
    confidence_score: float = Field(ge=0.0, le=1.0)


# ── Memory Contracts ────────────────────────────────────────────────────────

class LessonEntry(BaseModel):
    """A single entry in LESSON.md episodic memory."""
    lesson_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    failure_pattern: str
    root_cause: str
    generalized_heuristic: str
    applicable_agent_roles: list[AgentRole]
    domain_tags: list[str] = Field(default_factory=list)
    verification_count: int = 1


class ExperienceVector(BaseModel):
    """Vectorizable experience for semantic retrieval from Milvus."""
    experience_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_description: str
    agent_role: AgentRole
    success: bool
    key_actions: list[str]
    failure_pattern: Optional[str] = None
    outcome_summary: str
    embedding: Optional[list[float]] = None

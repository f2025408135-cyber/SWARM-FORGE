"""Swarm-Forge — autonomous multi-agent DAG orchestration framework.

Wires together the eight core modules that make up the Swarm-Forge Meta-Agent:
zero-trust input validation, DAG planning via the Anthropic API, parallel DAG
execution with sandboxed child processes, synchronised state persistence,
drift detection, AST-based error compression, semantic reward judging, and
OTel-style failure logging.

Typical programmatic usage::

    from src import MetaOrchestrator
    result = MetaOrchestrator().run("Optimize our global supply chain…")

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

from .agent_guard import (
    ActionFirewallVisitor,
    CognitiveFirewall,
    GeometricDOMSanitizer,
    verify_agent_action,
)
from .ast_context_compressor import ASTContextCompressor
from .dag_execution_engine import (
    BayesianBeliefState,
    DAGManager,
    ParallelDAGRunner,
    ROLocker,
)
from .dag_planner import DagMetadata, DagNode, DagPlan, plan_dag
from .drift_metrics import DriftDetector
from .execution_sandbox import SandboxExecutor
from .memory_system import SynapticGarbageCollector
from .meta_orchestrator import MetaOrchestrator
from .mutex_storage import SynchronizedJSONStore
from .otel_telemetry_logger import HPFELogger
from .reward_judge import RewardSwarmJudge
from .skill_synthesis import SkillSynthesisEngine
from .zero_trust_firewall import AgentFirewall

__all__: list[str] = [
    "ASTContextCompressor",
    "ActionFirewallVisitor",
    "AgentFirewall",
    "BayesianBeliefState",
    "CognitiveFirewall",
    "DAGManager",
    "DagMetadata",
    "DagNode",
    "DagPlan",
    "DriftDetector",
    "GeometricDOMSanitizer",
    "HPFELogger",
    "MetaOrchestrator",
    "ParallelDAGRunner",
    "ROLocker",
    "RewardSwarmJudge",
    "SandboxExecutor",
    "SkillSynthesisEngine",
    "SynchronizedJSONStore",
    "SynapticGarbageCollector",
    "plan_dag",
    "verify_agent_action",
]

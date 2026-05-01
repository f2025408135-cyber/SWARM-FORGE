"""AgentGuard — Deterministic three-layer zero-trust middleware for Swarm-Forge.

Implements DeepMind AI Agent Traps defenses (April 2026):
  Layer 1: GeometricDOMSanitizer  — Perception Defense (Content Injection)
  Layer 2: CognitiveFirewall      — Memory Taint Analysis (Cognitive State)
  Layer 3: ActionFirewallVisitor  — AST Capability Dropping (Behavioral Control)

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

from .action_firewall import ActionFirewallVisitor, verify_agent_action
from .cognitive_firewall import CognitiveFirewall
from .dom_sanitizer import GeometricDOMSanitizer

__all__: list[str] = [
    "ActionFirewallVisitor",
    "CognitiveFirewall",
    "GeometricDOMSanitizer",
    "verify_agent_action",
]

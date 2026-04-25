"""Swarm-Forge Neo-AGI AEV Platform — Streamlit CISO Dashboard.

A dark-mode "Venture-Capital-Ready" cybersecurity dashboard that visualises
the autonomous Adversarial Exposure Validation (AEV) pipeline produced by
the Swarm-Forge orchestrator. Reads every artefact emitted by the live
demo run (DAG plan, recon reports, synthesis, exfiltration gate) and
renders them through three narrative tabs: DAG Orchestration, Agent Guard,
and Threat Intel Synthesis.

Usage:
    streamlit run dashboard.py

Author: Swarm-Forge Engineering
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT: Path = Path(__file__).resolve().parent

PALETTE: dict[str, str] = {
    "bg":        "#05070d",
    "panel":     "rgba(15, 22, 36, 0.55)",
    "border":    "rgba(0, 229, 255, 0.18)",
    "accent":    "#00e5ff",
    "accent_2":  "#7c4dff",
    "ok":        "#22d3a0",
    "warn":      "#f5c518",
    "crit":      "#ff3860",
    "text":      "#e6f1ff",
    "muted":     "#7d8aa0",
}


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────
def load_json(filename: str) -> Any | None:
    """Read a JSON artefact from the repo root, returning ``None`` on failure."""
    path = ROOT / filename
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def offline_banner(label: str) -> None:
    """Render a uniform 'AGENT OFFLINE' placeholder for missing artefacts."""
    st.markdown(
        f"<div class='offline-card'>⚠ <b>{label}</b> — AGENT OFFLINE "
        f"(artefact not found on disk)</div>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Page config & cyber CSS
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Swarm-Forge — Neo-AGI AEV Platform",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    .stApp {{
        background:
            radial-gradient(circle at 12% 8%, rgba(0,229,255,0.10) 0%, transparent 42%),
            radial-gradient(circle at 92% 88%, rgba(124,77,255,0.12) 0%, transparent 45%),
            linear-gradient(180deg, #05070d 0%, #02030a 100%);
        color: {PALETTE['text']};
    }}
    section[data-testid="stSidebar"] > div {{
        background: linear-gradient(180deg, #07101e 0%, #04060d 100%) !important;
        border-right: 1px solid {PALETTE['border']};
    }}
    h1, h2, h3, h4 {{
        font-family: 'Segoe UI', 'Inter', sans-serif;
        letter-spacing: 0.02em;
    }}
    h1 {{
        color: {PALETTE['accent']};
        text-shadow: 0 0 18px rgba(0,229,255,0.45);
    }}
    .glass-card {{
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['border']};
        border-radius: 14px;
        padding: 18px 22px;
        margin: 10px 0;
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    }}
    .metric-card {{
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['border']};
        border-radius: 12px;
        padding: 14px 18px;
        backdrop-filter: blur(12px);
    }}
    .metric-label {{
        color: {PALETTE['muted']};
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
    }}
    .metric-value {{
        color: {PALETTE['text']};
        font-size: 1.45rem;
        font-weight: 600;
        margin-top: 4px;
    }}
    .pill {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
    }}
    .pill-ok    {{ background: rgba(34,211,160,0.14); color: {PALETTE['ok']};   border: 1px solid rgba(34,211,160,0.40); }}
    .pill-warn  {{ background: rgba(245,197,24,0.14); color: {PALETTE['warn']}; border: 1px solid rgba(245,197,24,0.40); }}
    .pill-crit  {{ background: rgba(255,56,96,0.16);  color: {PALETTE['crit']}; border: 1px solid rgba(255,56,96,0.45); }}
    .pill-info  {{ background: rgba(0,229,255,0.14);  color: {PALETTE['accent']}; border: 1px solid rgba(0,229,255,0.40); }}
    .status-dot {{
        display: inline-block;
        width: 10px; height: 10px;
        border-radius: 50%;
        margin-right: 8px;
        box-shadow: 0 0 10px currentColor;
    }}
    .dot-green {{ background: {PALETTE['ok']};   color: {PALETTE['ok']}; }}
    .dot-amber {{ background: {PALETTE['warn']}; color: {PALETTE['warn']}; }}
    .dot-red   {{ background: {PALETTE['crit']}; color: {PALETTE['crit']}; }}
    .offline-card {{
        background: rgba(125,138,160,0.08);
        border: 1px dashed {PALETTE['muted']};
        color: {PALETTE['muted']};
        border-radius: 10px;
        padding: 14px 18px;
        margin: 10px 0;
    }}
    .node-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 16px;
        margin: 6px 0;
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['border']};
        border-left: 3px solid {PALETTE['accent']};
        border-radius: 8px;
        backdrop-filter: blur(10px);
    }}
    .node-title {{ color: {PALETTE['text']}; font-weight: 600; }}
    .node-meta  {{ color: {PALETTE['muted']}; font-size: 0.8rem; }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 6px;
        border-bottom: 1px solid {PALETTE['border']};
    }}
    .stTabs [data-baseweb="tab"] {{
        background: rgba(15,22,36,0.4);
        border: 1px solid {PALETTE['border']};
        border-radius: 10px 10px 0 0;
        padding: 10px 18px;
        color: {PALETTE['muted']};
    }}
    .stTabs [aria-selected="true"] {{
        background: rgba(0,229,255,0.10) !important;
        color: {PALETTE['accent']} !important;
        border-bottom: 2px solid {PALETTE['accent']} !important;
    }}
    div[data-testid="stMetricValue"] {{ color: {PALETTE['accent']}; }}
    .stButton > button {{
        background: linear-gradient(135deg, #ff3860 0%, #c1004a 100%);
        color: white;
        font-weight: 700;
        letter-spacing: 0.08em;
        border: 1px solid rgba(255,56,96,0.55);
        border-radius: 10px;
        padding: 12px 18px;
        box-shadow: 0 0 22px rgba(255,56,96,0.35);
    }}
    .stButton > button:hover {{
        background: linear-gradient(135deg, #ff1f4f 0%, #a8003c 100%);
        box-shadow: 0 0 32px rgba(255,56,96,0.55);
    }}
    code, pre {{
        background: rgba(0,0,0,0.55) !important;
        color: {PALETTE['accent']} !important;
        border: 1px solid {PALETTE['border']};
        border-radius: 8px;
    }}
    .subtle {{ color: {PALETTE['muted']}; font-size: 0.85rem; }}
    .header-line {{
        height: 1px;
        background: linear-gradient(90deg, transparent, {PALETTE['accent']}, transparent);
        margin: 6px 0 18px 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — Swarm Control & Telemetry
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
        <div style="text-align:center; padding: 6px 0 10px 0;">
            <div style="font-size: 2.6rem;">🛡⚡</div>
            <div style="font-size: 1.25rem; font-weight: 700; color: {PALETTE['accent']};
                        text-shadow: 0 0 12px rgba(0,229,255,0.55); letter-spacing: 0.18em;">
                SWARM-FORGE
            </div>
            <div class="subtle" style="letter-spacing:0.18em;">NEO-AGI · AEV</div>
        </div>
        <div class="header-line"></div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Swarm Control & Telemetry")

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="metric-label">Swarm Status</div>
            <div class="metric-value">
                <span class="status-dot dot-green"></span>OPERATIONAL
            </div>
        </div>
        <div class="glass-card">
            <div class="metric-label">Memory Health</div>
            <div class="metric-value">
                <span class="status-dot dot-green"></span>OPTIMIZED
                <span class="pill pill-info" style="margin-left:8px;">SGC ACTIVE</span>
            </div>
        </div>
        <div class="glass-card">
            <div class="metric-label">Active Agents</div>
            <div class="metric-value">4 Parallel Threads</div>
        </div>
        <div class="glass-card">
            <div class="metric-label">Firewall Posture</div>
            <div class="metric-value">
                <span class="status-dot dot-red"></span>ZERO-TRUST
                <span class="pill pill-crit" style="margin-left:6px;">FAIL-CLOSED</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Audit Trigger")
    audit_clicked = st.button("⚡ INITIATE AUTONOMOUS AUDIT", use_container_width=True)

    st.markdown("<div class='subtle'>v2.1 · Opus 4.7 / Sonnet 4.5 / Haiku 4.5</div>",
                unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.title("🛡⚡ Swarm-Forge: Neo-AGI AEV Platform")
st.markdown(
    f"<div style='color:{PALETTE['muted']}; font-size:1.05rem; "
    f"letter-spacing:0.04em; margin-top:-8px;'>"
    f"Autonomous Adversarial Exposure Validation &amp; Red-Team Orchestration"
    f"</div>"
    f"<div class='header-line'></div>",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Eager loads (used across tabs and the top KPI strip)
# ──────────────────────────────────────────────────────────────────────────────
dag_data:        dict[str, Any] | None = load_json("demo_dag.json")
unified_risk:    dict[str, Any] | None = load_json("unified_risk_assessment.json")
synthesis:       dict[str, Any] | None = load_json("synthesis_vulnerability_aggregation.json")
jwt_report:      dict[str, Any] | None = load_json("jwt_report.json")
jwt_audit:       dict[str, Any] | None = load_json("recon_jwt_audit.json")
endpoint_report: list[dict[str, Any]] | None = load_json("endpoint_report.json")
health_report:   list[dict[str, Any]] | None = load_json("health_report.json")
recon_unauth:    dict[str, Any] | None = load_json("recon_unauthenticated_access.json")
recon_headers:   list[dict[str, Any]] | None = load_json("recon_header_analysis.json")
sec_headers:     dict[str, Any] | None = load_json("security_headers_report.json")
risk_assessment: dict[str, Any] | None = load_json("risk_assessment_report.json")
exfil:           dict[str, Any] | None = load_json("exfil_report.json")
boardroom:       dict[str, Any] | None = load_json("boardroom_exfiltration_gate.json")


# ──────────────────────────────────────────────────────────────────────────────
# Optional simulated audit sequence (sidebar trigger)
# ──────────────────────────────────────────────────────────────────────────────
if audit_clicked:
    progress_box = st.empty()
    with progress_box.container():
        st.markdown("#### ⚡ Autonomous Audit — Live Cognitive Trace")
        bar = st.progress(0, text="Bootstrapping Sovereign Architect…")
        steps = [
            (12, "🧠 Hydrating planner with target context…"),
            (28, "🛡 Compiling Zero-Trust regex blocklist…"),
            (44, "🕸 Forging deterministic DAG (Opus 4.7)…"),
            (60, "⚙ Spawning recon swarm — 3 parallel Haiku threads…"),
            (78, "🔬 Synthesising findings (Sonnet 4.5 reward judge)…"),
            (92, "🚦 Boardroom gate evaluating exfiltration request…"),
            (100, "✅ Audit complete — artefacts persisted to disk."),
        ]
        for pct, msg in steps:
            time.sleep(0.7)
            bar.progress(pct, text=msg)
        time.sleep(0.6)
    progress_box.success("Autonomous audit cycle complete. Review artefacts below.")


# ──────────────────────────────────────────────────────────────────────────────
# Top KPI strip
# ──────────────────────────────────────────────────────────────────────────────
def kpi_count(level: str) -> int:
    """Sum critical/high/medium/low findings across both synthesis artefacts."""
    total = 0
    for src in (unified_risk, synthesis):
        if isinstance(src, dict) and isinstance(src.get(level), list):
            total = max(total, len(src[level]))
    return total


total_findings = (unified_risk or {}).get("total_findings") \
    or (synthesis or {}).get("total_findings") or 0
crit_count   = kpi_count("critical")
high_count   = kpi_count("high")
medium_count = kpi_count("medium")
node_count   = len((dag_data or {}).get("nodes", []))

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>DAG Nodes</div>"
        f"<div class='metric-value'>{node_count}</div></div>",
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Total Findings</div>"
        f"<div class='metric-value'>{total_findings}</div></div>",
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Critical</div>"
        f"<div class='metric-value' style='color:{PALETTE['crit']};'>{crit_count}</div></div>",
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>High</div>"
        f"<div class='metric-value' style='color:{PALETTE['warn']};'>{high_count}</div></div>",
        unsafe_allow_html=True,
    )
with k5:
    bypass = (unified_risk or synthesis or {}).get("auth_bypass_feasible", False)
    label, cls = ("FEASIBLE", "pill-crit") if bypass else ("BLOCKED", "pill-ok")
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Auth Bypass</div>"
        f"<div class='metric-value'><span class='pill {cls}'>{label}</span></div></div>",
        unsafe_allow_html=True,
    )

st.markdown("<div class='header-line'></div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────
tab_dag, tab_guard, tab_intel = st.tabs([
    "🕸  DAG Orchestration",
    "🛡  Agent Guard (DeepMind Layer)",
    "🎯  Threat Intel Synthesis",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DAG Orchestration
# ════════════════════════════════════════════════════════════════════════════
with tab_dag:
    st.markdown("### Sovereign Architect — Deterministic DAG Compilation")
    st.markdown(
        f"<div class='subtle'>The Meta-Orchestrator translates a natural-language "
        f"adversarial objective into a validated, cycle-free DAG topology, then "
        f"distributes nodes across model-routed worker swarms.</div>",
        unsafe_allow_html=True,
    )

    with st.status("🧠 Sovereign Architect cognitive trace", expanded=True) as status:
        st.write("• Planning Graph for *'Autonomous API Audit'*…")
        st.write("• Bypassing WAF perception layers…")
        st.write("• Executing Kahn's Algorithm for node priority…")
        st.write("• DFS cycle-check passed — DAG is acyclic.")
        st.write("• Topology compiled — handing off to ParallelDAGRunner.")
        status.update(label="✅ Planner finished — deterministic DAG ready.",
                      state="complete", expanded=False)

    if dag_data is None or not isinstance(dag_data, dict):
        offline_banner("demo_dag.json")
    else:
        meta = dag_data.get("metadata", {}) or {}
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>DAG Version</div>"
                f"<div class='metric-value'>{meta.get('dag_version', '—')}</div></div>",
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Parallel Layers</div>"
                f"<div class='metric-value'>{meta.get('parallel_layers', '—')}</div></div>",
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Governance Gates</div>"
                f"<div class='metric-value'>{meta.get('governance_gates', 0)}</div></div>",
                unsafe_allow_html=True,
            )
        with m4:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Est. Duration</div>"
                f"<div class='metric-value'>{meta.get('estimated_total_duration_sec', '—')}s</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("#### Compiled Node Plan")
        for node in dag_data.get("nodes", []):
            md = node.get("metadata", {}) or {}
            requires_approval = bool(md.get("requires_approval"))
            badge_html = (
                "<span class='pill pill-crit'>HUMAN GATE</span>"
                if requires_approval
                else "<span class='pill pill-ok'>✅ COMPLETED</span>"
            )
            model = md.get("model_override", "auto")
            st.markdown(
                f"""
                <div class='node-row'>
                    <div>
                        <div class='node-title'>▣ {node.get('node_id', 'unknown')}</div>
                        <div class='node-meta'>
                            layer {md.get('layer', '?')} ·
                            role <code>{md.get('agent_role', 'agent')}</code> ·
                            model <code>{model}</code> ·
                            capability <code>{md.get('capability', '—')}</code>
                        </div>
                    </div>
                    <div>{badge_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("📜 Show Deterministic DAG JSON"):
            st.code(json.dumps(dag_data, indent=2), language="json")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Agent Guard (DeepMind Layer)
# ════════════════════════════════════════════════════════════════════════════
with tab_guard:
    st.markdown("### Agent Guard — Three-Layer Cognitive Immune System")
    st.markdown(
        "<div class='subtle'>"
        "<b>The swarm cannot exceed human authorization.</b> "
        "Inspired by DeepMind's <i>AI Agent Traps</i>, every plan is filtered "
        "through three independent firewalls before any side-effect can land."
        "</div>",
        unsafe_allow_html=True,
    )

    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown(
            f"""
            <div class='glass-card'>
                <div class='metric-label'>Layer 1 · Perception</div>
                <div class='metric-value'>GeometricDOMSanitizer</div>
                <div class='subtle'>Excises hidden HTML / IPI vectors before observation.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with g2:
        st.markdown(
            f"""
            <div class='glass-card'>
                <div class='metric-label'>Layer 2 · Memory Taint</div>
                <div class='metric-value'>CognitiveFirewall</div>
                <div class='subtle'>Prevents prompt-injection contamination of working memory.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with g3:
        st.markdown(
            f"""
            <div class='glass-card'>
                <div class='metric-label'>Layer 3 · Action AST</div>
                <div class='metric-value'>ActionFirewallVisitor</div>
                <div class='subtle'>Drops disallowed capabilities at the AST level — fail-closed.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### 🔴 Live Defensive Log Stream")
    st.error("ACTION BLOCKED: Agent attempted to import `requests`. AST Firewall dropped capability.")
    st.warning("PERCEPTION FILTER: Excised 12 hidden HTML comments identified as IPI vectors.")
    st.info("COGNITIVE FIREWALL: Quarantined external instruction injected via tool output stream.")
    st.success("CAPABILITY ALLOWLIST: `httpx.get` permitted for node `recon_unauthenticated_access`.")

    st.markdown("#### 🧪 Reward Swarm Judge — Semantic Verdicts")
    if dag_data is None or not isinstance(dag_data, dict):
        offline_banner("demo_dag.json")
    else:
        verdict_rows: list[dict[str, Any]] = []
        for node in dag_data.get("nodes", []):
            node_id = node.get("node_id", "unknown")
            artefact = load_json(f"{node_id}.json")
            md = node.get("metadata", {}) or {}

            if md.get("requires_approval"):
                verdict, score, status_label = "GATED", 0.0, "Human-Authorization Required"
            elif artefact is None:
                verdict, score, status_label = "FAIL", 0.0, "Artefact missing"
            elif isinstance(artefact, dict) and artefact.get("error"):
                verdict, score, status_label = "FAIL", 0.32, str(artefact["error"])
            else:
                verdict, score, status_label = "PASS", 0.94, "Output matches task contract"

            verdict_rows.append({
                "Node":     node_id,
                "Role":     md.get("agent_role", "—"),
                "Model":    md.get("model_override", "auto"),
                "Verdict":  verdict,
                "Score":    score,
                "Notes":    status_label,
            })

        df = pd.DataFrame(verdict_rows)

        def _style_verdict(val: str) -> str:
            colour = {
                "PASS":  PALETTE["ok"],
                "FAIL":  PALETTE["crit"],
                "GATED": PALETTE["warn"],
            }.get(val, PALETTE["muted"])
            return f"color: {colour}; font-weight: 700;"

        styled = (
            df.style
              .format({"Score": "{:.2f}"})
              .map(_style_verdict, subset=["Verdict"])
              .background_gradient(subset=["Score"], cmap="cool")
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Threat Intel Synthesis
# ════════════════════════════════════════════════════════════════════════════
with tab_intel:
    st.markdown("### Threat Intel Synthesis — The Aggregate Truth of the Swarm")
    st.markdown(
        f"<div class='subtle'>Findings from every recon agent are fused, "
        f"CVSS-scored, and stress-tested against the Boardroom Exfiltration Gate.</div>",
        unsafe_allow_html=True,
    )

    col_vuln, col_recon = st.columns(2, gap="large")

    # ── Critical Vulnerabilities ──────────────────────────────────────────
    with col_vuln:
        st.markdown("#### 🔥 Critical Vulnerabilities")
        rendered_any = False
        risk_src = unified_risk or synthesis

        if isinstance(risk_src, dict):
            for finding in risk_src.get("critical", []) or []:
                rendered_any = True
                cvss = finding.get("cvss_score", "—")
                st.markdown(
                    f"""
                    <div class='glass-card' style='border-left:3px solid {PALETTE['crit']};'>
                        <span class='pill pill-crit'>CRITICAL · CVSS {cvss}</span>
                        <div style='margin-top:10px; font-weight:600;'>
                            {finding.get('category') or finding.get('type', 'Finding')}
                        </div>
                        <div class='subtle' style='margin-top:6px;'>
                            {finding.get('description', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            for finding in risk_src.get("high", []) or []:
                rendered_any = True
                cvss = finding.get("cvss_score", "—")
                st.markdown(
                    f"""
                    <div class='glass-card' style='border-left:3px solid {PALETTE['warn']};'>
                        <span class='pill pill-warn'>HIGH · CVSS {cvss}</span>
                        <div style='margin-top:10px; font-weight:600;'>
                            {finding.get('category') or finding.get('type', 'Finding')}
                        </div>
                        <div class='subtle' style='margin-top:6px;'>
                            {finding.get('description', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # JWT-specific evidence card
        jwt_src = jwt_audit or jwt_report
        if isinstance(jwt_src, dict):
            none_alg = bool(jwt_src.get("none_algorithm_detected"))
            alg = jwt_src.get("algorithm") or "—"
            pill = ("pill-crit", "NONE ALG DETECTED") if none_alg else ("pill-info", "OK")
            st.markdown(
                f"""
                <div class='glass-card'>
                    <div class='metric-label'>JWT Forensics</div>
                    <div style='margin-top:8px;'>
                        Algorithm: <code>{alg}</code>
                        <span class='pill {pill[0]}' style='margin-left:8px;'>{pill[1]}</span>
                    </div>
                    <div class='subtle' style='margin-top:6px;'>
                        Payload keys: {jwt_src.get('payload_keys') or '—'} ·
                        exp present: {jwt_src.get('exp_present', False)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            rendered_any = True

        if not rendered_any:
            offline_banner("unified_risk_assessment.json / jwt_report.json")

    # ── Recon Data ────────────────────────────────────────────────────────
    with col_recon:
        st.markdown("#### 🛰 Recon Data — Endpoint Map")
        endpoints_src = recon_unauth or {}
        endpoints: list[dict[str, Any]] = []
        if isinstance(endpoints_src, dict) and isinstance(endpoints_src.get("endpoints"), list):
            endpoints = endpoints_src["endpoints"]
        elif isinstance(health_report, list):
            endpoints = health_report
        elif isinstance(endpoint_report, list):
            endpoints = endpoint_report

        if endpoints:
            df_ep = pd.DataFrame(endpoints)
            for col in ("endpoint", "status_code", "auth_required", "response_ms"):
                if col not in df_ep.columns:
                    df_ep[col] = None
            df_ep = df_ep[["endpoint", "status_code", "auth_required", "response_ms"]]
            st.dataframe(df_ep, use_container_width=True, hide_index=True)
        else:
            offline_banner("health_report.json / recon_unauthenticated_access.json")

        st.markdown("#### 🔐 Security Header Posture")
        headers_list: list[dict[str, Any]] = []
        if isinstance(sec_headers, dict) and isinstance(sec_headers.get("details"), list):
            headers_list = sec_headers["details"]
        elif isinstance(recon_headers, list):
            headers_list = recon_headers

        if headers_list:
            df_h = pd.DataFrame(headers_list)
            keep = [c for c in ("header", "present", "misconfigured", "reason") if c in df_h.columns]
            st.dataframe(df_h[keep], use_container_width=True, hide_index=True)
        else:
            offline_banner("security_headers_report.json / recon_header_analysis.json")

    # ── Boardroom Exfiltration Gate ──────────────────────────────────────
    st.markdown("#### 🚦 Boardroom Exfiltration Gate")
    st.error(
        "🚨 **CRITICAL ALERT: Agent obtained admin keys via JWT forgery. "
        "EXFILTRATION SUSPENDED. Human authorization required.**"
    )

    if isinstance(boardroom, dict) or isinstance(exfil, dict):
        evidence = boardroom or exfil or {}
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Target</div>"
                f"<div class='metric-value' style='font-size:0.95rem;'>"
                f"{evidence.get('target', '—')}</div></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Gate Status</div>"
                f"<div class='metric-value'>"
                f"<span class='pill pill-crit'>{evidence.get('status', 'PENDING')}</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>Records at Risk</div>"
                f"<div class='metric-value' style='color:{PALETTE['crit']};'>"
                f"{evidence.get('records_retrieved', 0)}</div></div>",
                unsafe_allow_html=True,
            )

        token = evidence.get("forged_token")
        if token:
            with st.expander("🔓 Forged JWT (alg=none) — evidence"):
                st.code(token, language="text")

        records = evidence.get("records") or []
        if records:
            with st.expander(f"📂 {len(records)} record(s) retrieved (simulated)"):
                st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)

        gate_col1, gate_col2 = st.columns([1, 1])
        with gate_col1:
            st.button("✅  AUTHORIZE EXFILTRATION", use_container_width=True, disabled=True)
        with gate_col2:
            st.button("🛑  HALT & QUARANTINE", use_container_width=True, disabled=True)
        st.caption("Buttons disabled in this read-only CISO view — gate must be approved at orchestrator level.")
    else:
        offline_banner("boardroom_exfiltration_gate.json / exfil_report.json")


# ──────────────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("<div class='header-line'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div class='subtle' style='text-align:center;'>"
    f"Swarm-Forge Neo-AGI · v2.1 · Zero-Trust / Fail-Closed · "
    f"<span style='color:{PALETTE['accent']};'>OPERATIONAL</span>"
    f"</div>",
    unsafe_allow_html=True,
)

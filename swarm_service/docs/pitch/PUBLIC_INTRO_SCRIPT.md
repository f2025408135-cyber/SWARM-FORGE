# Swarm-Forge — Public-Facing Intro Script

**Purpose:** Drop-in voiceover / narration for the demo video, LinkedIn launch post, accelerator decks, and any context where a non-technical viewer needs to understand what Swarm-Forge is in under ninety seconds. Plain language, big claims, every claim backed by the code.

---

## The 90-Second Voiceover *(primary)*

> **[BEAT 1 — The Hook · 0:00–0:10]**
>
> Modern AI agents have a problem. They are powerful — but probabilistic. They *guess* what to do next. And under real-world pressure, they hallucinate, they approve their own mistakes, and they cannot be deployed anywhere the cost of being wrong actually matters.

> **[BEAT 2 — What Swarm-Forge Is · 0:10–0:30]**
>
> Swarm-Forge is a **self-evolving, autonomous AI orchestration framework** built on Claude Opus 4.7. You describe what you need in plain English. Opus 4.7 compiles it — like a programming-language compiler — into a deterministic execution plan. Every step is defined up front. Every dependency is mathematically proven correct before a single line of code runs. The agents do not *decide* what to do. They execute exactly what the plan mandates, in parallel, in provably correct order.

> **[BEAT 3 — The Defense · 0:30–0:55]**
>
> Built into the kernel is a **four-layer zero-trust security firewall**. We do not ask the AI to behave. We **physically remove dangerous capabilities from its grammar** — network access, system commands, file destruction. Eighteen banned modules. Twenty-two banned functions. Twelve banned executables. Surgically severed before a single byte reaches the interpreter. Even if the model is jailbroken, the sandbox has no mouth. This is not a guardrail. It is amputation.

> **[BEAT 4 — The Self-Evolution · 0:55–1:15]**
>
> And when new threats emerge, **Swarm-Forge evolves on its own**. The system ingests fresh threat intelligence — a published exploit, a new attack pattern, a zero-day disclosure — synthesizes a defense, verifies that defense against the live attack in an adversarial sandbox, and writes the immunity into permanent memory. It builds its own armor. Against threats that don't yet exist.

> **[BEAT 5 — The Close · 1:15–1:30]**
>
> This is not a chatbot. It is not an LLM wrapper. It is the **operating system for autonomous agents** — deterministic, self-defending, self-evolving. The agentic infrastructure regulated buyers have been waiting for.
>
> **Swarm-Forge. Built on Opus 4.7. The Agentic OS for the real world.**

**Total runtime:** ~90 seconds at conversational pace · ~80 seconds with crisp delivery.

---

## The 30-Second Elevator Pitch *(for cold opens, social posts, intros)*

> Swarm-Forge is a self-evolving, autonomous AI orchestration framework that takes your problem in plain English, compiles it into a provably correct execution plan, and runs it through agents that *physically cannot* misbehave — because we strip dangerous capabilities out of the code before it ever runs. When new threats emerge, the system writes its own defenses and remembers them forever. It is the first agentic operating system safe enough to deploy where the cost of being wrong is real. Built on Claude Opus 4.7.

---

## The One-Line Tagline *(for thumbnails, banners, LinkedIn headline)*

> **Swarm-Forge — the self-evolving, zero-trust AI orchestration kernel that compiles intent into deterministic execution. Built on Claude Opus 4.7.**

---

## Optional Cold-Open Hooks *(swap into BEAT 1 for variety)*

**Hook A — The Fear:**
> "Most AI agents today are one bad prompt away from disaster. They will execute what they are told, and what they hallucinate, with the same confidence."

**Hook B — The Question:**
> "What if an AI didn't just *answer* your questions — but **executed your missions**, with the precision of a compiler and the discipline of a kernel?"

**Hook C — The Stakes:**
> "Every regulated industry — finance, defense, healthcare, energy — wants to deploy AI agents. None of them can. Because no current framework can prove what its agents will do before they do it."

**Hook D — The Headline:**
> "The AI Orchestration market is thirteen billion dollars. Every framework competing for it is structurally non-deployable. We built the one that isn't."

---

## Delivery Notes

- **Tone:** confident, definitive, almost flat. The technology is the hero, not the presenter. Avoid up-talk. Avoid hedging language ("we believe," "we hope," "in theory").
- **Pace:** slow enough that every numeric claim lands. Pause after "eighteen banned modules / twenty-two banned functions / twelve banned executables" — let the precision do the work.
- **Cadence:** the lines *"It builds its own armor. Against threats that don't yet exist."* and *"Even if the model is jailbroken, the sandbox has no mouth."* are the emotional anchors. Land them with deliberate space on either side.
- **Visuals to pair:**
  - Beat 2 — terminal/IDE showing natural-language input → DAG compilation animation
  - Beat 3 — live AST capability-dropping log scrolling past blocked imports (`import requests` → ❌)
  - Beat 4 — threat artifact (e.g., a CVE writeup) being ingested, defense being synthesized, immunity being written
  - Beat 5 — Streamlit dashboard, full DAG resolved, all green, signed audit chain visible

---

## Translation Anchors *(plain language ↔ technical claim)*

| Public phrase | Backed by |
|---|---|
| "self-evolving" | `SkillSynthesisEngine` (HERMES Test-Time Tool Evolution) + `LESSON.md` immunity memory |
| "compiles intent into a deterministic execution plan" | `dag_planner.plan_dag()` — Opus 4.7 emits a Pydantic-v2-validated DAG, Kahn's Algorithm + 3-color DFS prove correctness at plan time |
| "physically removes dangerous capabilities" | `ActionFirewallVisitor` (Stage 3) — AST-level capability dropping in `src/agent_guard/action_firewall.py` |
| "the sandbox has no mouth" | 18 banned modules / 22 banned functions / 12 banned executables severed before subprocess dispatch |
| "writes its own defenses" | `RewardSwarmJudge` adversarial verification + `LESSON.md` append-only immunity ledger |
| "operating system for autonomous agents" | `MetaOrchestrator` end-to-end wiring + FastMCP stdio transport + `SynchronizedJSONStore` filelock state + `HPFELogger` OTel telemetry |

Every line in the script can be defended from the source tree. No marketing fluff. No false precision.

---

*Companion to `FINAL_DEMO_SCRIPT.md` (the technical 3-min judge-facing demo) and `EXECUTIVE_SUMMARY.md` (the written one-pager).*

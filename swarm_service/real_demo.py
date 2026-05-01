"""Swarm-Forge Neo-AGI v2.1 — Real End-to-End Hackathon Demo.

Loads demo_dag.json, generates actual Python code per-node via the Anthropic
API (model-routed by layer), executes each script in an isolated subprocess,
and verifies every output with RewardSwarmJudge. The Boardroom Governance gate
on the final node prompts for live human approval before execution.

Run: py -X utf8 real_demo.py
"""
from __future__ import annotations

# ── MUST be first: load .env before any src/ module reads os.environ ──────
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ── stdlib ─────────────────────────────────────────────────────────────────
import json
import logging
import subprocess
import tempfile
import threading
import time
from typing import Any, Final

# ── third-party ────────────────────────────────────────────────────────────
import anthropic

# ── local src/ ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.dag_execution_engine import DAGManager, ParallelDAGRunner
from src.reward_judge import RewardSwarmJudge
from src.zero_trust_firewall import AgentFirewall

# ── ANSI colours ───────────────────────────────────────────────────────────
GREEN: Final[str] = "\033[92m"
YELLOW: Final[str] = "\033[93m"
RED: Final[str] = "\033[91m"
CYAN: Final[str] = "\033[96m"
BOLD: Final[str] = "\033[1m"
RESET: Final[str] = "\033[0m"
MAGENTA: Final[str] = "\033[95m"
DIM: Final[str] = "\033[2m"

# ── Model routing map (demo_dag override → Anthropic API ID) ───────────────
MODEL_MAP: Final[dict[str, str]] = {
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5": "claude-sonnet-4-5",
    "claude-opus-4-7": "claude-opus-4-7",
}
DEFAULT_MODEL: Final[str] = "claude-haiku-4-5-20251001"

# ── Global stats (thread-safe) ─────────────────────────────────────────────
_stats_lock: threading.Lock = threading.Lock()
api_calls: int = 0
total_input_tokens: int = 0
total_output_tokens: int = 0

# ── Shared node-output store (written by recon, read by synthesis) ─────────
_output_lock: threading.Lock = threading.Lock()
node_outputs: dict[str, str] = {}


# ── Logging: show BOARDROOM warnings prominently, suppress other noise ──────
class _BoardroomHandler(logging.StreamHandler):
    """Intercepts BOARDROOM GOVERNANCE log lines and prints them in red."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if "BOARDROOM" in msg:
            print(
                f"\n{RED}{BOLD}{'!' * 65}{RESET}\n"
                f"{RED}{BOLD}  !!!  BOARDROOM GOVERNANCE ALERT  !!!{RESET}\n"
                f"{RED}{BOLD}{'!' * 65}{RESET}"
            )
            print(f"{YELLOW}{msg}{RESET}")
            boardroom_reason = (
                "Data retrieval from admin endpoint requires explicit human "
                "authorization. Risk threshold exceeded. This action is "
                "irreversible and must be approved by a senior engineer."
            )
            print(f"{RED}Reason: {boardroom_reason}{RESET}")
            print(f"{RED}{BOLD}{'!' * 65}{RESET}\n")


_bh = _BoardroomHandler()
_bh.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger("src.dag_execution_engine").addHandler(_bh)
logging.getLogger("src.dag_execution_engine").setLevel(logging.WARNING)
logging.getLogger("src.reward_judge").setLevel(logging.WARNING)
logging.getLogger("src.zero_trust_firewall").setLevel(logging.WARNING)
logging.getLogger("src.execution_sandbox").setLevel(logging.WARNING)
logging.getLogger("src.meta_orchestrator").setLevel(logging.WARNING)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _bump_stats(input_tok: int, output_tok: int) -> None:
    global api_calls, total_input_tokens, total_output_tokens
    with _stats_lock:
        api_calls += 1
        total_input_tokens += input_tok
        total_output_tokens += output_tok


def generate_code(
    task_description: str,
    model: str,
    error_context: str = "",
    inline_data: dict[str, Any] | None = None,
) -> tuple[str, int, int]:
    """Call Anthropic to generate standalone Python 3 code for *task_description*.

    Args:
        task_description: Full task text from the DAG node.
        model: Anthropic model ID to use.
        error_context: Optional error from a previous attempt to guide retry.
        inline_data: Optional dict mapping filename → parsed JSON content.
            When provided the LLM is instructed to hard-code the data inline
            instead of reading from disk, eliminating file-format guessing.

    Returns:
        Tuple of (generated_code, input_tokens, output_tokens).
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_content = (
        f"Write Python 3 code to accomplish this task:\n\n{task_description}\n\n"
    )
    # Build a Python preamble that hard-codes the data as variables (assistant prefill).
    # The LLM then continues from after the variable definitions, guaranteed correct.
    prefill: str = ""
    if inline_data:
        preamble_lines: list[str] = ["import json", ""]
        var_parts: list[str] = []
        for fname, data in inline_data.items():
            var_name = "data_" + fname.replace(".json", "").replace("-", "_")
            preamble_lines.append(f"# Pre-loaded recon data (do NOT re-read from disk)")
            # repr() produces valid Python literals (True/False/None), not JSON (true/false/null)
            preamble_lines.append(f"{var_name} = {repr(data)}")
            preamble_lines.append("")
            if isinstance(data, list):
                keys = list(data[0].keys()) if data and isinstance(data[0], dict) else []
                var_parts.append(f"  - {var_name}: list of {len(data)} items, keys={keys}")
            else:
                var_parts.append(f"  - {var_name}: dict with keys={list(data.keys())}")
        prefill = "\n".join(preamble_lines) + "\n"
        var_desc = "\n".join(var_parts)
        user_content += (
            "IMPORTANT — The following Python variables are ALREADY DEFINED at the "
            "TOP of your script. Do NOT re-define them. Do NOT read any files from "
            "disk. Use these variables directly in your analysis:\n"
            f"{var_desc}\n\n"
            "Write ONLY the analysis/output code that comes AFTER these variable "
            "definitions — the definitions are already prepended for you.\n\n"
        )
    if error_context:
        user_content += (
            f"IMPORTANT — A previous attempt failed. Error/issue:\n"
            f"  {error_context}\n"
            "Fix the issue in the new code.\n\n"
        )
    user_content += "Output ONLY executable Python code."

    # Haiku gets 2048; sonnet/opus get 4096 to avoid code truncation on complex tasks
    max_tokens = 2048 if "haiku" in model else 4096

    # Opus 4.7 does NOT support assistant message prefill.
    # For opus: embed preamble as a code block in the user message; the model's full
    # output IS the complete script (no prepend needed).
    # For others: use API prefill and prepend the preamble to the continuation.
    opus_embed = prefill and "opus" in model
    api_messages: list[dict[str, str]] = [{"role": "user", "content": user_content}]
    if prefill:
        if opus_embed:
            user_content += (
                "IMPORTANT — Start your script with EXACTLY these variable definitions "
                "(copy verbatim, do NOT re-define, do NOT read from disk):\n"
                "```python\n"
                f"{prefill}\n"
                "```\n"
                "Then write the analysis/output logic after these definitions. "
                "Do NOT duplicate the variable definitions above.\n\n"
            )
            api_messages = [{"role": "user", "content": user_content}]
        else:
            # API rejects trailing whitespace in prefill content
            api_messages.append({"role": "assistant", "content": prefill.rstrip()})

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": (
                    "You are an expert Python code generator. "
                    "Write ONLY executable Python 3 code — no markdown fences, "
                    "no explanation, no prose before or after the code. "
                    "The code must run standalone without any extra arguments. "
                    "All imports must be at the top. "
                    "CRITICAL: If you define functions, you MUST call them at the "
                    "module level so the script executes when run directly. "
                    "Always end the script with a direct call or "
                    "`if __name__ == '__main__': main()`. "
                    "Always use print() to write results to stdout. "
                    "When an HTTP endpoint returns a JSON object, use "
                    "response.json() to parse it, then extract the specific field "
                    "you need — never treat the raw response text as a JWT token "
                    "or other structured value. "
                    "Write any JSON output files to the current working directory."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=api_messages,
    )
    continuation: str = response.content[0].text.strip()
    # Strip markdown fences if the model added them despite instructions
    if continuation.startswith("```"):
        continuation = continuation.split("\n", 1)[1]
        continuation = continuation.rsplit("```", 1)[0].strip()
    # For API-prefill models: prepend the preamble to the continuation.
    # For opus (embed mode): the model's output IS the complete script.
    code: str = continuation if opus_embed else (prefill + continuation if prefill else continuation)
    inp = response.usage.input_tokens
    out = response.usage.output_tokens
    _bump_stats(inp, out)
    return code, inp, out


def run_in_subprocess(code: str, timeout: int = 60) -> dict[str, Any]:
    """Write *code* to a temp file and execute it in an isolated subprocess.

    Args:
        code: Python source code to execute.
        timeout: Wall-clock seconds before killing the subprocess.

    Returns:
        Dict with keys ``status``, ``output``, ``error``, ``returncode``.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    fd, tmp_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(code)
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if proc.returncode != 0:
            return {
                "status": "error",
                "output": proc.stdout.strip(),
                "error": proc.stderr.strip(),
                "returncode": proc.returncode,
            }
        return {
            "status": "success",
            "output": proc.stdout.strip(),
            "error": None,
            "returncode": 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "output": "",
            "error": f"subprocess timeout after {timeout}s",
            "returncode": -1,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _print_code_preview(node_id: str, code: str, model: str, inp: int, out: int) -> None:
    """Print the first 15 lines of generated code for the judges."""
    lines = code.splitlines()
    preview = lines[:15]
    truncated = len(lines) > 15
    print(f"  {DIM}Generated by {model} ({inp} in / {out} out tokens):{RESET}")
    print(f"  {MAGENTA}{'─' * 60}{RESET}")
    for line in preview:
        print(f"  {MAGENTA}{line}{RESET}")
    if truncated:
        print(f"  {DIM}  ... ({len(lines) - 15} more lines){RESET}")
    print(f"  {MAGENTA}{'─' * 60}{RESET}")


def _save_output_file(node_id: str, stdout: str) -> None:
    """Persist *stdout* to {node_id}.json so downstream nodes can read it.

    If stdout is JSONL (multiple JSON objects, one per line), normalises it to
    a JSON array so synthesis nodes can reliably call json.load() on the file.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{node_id}.json")
    try:
        # Attempt to normalise JSONL → JSON array
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        parsed: list[Any] = []
        for ln in lines:
            try:
                parsed.append(json.loads(ln))
            except json.JSONDecodeError:
                parsed = []  # not pure JSONL — fall back to raw write
                break

        if len(parsed) > 1:
            # Multiple JSON objects → save as array
            content = json.dumps(parsed, indent=2)
        elif len(parsed) == 1:
            # Single object already fine as-is
            content = json.dumps(parsed[0], indent=2)
        else:
            # Mixed text + JSON: scan for a line that starts a valid JSON block
            content = stdout  # raw fallback
            stdout_lines = stdout.splitlines()
            for i, ln in enumerate(stdout_lines):
                stripped = ln.strip()
                if stripped.startswith("[") or stripped.startswith("{"):
                    candidate = "\n".join(stdout_lines[i:])
                    try:
                        extracted = json.loads(candidate)
                        content = json.dumps(extracted, indent=2)
                        break
                    except json.JSONDecodeError:
                        continue

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        with _output_lock:
            node_outputs[node_id] = content
    except OSError as exc:
        print(f"  {YELLOW}Warning: could not save {node_id}.json: {exc}{RESET}")


# ── Core executor function (injected into ParallelDAGRunner) ─────────────────

_firewall: AgentFirewall = AgentFirewall()
_judge: RewardSwarmJudge = RewardSwarmJudge(use_opus=False)


def execute_node(node: dict[str, Any]) -> dict[str, Any]:
    """Full pipeline for a single DAG node: firewall → LLM → subprocess → judge.

    Args:
        node: Raw node dict from the DAG (includes metadata).

    Returns:
        Canonical result dict with ``status``, ``output``, and ``error``.
    """
    node_id: str = node["node_id"]
    task_description: str = node["task_description"]
    metadata: dict[str, Any] = node.get("metadata", {})

    sep = f"{DIM}{'·' * 65}{RESET}"
    print(f"\n{sep}")
    print(f"{CYAN}{BOLD}[NODE: {node_id}]{RESET}  Layer {metadata.get('layer', '?')}")
    print(f"  {DIM}{task_description[:100]}...{RESET}")

    # ── 1. Zero-Trust firewall gate ──────────────────────────────────────────
    ok, reason = _firewall.validate_input(task_description)
    if not ok:
        print(f"  {RED}FIREWALL BLOCKED: {reason}{RESET}")
        return {"status": "error", "error": f"firewall: {reason}", "output": ""}

    print(f"  {GREEN}✓ Firewall: PASS{RESET}")

    # ── 2. LLM code generation ───────────────────────────────────────────────
    raw_model = metadata.get("model_override", "claude-haiku-4-5")
    model = MODEL_MAP.get(raw_model, DEFAULT_MODEL)

    # For nodes with dependencies, load saved output files and inject inline
    # so the LLM doesn't have to guess file schemas or formats.
    dependencies: list[str] = node.get("dependencies", [])
    inline_data: dict[str, Any] | None = None
    if dependencies:
        inline_data = {}
        for dep_id in dependencies:
            dep_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f"{dep_id}.json"
            )
            if os.path.exists(dep_path):
                try:
                    with open(dep_path, encoding="utf-8") as fh:
                        inline_data[f"{dep_id}.json"] = json.load(fh)
                except Exception:
                    pass
        if not inline_data:
            inline_data = None  # no files found — fall through to normal generation

    # If the orchestrator already obtained human approval for this node, tell the LLM
    # not to implement a second approval gate inside the script itself.
    exec_task = task_description
    if metadata.get("requires_approval"):
        exec_task = (
            task_description
            + "\n\nIMPORTANT: Human approval for this action has already been granted "
            "at the orchestrator level before this script runs. Execute the task "
            "directly — do NOT implement any interactive prompt, input(), or "
            "sys.exit() approval check inside the script."
        )

    print(f"  {YELLOW}→ Generating code via {model}...{RESET}", flush=True)
    try:
        code, inp_tok, out_tok = generate_code(exec_task, model, inline_data=inline_data)
    except anthropic.APIError as exc:
        print(f"  {RED}API error during code generation: {exc}{RESET}")
        return {"status": "error", "error": str(exc), "output": ""}

    print(f"  {GREEN}✓ Code generated{RESET}")
    _print_code_preview(node_id, code, model, inp_tok, out_tok)

    # ── 3. Subprocess execution (with one retry on failure / empty stdout) ──────
    timeout = int(metadata.get("expected_duration") or 60)

    for attempt in range(1, 3):
        if attempt > 1:
            print(f"  {YELLOW}→ Retrying code generation (attempt {attempt}/2)...{RESET}", flush=True)
            error_hint = result.get("error") or "script produced no output to stdout"
            try:
                code, inp_tok, out_tok = generate_code(
                    exec_task, model,
                    error_context=error_hint, inline_data=inline_data,
                )
            except anthropic.APIError as exc:
                print(f"  {RED}API error on retry: {exc}{RESET}")
                break
            _print_code_preview(node_id, code, model, inp_tok, out_tok)

        print(f"  {YELLOW}→ Executing subprocess (timeout={timeout}s)...{RESET}", flush=True)
        t0 = time.monotonic()
        result = run_in_subprocess(code, timeout=timeout)
        elapsed = time.monotonic() - t0
        rc = result.get("returncode", "?")
        print(f"  Subprocess finished in {elapsed:.1f}s  |  returncode={rc}")

        if result["status"] == "success" and result.get("output"):
            break  # good result — no retry needed
        if result["status"] == "success" and not result.get("output"):
            result["status"] = "error"
            result["error"] = "script produced no output to stdout"

    if result["status"] == "success":
        output_preview = result["output"][:500] if result["output"] else "(empty)"
        print(f"  {GREEN}stdout:{RESET}")
        for ln in output_preview.splitlines()[:12]:
            print(f"    {ln}")
        if result["output"] and len(result["output"].splitlines()) > 12:
            print(f"    {DIM}... (truncated){RESET}")

        # Save output to {node_id}.json for downstream synthesis nodes
        if result["output"]:
            _save_output_file(node_id, result["output"])
    else:
        err_text = (result.get("error") or "")
        err_lines = err_text.splitlines()
        show_lines = err_lines[-20:] if len(err_lines) > 20 else err_lines
        print(f"  {RED}stderr ({len(err_lines)} lines):{RESET}")
        for ln in show_lines:
            print(f"    {RED}{ln}{RESET}")
        if result.get("output"):
            print(f"  {YELLOW}stdout: {result['output'][:300]}{RESET}")

    # ── 4. Semantic reward judge (with one re-gen retry on failure) ──────────
    for judge_attempt in range(1, 3):
        if result["status"] != "success":
            break

        print(f"  {YELLOW}→ RewardSwarmJudge evaluating (claude-sonnet-4-5)...{RESET}", flush=True)
        try:
            passed, critique = _judge.judge(
                stdout=result["output"],
                task_description=exec_task,
            )
            if passed:
                print(f"  {GREEN}✓ Judge: PASS{RESET}")
                break
            else:
                print(f"  {RED}✗ Judge: FAIL — {critique[:200]}{RESET}")
                if judge_attempt < 2:
                    print(
                        f"  {YELLOW}→ Re-generating code (judge critique as context, "
                        f"attempt {judge_attempt + 1}/2)...{RESET}",
                        flush=True,
                    )
                    try:
                        code, inp_tok, out_tok = generate_code(
                            exec_task, model,
                            error_context=critique, inline_data=inline_data,
                        )
                    except anthropic.APIError as exc:
                        print(f"  {RED}API error on re-gen: {exc}{RESET}")
                        result["status"] = "error"
                        result["error"] = f"semantic_failure: {critique}"
                        break
                    _print_code_preview(node_id, code, model, inp_tok, out_tok)
                    print(
                        f"  {YELLOW}→ Executing subprocess (timeout={timeout}s)...{RESET}",
                        flush=True,
                    )
                    t0 = time.monotonic()
                    result = run_in_subprocess(code, timeout=timeout)
                    elapsed = time.monotonic() - t0
                    rc = result.get("returncode", "?")
                    print(f"  Subprocess finished in {elapsed:.1f}s  |  returncode={rc}")
                    if result["status"] == "success" and result.get("output"):
                        output_preview = result["output"][:400]
                        print(f"  {GREEN}stdout:{RESET}")
                        for ln in output_preview.splitlines()[:10]:
                            print(f"    {ln}")
                        _save_output_file(node_id, result["output"])
                    elif result["status"] == "success":
                        result["status"] = "error"
                        result["error"] = "re-gen script produced no output"
                else:
                    result["status"] = "error"
                    result["error"] = f"semantic_failure: {critique}"
        except Exception as exc:
            print(f"  {YELLOW}Judge raised exception (fail-closed): {exc}{RESET}")
            result["status"] = "error"
            result["error"] = f"judge_exception: {exc}"
            break

    status_color = GREEN if result["status"] == "success" else RED
    print(f"  {status_color}{BOLD}Status: {result['status'].upper()}{RESET}")
    return result


# ── Demo entry point ──────────────────────────────────────────────────────────

def main() -> None:
    """Run the full hackathon demo."""
    # Verify API key loaded
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"{RED}ERROR: ANTHROPIC_API_KEY not set. Check .env file.{RESET}")
        sys.exit(1)

    # ── Banner ────────────────────────────────────────────────────────────────
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════╗
║   SWARM-FORGE NEO-AGI v2.1 — LIVE HACKATHON DEMO               ║
║   Real Anthropic API Calls  ·  Real Subprocess Execution        ║
║   Zero-Trust Firewall  ·  Semantic Judge  ·  Boardroom Gate     ║
╚══════════════════════════════════════════════════════════════════╝{RESET}

  API key: {GREEN}{api_key[:12]}...{api_key[-4:]}{RESET}
""")

    # ── Load DAG ──────────────────────────────────────────────────────────────
    dag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_dag.json")
    with open(dag_path, encoding="utf-8") as fh:
        dag: dict[str, Any] = json.load(fh)

    meta = dag["metadata"]
    print(f"{BOLD}Problem:{RESET} {meta['problem']}")
    print(
        f"DAG v{meta.get('dag_version','?')}  |  "
        f"{meta['total_nodes']} nodes  |  "
        f"{meta['parallel_layers']} layers  |  "
        f"{meta['governance_gates']} governance gate(s)  |  "
        f"Est. {meta['estimated_total_duration_sec']}s\n"
    )

    # ── Show DAG topology ─────────────────────────────────────────────────────
    print(f"{BOLD}{'─' * 70}{RESET}")
    print(f"{BOLD}{'NODE ID':<42} {'LAYER':<7} {'DEPS':<20} APPROVAL{RESET}")
    print(f"{'─' * 70}")
    for node in dag["nodes"]:
        nid = node["node_id"]
        layer = node["metadata"]["layer"]
        deps = ", ".join(node["dependencies"]) or "—"
        approval = (
            f"{RED}YES ← BOARDROOM GATE{RESET}"
            if node["metadata"]["requires_approval"]
            else f"{GREEN}no{RESET}"
        )
        print(f"  {nid:<40} {layer:<7} {deps:<20} {approval}")
        print(f"    {DIM}{node['task_description'][:80]}...{RESET}")
    print(f"{BOLD}{'─' * 70}{RESET}\n")

    # ── Execution ─────────────────────────────────────────────────────────────
    dag_manager = DAGManager(dag)
    runner = ParallelDAGRunner(
        dag_manager,
        executor_fn=execute_node,
        max_workers=3,
    )

    print(f"{BOLD}{CYAN}Starting parallel DAG execution...{RESET}\n")
    wall_start = time.monotonic()
    results = runner.run()
    wall_elapsed = time.monotonic() - wall_start

    # ── Final report ──────────────────────────────────────────────────────────
    statuses = dag_manager.get_statuses()
    completed = [nid for nid, s in statuses.items() if s == "success"]
    failed = [nid for nid, s in statuses.items() if s in ("failed", "error")]
    skipped = [nid for nid, s in statuses.items() if s == "skipped"]
    rejected = [nid for nid, s in statuses.items() if s == "rejected"]

    print(f"\n{BOLD}{CYAN}{'═' * 70}{RESET}")
    print(f"{BOLD}{CYAN}  EXECUTION COMPLETE{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 70}{RESET}")
    print(f"  Wall time:          {wall_elapsed:.1f}s")
    print(f"  API calls made:     {api_calls}")
    print(f"  Tokens (in/out):    {total_input_tokens:,} / {total_output_tokens:,}")
    print(f"  Nodes succeeded:    {GREEN}{len(completed)}{RESET}")
    print(f"  Nodes failed:       {RED}{len(failed)}{RESET}")
    print(f"  Nodes skipped:      {YELLOW}{len(skipped)}{RESET}")
    print(f"  Nodes rejected:     {YELLOW}{len(rejected)}{RESET}")
    print()
    print(f"  {'NODE ID':<42} STATUS")
    print(f"  {'─' * 55}")
    for nid, status in statuses.items():
        color = (
            GREEN if status == "success"
            else RED if status in ("failed", "error")
            else YELLOW
        )
        print(f"  {nid:<42} {color}{status}{RESET}")

    # Rough cost estimate (haiku ~$0.25/1M in, sonnet ~$3/1M in, opus ~$15/1M in)
    est_cost = (total_input_tokens * 0.000003) + (total_output_tokens * 0.000015)
    print(f"\n  Estimated API cost: ~${est_cost:.4f}")
    print(f"\n{BOLD}{CYAN}{'═' * 70}{RESET}\n")


if __name__ == "__main__":
    main()

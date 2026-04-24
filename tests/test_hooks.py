"""Tests for Claude Code CLI hooks — pre_tool_validation, post_tool_ast_flush, post_bash_audit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_HOOKS_DIR: Path = Path(__file__).resolve().parent.parent / "scripts"


def _run_hook(script_name: str, stdin_data: dict) -> subprocess.CompletedProcess:
    """Run a hook script as a subprocess with JSON on stdin."""
    script = _HOOKS_DIR / script_name
    result = subprocess.run(
        ["python3", str(script)],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result


# ── pre_tool_validation.py ──────────────────────────────────────────────────


class TestPreToolValidation:
    """Verify the PreToolUse anti-sycophancy and destructive pattern blocker."""

    def test_blocks_rm_rf_root(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "rm -rf /" in output["reason"]

    def test_blocks_drop_table(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "DROP TABLE users;"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "DROP TABLE" in output["reason"]

    def test_blocks_delete_from(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "DELETE FROM sessions WHERE expired = 1"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_blocks_sudo_rm(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "sudo rm -rf /var/log"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_blocks_dev_sda(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "echo 'data' > /dev/sda"},
        })
        assert result.returncode == 2

    def test_blocks_format_c(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "format c: /q"},
        })
        assert result.returncode == 2

    def test_case_insensitive_blocking(self) -> None:
        # Uppercase "DROP TABLE" should still be caught
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "drop table users"},
        })
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert "DROP TABLE" in output["reason"]

        # Uppercase "DELETE FROM" should still be caught
        result2 = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "delete from sessions"},
        })
        assert result2.returncode == 2
        output2 = json.loads(result2.stdout)
        assert "DELETE FROM" in output2["reason"]

    def test_allows_normal_bash_command(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest tests/ -v"},
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"

    def test_allows_write_with_anti_sycophancy_context(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Write",
            "tool_input": {"path": "main.py", "content": "print('hello')"},
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"
        assert "ANTI-SYCOPHANCY OVERRIDE ACTIVE" in output["injected_context"]
        assert "hostile code reviewer" in output["injected_context"]

    def test_allows_edit_with_injected_context(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Edit",
            "tool_input": {"path": "agent.py", "old": "x", "new": "y"},
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"
        assert "injected_context" in output

    def test_allows_create_with_injected_context(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Create",
            "tool_input": {"path": "new_module.py"},
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"

    def test_allows_read_without_injected_context(self) -> None:
        result = _run_hook("pre_tool_validation.py", {
            "tool_name": "Read",
            "tool_input": {"path": "config.yaml"},
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"
        assert "injected_context" not in output

    def test_handles_invalid_json_gracefully(self) -> None:
        result = subprocess.run(
            ["python3", str(_HOOKS_DIR / "pre_tool_validation.py")],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should exit 0 (pass through) on invalid JSON
        assert result.returncode == 0

    def test_handles_empty_stdin(self) -> None:
        result = subprocess.run(
            ["python3", str(_HOOKS_DIR / "pre_tool_validation.py")],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# ── post_tool_ast_flush.py ─────────────────────────────────────────────────


class TestPostToolASTFlush:
    """Verify the PostToolUse AST flush hook."""

    def test_flush_valid_python_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "valid_module.py"
        test_file.write_text(
            "def hello():\n    return 'world'\n"
            "class Agent:\n    def run(self): pass\n"
        )

        result = _run_hook("post_tool_ast_flush.py", {
            "tool_input": {"path": str(test_file)},
        })
        assert result.returncode == 0

    def test_flush_syntax_error_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "broken.py"
        test_file.write_text("def broken(:\n    pass\n")

        result = _run_hook("post_tool_ast_flush.py", {
            "tool_input": {"path": str(test_file)},
        })
        # Should still exit 0 (hook should not crash the pipeline)
        assert result.returncode == 0
        # But should output a warning
        if result.stdout.strip():
            output = json.loads(result.stdout)
            assert "syntax error" in output.get("warning", "").lower() or "warning" in output

    def test_flush_non_python_file_ignored(self, tmp_path: Path) -> None:
        test_file = tmp_path / "config.yaml"
        test_file.write_text("key: value\n")

        result = _run_hook("post_tool_ast_flush.py", {
            "tool_input": {"path": str(test_file)},
        })
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_flush_empty_path(self) -> None:
        result = _run_hook("post_tool_ast_flush.py", {
            "tool_input": {"path": ""},
        })
        assert result.returncode == 0

    def test_flush_missing_path_key(self) -> None:
        result = _run_hook("post_tool_ast_flush.py", {
            "tool_input": {"other": "value"},
        })
        assert result.returncode == 0

    def test_flush_handles_invalid_json(self) -> None:
        result = subprocess.run(
            ["python3", str(_HOOKS_DIR / "post_tool_ast_flush.py")],
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# ── post_bash_audit.py ─────────────────────────────────────────────────────


class TestPostBashAudit:
    """Verify the PostToolUse bash audit hook for budget/rate-limit detection."""

    def test_detects_rate_limit(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "Error: rate limit exceeded. Try again later.",
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "rate limit" in output["warning"].lower()
        assert "exponential backoff" in output["action"].lower()

    def test_detects_quota_exceeded(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "ERROR: quota exceeded for this billing period",
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "quota exceeded" in output["warning"].lower()

    def test_detects_too_many_requests(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "HTTP 429 Too Many Requests",
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "429" in output["warning"].lower() or "too many requests" in output["warning"].lower()

    def test_detects_429_status_code(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "Response status: 429",
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "429" in output["warning"]

    def test_no_warning_clean_output(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "All tests passed. 42 assertions in 0.5s",
        })
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_case_insensitive_detection(self) -> None:
        result = _run_hook("post_bash_audit.py", {
            "tool_output": "WARNING: RATE LIMIT approaching threshold",
        })
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "rate limit" in output["warning"].lower()

    def test_handles_invalid_json(self) -> None:
        result = subprocess.run(
            ["python3", str(_HOOKS_DIR / "post_bash_audit.py")],
            input="garbage",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_handles_missing_tool_output(self) -> None:
        result = _run_hook("post_bash_audit.py", {"other_key": "value"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ── .claude/settings.json ───────────────────────────────────────────────────


class TestClaudeSettings:
    """Verify the Claude Code settings file structure."""

    def test_settings_file_exists(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        assert settings.exists()

    def test_settings_valid_json(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())

    def test_settings_has_hooks(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert "hooks" in data
        assert "PreToolUse" in data["hooks"]
        assert "PostToolUse" in data["hooks"]

    def test_settings_pretooluse_catches_all(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        pre = data["hooks"]["PreToolUse"]
        assert len(pre) == 1
        assert pre[0]["matcher"] == ".*"
        assert pre[0]["hooks"][0]["command"] == "python scripts/pre_tool_validation.py"

    def test_settings_posttooluse_has_ast_and_bash(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        post = data["hooks"]["PostToolUse"]
        matchers = [h["matcher"] for h in post]
        assert "Write|Edit|Create" in matchers
        assert "Bash" in matchers

    def test_settings_permissions(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert "permissions" in data
        assert "Bash" in data["permissions"]["allow"]
        assert "WebFetch" in data["permissions"]["deny"]

    def test_settings_env(self) -> None:
        settings = Path(__file__).resolve().parent.parent / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        assert data["env"]["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "35"
        assert data["env"]["CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY"] == "5"

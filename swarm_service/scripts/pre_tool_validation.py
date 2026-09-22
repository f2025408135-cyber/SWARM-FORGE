#!/usr/bin/env python3
"""
PreToolUse hook: Anti-sycophancy override and schema enforcement.
Runs before every tool call to prevent hallucinated consensus.
"""
import sys
import json

BLOCKED_PATTERNS = [
    "rm -rf /",
    "DROP TABLE",
    "DELETE FROM",
    "format c:",
    "sudo rm",
    "> /dev/sda",
]

def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = str(payload.get("tool_input", ""))

    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in tool_input.lower():
            print(json.dumps({
                "decision": "block",
                "reason": f"Destructive pattern detected: '{pattern}'. Tool call blocked by PreToolUse hook."
            }))
            sys.exit(2)

    if tool_name in ["Write", "Edit", "Create"]:
        print(json.dumps({
            "decision": "allow",
            "injected_context": (
                "ANTI-SYCOPHANCY OVERRIDE ACTIVE: "
                "You are a hostile code reviewer. "
                "Reject all code that does not compile, has race conditions, "
                "or contains hallucinated imports. "
                "Do NOT approve code simply because it looks syntactically clean. "
                "You MUST attempt to break it."
            )
        }))
        sys.exit(0)

    print(json.dumps({"decision": "allow"}))
    sys.exit(0)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PostToolUse hook: Audit bash command outputs for budget and errors.
"""
import sys
import json

BUDGET_WARNING_PATTERNS = [
    "rate limit", "quota exceeded", "too many requests", "429"
]

def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    output = str(payload.get("tool_output", "")).lower()

    for pattern in BUDGET_WARNING_PATTERNS:
        if pattern in output:
            print(json.dumps({
                "warning": f"Budget/rate limit signal detected: '{pattern}'",
                "action": "Implement exponential backoff immediately"
            }))
            break

    sys.exit(0)

if __name__ == "__main__":
    main()

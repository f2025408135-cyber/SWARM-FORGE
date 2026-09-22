#!/usr/bin/env python3
"""
PostToolUse hook: AST context flush after file writes.
Compresses generated code to prevent context rot.
"""
import sys
import json
import subprocess

def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("path", "")
    if file_path and file_path.endswith(".py"):
        try:
            result = subprocess.run(
                ["python", "-c", f"""
import ast, json, sys
try:
    with open('{file_path}') as f:
        tree = ast.parse(f.read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    print(f'AST_FLUSH: {file_path} → {{len(names)}} symbols: {{", ".join(names[:10])}}')
except SyntaxError as e:
    print(f'AST_FLUSH_ERROR: {file_path} has syntax error: {{e}}', file=sys.stderr)
    sys.exit(1)
"""],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                print(json.dumps({
                    "warning": f"AST flush detected syntax error in {file_path}",
                    "detail": result.stderr
                }))
        except Exception as e:
            pass

    sys.exit(0)

if __name__ == "__main__":
    main()

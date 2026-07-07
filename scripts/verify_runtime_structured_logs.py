#!/usr/bin/env python3
"""Verify runtime logs are structured JSONL only.

This script validates that runtime log output contains only valid JSON lines
with required fields. Non-JSON lines are failures because they indicate
unstructured logging that bypasses the scheduler JSON formatter.

Usage:
    python scripts/verify_runtime_structured_logs.py <file> [<file>...]
    python scripts/verify_runtime_structured_logs.py -           # read from stdin

Contract:
- Each non-empty line must be a valid JSON object
- Required fields: timestamp, component, severity, message
- Valid severities: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Empty lines are skipped

Exit codes:
    0 - PASS: all lines are valid structured JSON
    1 - FAIL: one or more lines are invalid
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = frozenset({"timestamp", "component", "severity", "message"})
VALID_SEVERITIES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def validate_line(line: str, line_no: int) -> list[str]:
    """Validate a single log line.

    Args:
        line: The line to validate
        line_no: Line number for error reporting

    Returns:
        List of error messages (empty if valid)
    """
    if not line.strip():
        return []

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return [f"line {line_no}: non-json runtime log line: {line[:160]!r}"]

    if not isinstance(payload, dict):
        return [f"line {line_no}: JSON log line is not an object"]

    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        return [f"line {line_no}: missing required fields: {sorted(missing)}"]

    severity = payload.get("severity", "")
    if severity not in VALID_SEVERITIES:
        return [f"line {line_no}: invalid severity: {severity!r}"]

    return []


def validate_file(path: Path) -> tuple[bool, list[str]]:
    """Validate all lines in a file.

    Args:
        path: Path to the log file, or Path("-") for stdin

    Returns:
        Tuple of (success, list of error messages)
    """
    errors: list[str] = []

    if str(path) == "-":
        lines = sys.stdin.read().splitlines()
    else:
        with path.open("r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    for line_no, line in enumerate(lines, start=1):
        errors.extend(validate_line(line, line_no))

    return len(errors) == 0, errors


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: verify_runtime_structured_logs.py <file> [<file>...]")
        print("       verify_runtime_structured_logs.py -  # read from stdin")
        return 1

    all_passed = True
    all_errors: list[str] = []

    for arg in sys.argv[1:]:
        if arg == "-":
            path = Path("-")
        else:
            path = Path(arg)
            if not path.exists():
                print(f"ERROR: file not found: {path}", file=sys.stderr)
                all_passed = False
                continue

        passed, errors = validate_file(path)

        if passed:
            print(f"PASS: {path}")
        else:
            print(f"FAIL: {path}")
            all_passed = False
            all_errors.extend(errors)

    for error in all_errors:
        print(error)

    if all_passed:
        print("\nVERIFICATION GATE: PASSED")
        return 0
    else:
        print(f"\nVERIFICATION GATE: FAILED ({len(all_errors)} error(s))")
        return 1


if __name__ == "__main__":
    sys.exit(main())

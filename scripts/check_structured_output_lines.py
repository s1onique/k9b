#!/usr/bin/env python3
"""Structured output line checker for health-loop stdout/stderr hygiene gate.

This script validates that output lines are valid JSON objects only.
Rejecting JSON arrays, JSON strings, malformed JSON, and all arbitrary plain text.

Usage:
    python scripts/check_structured_output_lines.py [file ...]
    cat output.txt | python scripts/check_structured_output_lines.py

Exit codes:
    0 - all lines accepted
    non-zero - any line rejected (with diagnostics)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def check_line(line: str, source_label: str, line_number: int) -> tuple[bool, str]:
    """Check if a single line is an accepted structured output line.

    Args:
        line: The raw line content (without trailing newline)
        source_label: Label for diagnostics (file path or '<stdin>')
        line_number: 1-based line number for diagnostics

    Returns:
        Tuple of (accepted: bool, diagnostics: str)
    """
    # Ignore blank lines
    stripped = line.strip()
    if not stripped:
        return True, ""

    try:
        parsed = json.loads(stripped)
        # Only accept JSON objects (dicts)
        if isinstance(parsed, dict):
            return True, ""
        else:
            if isinstance(parsed, list):
                rejected_type = "JSON array"
            elif isinstance(parsed, str):
                rejected_type = "JSON string"
            else:
                rejected_type = f"JSON {type(parsed).__name__}"
            return False, f"{source_label}:{line_number}: rejected {rejected_type}: {line[:100]}"
    except json.JSONDecodeError:
        return False, f"{source_label}:{line_number}: rejected non-JSON: {line[:100]}"


def check_file(file_path: Path) -> tuple[int, int, list[str]]:
    """Check a single file for structured output compliance.

    Args:
        file_path: Path to the file to check

    Returns:
        Tuple of (passed: int, failed: int, diagnostics: list[str])
    """
    diagnostics: list[str] = []
    passed = 0
    failed = 0

    with open(file_path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            # Remove trailing newline for checking
            line = line.rstrip("\n\r")
            accepted, diag = check_line(line, str(file_path), line_number)
            if accepted:
                passed += 1
            else:
                failed += 1
                if diag:
                    diagnostics.append(diag)

    return passed, failed, diagnostics


def check_stdin() -> tuple[int, int, list[str]]:
    """Check stdin for structured output compliance.

    Returns:
        Tuple of (passed: int, failed: int, diagnostics: list[str])
    """
    diagnostics: list[str] = []
    passed = 0
    failed = 0

    for line_number, line in enumerate(sys.stdin, start=1):
        # Remove trailing newline for checking
        line = line.rstrip("\n\r")
        accepted, diag = check_line(line, "<stdin>", line_number)
        if accepted:
            passed += 1
        else:
            failed += 1
            if diag:
                diagnostics.append(diag)

    return passed, failed, diagnostics


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]

    if not args:
        # Read from stdin
        passed, failed, diagnostics = check_stdin()
    else:
        # Check each provided file
        total_passed = 0
        total_failed = 0
        all_diagnostics: list[str] = []

        for file_path_str in args:
            file_path = Path(file_path_str)
            if not file_path.exists():
                print(f"ERROR: file not found: {file_path}", file=sys.stderr)
                return 2
            if not file_path.is_file():
                print(f"ERROR: not a file: {file_path}", file=sys.stderr)
                return 2

            passed, failed, diagnostics = check_file(file_path)
            total_passed += passed
            total_failed += failed
            all_diagnostics.extend(diagnostics)

        passed = total_passed
        failed = total_failed
        diagnostics = all_diagnostics

    # Print diagnostics
    for diag in diagnostics:
        print(diag, file=sys.stderr)

    if failed > 0:
        print(f"\nFAIL: {failed} line(s) rejected, {passed} line(s) accepted", file=sys.stderr)
        return 1
    else:
        print(f"PASS: {passed} line(s) accepted (all structured)", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""Test helpers for validating structured log output.

This module provides utilities for asserting that log output is properly
structured as JSON with the required fields for health-loop observability.
"""

from __future__ import annotations

import json
from typing import Any


def parse_log_lines(output: str) -> list[dict[str, Any]]:
    """Parse JSON log lines from stdout/stderr output.

    Args:
        output: Combined stdout/stderr output from a test

    Returns:
        List of parsed JSON log dicts, skipping non-JSON lines
    """
    lines = output.splitlines()
    parsed = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return parsed


def assert_all_log_lines_are_structured(
    captured_out: str,
    captured_err: str,
    required_fields: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Assert that all non-empty log lines are structured JSON records.

    This helper validates that health-loop / discovery output contains only
    valid JSON log records, preventing unstructured log leakage like raw
    "Forbidden" errors from kubectl.

    Args:
        captured_out: Captured stdout from capsys.readouterr()
        captured_err: Captured stderr from capsys.readouterr()
        required_fields: Optional tuple of required field names (default: standard set)

    Returns:
        List of parsed log records for further assertion

    Raises:
        AssertionError: If any non-empty line is not valid JSON or missing required fields
    """
    if required_fields is None:
        required_fields = ("timestamp", "component", "severity", "message", "event")

    valid_severities = {"DEBUG", "INFO", "WARNING", "ERROR"}

    combined_output = captured_out + "\n" + captured_err
    lines = [line.strip() for line in combined_output.splitlines() if line.strip()]

    parsed_records = []
    for line in lines:
        # Skip empty lines
        if not line:
            continue

        # Each non-empty line must be valid JSON
        if not (line.startswith("{") and line.endswith("}")):
            raise AssertionError(
                f"Found unstructured log line: {line[:100]!r}..."
                f"\nAll operational log lines must be valid JSON."
            )

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Found invalid JSON log line: {line[:100]!r}..."
                f"\nJSON parse error: {exc}"
            )

        # Validate required fields
        for field in required_fields:
            if field not in record:
                raise AssertionError(
                    f"Log record missing required field '{field}': {record}"
                )

        # Validate severity is one of the allowed values
        severity = record.get("severity", "")
        if severity not in valid_severities:
            raise AssertionError(
                f"Log record has invalid severity '{severity}': {record}"
                f"\nMust be one of: {valid_severities}"
            )

        parsed_records.append(record)

    return parsed_records


def assert_no_raw_forbidden_errors(captured_out: str, captured_err: str) -> None:
    """Assert that no raw 'Forbidden' Kubernetes errors appear in the output.

    Forbidden RBAC errors should be represented as structured WARNING events,
    never as raw subprocess text leaked to stdout/stderr.

    Args:
        captured_out: Captured stdout from capsys.readouterr()
        captured_err: Captured stderr from capsys.readouterr()

    Raises:
        AssertionError: If raw 'Forbidden' text found in non-JSON output
    """
    combined_output = captured_out + "\n" + captured_err

    for line in combined_output.splitlines():
        stripped = line.strip()
        # Skip empty lines
        if not stripped:
            continue

        # If line is not JSON, it must not contain "Forbidden"
        if not (stripped.startswith("{") and stripped.endswith("}")):
            if "Forbidden" in stripped or "forbidden" in stripped:
                raise AssertionError(
                    f"Found raw Forbidden error in unstructured output: {stripped[:200]!r}..."
                    f"\nForbidden errors must be structured as JSON WARNING events."
                )

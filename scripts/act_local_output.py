#!/usr/bin/env python3
"""ACT-Local output formatting.

Provides human-readable and JSON output formatters for ACT-local results.
"""

from __future__ import annotations

import json

from act_local_contract import ActLocalResult


def format_human_output(result: ActLocalResult) -> str:
    """Format human-readable output."""
    lines = []
    
    # Header
    overall_status = "PASS" if result.success else "FAIL"
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"ACT-local verification result: {overall_status}")
    lines.append("=" * 60)
    lines.append("")
    
    # Changed files
    lines.append("Changed files checked:")
    if result.changed_files:
        for f in result.changed_files:
            lines.append(f"  - {f}")
    else:
        lines.append("  (none detected)")
    lines.append("")
    
    # Checks run
    lines.append("Checks run:")
    for check in result.checks:
        status_icon = "✓" if check.status == "PASS" else "✗" if check.status == "FAIL" else "-"
        lines.append(f"  [{status_icon}] {check.name}")
        lines.append(f"      command: {check.command}")
        lines.append(f"      duration: {check.duration_ms}ms")
        lines.append(f"      exit code: {check.exit_code}")
        if check.error_message:
            lines.append(f"      error: {check.error_message[:100]}")
    lines.append("")
    
    # Skipped checks
    lines.append("Skipped by doctrine:")
    for skip in result.skipped_checks:
        lines.append(f"  - {skip['id']}: {skip['reason']}")
    lines.append("")
    
    # Broader gate status
    lines.append("Broader gate status:")
    lines.append(f"  {result.broader_gate_status}")
    lines.append("")
    
    # Failure commands
    if result.failure_commands:
        lines.append("To rerun failed checks:")
        for cmd in result.failure_commands:
            lines.append(f"  {cmd}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_json_output(result: ActLocalResult) -> str:
    """Format JSON output."""
    return json.dumps(result.to_dict(), indent=2)

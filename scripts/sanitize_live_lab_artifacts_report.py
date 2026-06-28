"""Reporting module for sanitize_live_lab_artifacts.

This module contains functions for formatting and reporting sanitization results.
"""

from __future__ import annotations

import json
from pathlib import Path

from sanitize_live_lab_artifacts_contract import Finding, FindingKind


def format_findings_summary(findings: list[Finding]) -> str:
    """Format findings into a human-readable summary."""
    if not findings:
        return "No findings."

    fatal = [f for f in findings if f.kind == FindingKind.FATAL]
    warnings = [f for f in findings if f.kind == FindingKind.WARNING]
    info = [f for f in findings if f.kind == FindingKind.INFO]

    lines = []
    if fatal:
        lines.append(f"FATAL ({len(fatal)}):")
        for f in fatal[:5]:  # Limit output
            lines.append(f"  - {f.message} in {f.file}")
        if len(fatal) > 5:
            lines.append(f"  ... and {len(fatal) - 5} more")

    if warnings:
        lines.append(f"Warnings ({len(warnings)}):")
        for f in warnings[:5]:
            lines.append(f"  - {f.message} in {f.file}")
        if len(warnings) > 5:
            lines.append(f"  ... and {len(warnings) - 5} more")

    if info:
        lines.append(f"Info ({len(info)}):")
        for f in info[:3]:
            lines.append(f"  - {f.message} in {f.file}")

    return "\n".join(lines)


def write_findings_json(
    output_dir: Path,
    success: bool,
    findings: list[Finding],
    results: list,
) -> Path:
    """Write findings to a JSON file for downstream consumption.
    
    Returns the path to the findings file.
    """
    findings_path = output_dir / "_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    
    fatal_count = sum(1 for f in findings if f.kind == FindingKind.FATAL)
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    
    findings_data = {
        "scan_completed": True,
        "success": success,
        "upload_safe": fatal_count == 0 and success,
        "total_files": total,
        "succeeded": succeeded,
        "fatal_count": fatal_count,
        "findings": [
            {
                "kind": f.kind,
                "message": f.message,
                "file": f.file,
                "context": f.context,
            }
            for f in findings
        ],
    }
    findings_path.write_text(json.dumps(findings_data, indent=2))
    return findings_path


def print_verbose_results(results: list, input_dir: Path) -> None:
    """Print verbose sanitization results."""
    print("Sanitization results:")
    for result in results:
        status = "✓" if result.success else "✗"
        print(f"  {status} {result.input_path.relative_to(input_dir)}")
        if result.error:
            print(f"    Error: {result.error}")


def print_summary(
    results: list,
    findings: list[Finding],
    success: bool,
) -> tuple[int, int, int]:
    """Print sanitization summary.
    
    Returns (total, succeeded, fatal_count).
    """
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    fatal_count = sum(1 for f in findings if f.kind == FindingKind.FATAL)
    warning_count = sum(1 for f in findings if f.kind == FindingKind.WARNING)
    info_count = sum(1 for f in findings if f.kind == FindingKind.INFO)

    print(f"Summary: {succeeded}/{total} files sanitized")
    print(f"Findings: {len(findings)} ({fatal_count} fatal, "
          f"{warning_count} warnings, "
          f"{info_count} info)")
    
    return total, succeeded, fatal_count

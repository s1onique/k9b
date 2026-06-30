"""Reporting utilities for OTel demo lab contract verification."""

from __future__ import annotations

import json
import sys

from scripts.otel_lab_contracts.models import VerificationReport


def format_report(report: VerificationReport, json_output: bool) -> str:
    """Format verification report for output.

    When report fails, emits GitHub Actions error annotations to stderr
    for CI visibility. JSON output remains unchanged.
    """
    # Emit GitHub Actions annotations on failure (for CI visibility)
    if not report.passed:
        for error in report.errors:
            print(f"::error title=Live Lab Contract Failed::{error}", file=sys.stderr)
        for warning in report.warnings:
            print(f"::warning title=Live Lab Contract Warning::{warning}", file=sys.stderr)

    if json_output:
        return json.dumps(
            {
                "passed": report.passed,
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "phase": c.phase,
                        "reason": c.reason,
                        "details": c.details,
                    }
                    for c in report.checks
                ],
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
        )

    # Human-readable output
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("LIVE-LAB CONTRACT VERIFICATION REPORT")
    lines.append("=" * 60)

    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        reason = f" ({check.reason})" if check.reason else ""
        lines.append(f"  [{status}] {check.phase}: {check.name}{reason}")

    if report.errors:
        lines.append("")
        lines.append("ERRORS:")
        for error in report.errors:
            lines.append(f"  - {error}")

    if report.warnings:
        lines.append("")
        lines.append("WARNINGS:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")

    lines.append("")
    lines.append(f"VERIFICATION GATE: {'PASSED' if report.passed else 'FAILED'}")

    return "\n".join(lines)

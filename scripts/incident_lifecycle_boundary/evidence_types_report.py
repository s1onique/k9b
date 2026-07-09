"""Evidence type reporting: human-readable formatting.

This module provides formatting utilities for evidence type check results.
"""

from __future__ import annotations


def format_evidence_type_report(errors: list[str]) -> str:
    """Format a list of evidence type errors into a human-readable report.

    Args:
        errors: List of error messages from evidence type checks.

    Returns:
        Formatted report string with header and bullet points.
    """
    if not errors:
        return "✓ Evidence type contract check passed"

    lines = ["Evidence type contract violations found:"]
    for error in errors:
        lines.append(f"  • {error}")

    return "\n".join(lines)


__all__ = [
    "format_evidence_type_report",
]

"""
Report formatting for K3s CNPG incident lab artifact verification.

This module provides report formatting functions for verification results.
"""

from __future__ import annotations

from sanitize_live_lab_artifacts_contract import FindingKind
from verify_k3s_cnpg_incident_lab_artifact_contract import VerificationContext


def format_findings_report(ctx: VerificationContext) -> str:
    """Format verification findings into a structured report."""
    
    if not ctx.findings:
        return ""

    lines = []
    lines.append("\n" + "=" * 50)
    lines.append("VERIFICATION FINDINGS")
    lines.append("=" * 50)

    # Group by severity
    fatal = [f for f in ctx.findings if f.kind == FindingKind.FATAL]
    warnings = [f for f in ctx.findings if f.kind == FindingKind.WARNING]
    info = [f for f in ctx.findings if f.kind == FindingKind.INFO]

    if fatal:
        lines.append(f"\nFATAL ({len(fatal)}):")
        for f in fatal[:10]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")
        if len(fatal) > 10:
            lines.append(f"  ... and {len(fatal) - 10} more fatal findings")

    if warnings:
        lines.append(f"\nWarnings ({len(warnings)}):")
        for f in warnings[:5]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")
        if len(warnings) > 5:
            lines.append(f"  ... and {len(warnings) - 5} more warnings")

    if info:
        lines.append(f"\nInfo ({len(info)}):")
        for f in info[:3]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")

    return "\n".join(lines)

"""Writer functions for incident bundle persistence.

This module contains functions for writing incident evidence bundles
to disk with deterministic layout.
"""

from __future__ import annotations

import json
from pathlib import Path

from .incident_models import IncidentEvidenceBundle


def write_incident_bundle(
    bundle: IncidentEvidenceBundle,
    output_dir: Path,
) -> dict[str, Path]:
    """Write incident bundle to disk with deterministic layout.

    Returns:
        Mapping of file names to written paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    # Write incident.json (machine-readable summary)
    incident_path = output_dir / "incident.json"
    incident_path.write_text(
        json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["incident.json"] = incident_path

    # Write evidence-index.md (human-readable index)
    index_path = output_dir / "evidence-index.md"
    index_path.write_text(_build_evidence_index(bundle), encoding="utf-8")
    written["evidence-index.md"] = index_path

    # Write objects/
    objects_dir = output_dir / "objects"
    objects_dir.mkdir(exist_ok=True)

    pods_path = objects_dir / "pods.json"
    pods_path.write_text(
        json.dumps([p.to_dict() for p in bundle.pods], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["objects/pods.json"] = pods_path

    deployments_path = objects_dir / "deployments.json"
    deployments_path.write_text(
        json.dumps(
            [d.to_dict() for d in bundle.deployments], indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    written["objects/deployments.json"] = deployments_path

    events_path = objects_dir / "events.json"
    events_path.write_text(
        json.dumps([e.to_dict() for e in bundle.events], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["objects/events.json"] = events_path

    # Write summary/symptoms.md
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(exist_ok=True)

    symptoms_path = summary_dir / "symptoms.md"
    symptoms_path.write_text(_build_symptoms_report(bundle), encoding="utf-8")
    written["summary/symptoms.md"] = symptoms_path

    return written


def _build_evidence_index(bundle: IncidentEvidenceBundle) -> str:
    """Build evidence index markdown."""
    lines = [
        "# Incident Evidence Index",
        "",
        f"**Bundle ID**: {bundle.metadata.bundle_id}",
        f"**Captured**: {bundle.metadata.captured_at.isoformat()}",
        f"**Namespace**: {bundle.metadata.namespace}",
        f"**Context**: {bundle.metadata.context or 'in-cluster'}",
        "",
        "## Evidence Summary",
        "",
        f"- Pods: {bundle.metadata.total_pods} (failing: {bundle.metadata.failing_pods_count})",
        f"- Deployments: {bundle.metadata.total_deployments}",
        f"- Events: {bundle.metadata.total_events}",
        f"- Symptoms: {bundle.metadata.symptoms_count}",
        "",
        "## Bundle Contents",
        "",
        "```",
        "incident.json          # Machine-readable incident bundle",
        "evidence-index.md      # This file",
        "objects/",
        "  pods.json            # All pods in namespace",
        "  deployments.json     # All deployments in namespace",
        "  events.json          # Events in namespace",
        "summary/",
        "  symptoms.md          # Detected symptoms and triage",
        "```",
        "",
        "## Detected Symptoms",
        "",
    ]

    if bundle.symptoms:
        for symptom in bundle.symptoms:
            lines.append(
                f"- **{symptom.symptom_type}** ({symptom.severity}): {symptom.message}"
            )
    else:
        lines.append("_No symptoms detected_")

    if bundle.collection_errors:
        lines.append("")
        lines.append("## Collection Errors")
        lines.append("")
        for error in bundle.collection_errors:
            lines.append(f"- {error}")

    lines.append("")
    return "\n".join(lines)


def _build_symptoms_report(bundle: IncidentEvidenceBundle) -> str:
    """Build symptoms report markdown."""
    lines = [
        "# Incident Symptoms",
        "",
        f"**Bundle ID**: {bundle.metadata.bundle_id}",
        f"**Namespace**: {bundle.metadata.namespace}",
        "",
        f"Total symptoms detected: {bundle.metadata.symptoms_count}",
        "",
    ]

    if not bundle.symptoms:
        lines.append("## No Symptoms Detected")
        lines.append("")
        lines.append("No mechanical symptoms were detected in the captured evidence.")
        lines.append("Manual investigation may be required.")
    else:
        # Group by severity
        errors = [s for s in bundle.symptoms if s.severity == "error"]
        warnings = [s for s in bundle.symptoms if s.severity == "warning"]

        if errors:
            lines.append("## Critical Symptoms (Error)")
            lines.append("")
            for symptom in errors:
                pod_info = f"Pod: `{symptom.pod_name}`" if symptom.pod_name else ""
                lines.append(f"- **{symptom.symptom_type}**")
                lines.append(f"  - {pod_info}")
                lines.append(f"  - {symptom.message}")
                lines.append("")

        if warnings:
            lines.append("## Warning Symptoms")
            lines.append("")
            for symptom in warnings:
                pod_info = f"Pod: `{symptom.pod_name}`" if symptom.pod_name else ""
                lines.append(f"- **{symptom.symptom_type}**")
                lines.append(f"  - {pod_info}")
                lines.append(f"  - {symptom.message}")
                lines.append("")

    lines.append("## Manual Investigation Required")
    lines.append("")
    lines.append(
        "This is a deterministic symptom summary only. "
        "LLM review of the raw evidence is required for root cause analysis."
    )

    return "\n".join(lines)


__all__ = [
    "write_incident_bundle",
]

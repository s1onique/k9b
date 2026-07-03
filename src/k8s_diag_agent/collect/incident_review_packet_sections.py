"""Section builders for incident review packets.

This module contains pure section-building functions that construct
markdown sections for the incident review packet.

Each function takes a bundle and returns a list of markdown lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_models import (
    IncidentEvidenceBundle,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


def build_metadata_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build metadata section."""
    meta = bundle.metadata
    return [
        "## Metadata",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Bundle ID | `{meta.bundle_id}` |",
        f"| Captured At | {meta.captured_at.isoformat()} |",
        f"| Namespace | `{meta.namespace}` |",
        f"| Context | {meta.context or 'in-cluster (default)'} |",
        f"| Event Lookback | {meta.since_hours}h |",
        "",
    ]


def build_evidence_summary(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build evidence summary section."""
    meta = bundle.metadata
    return [
        "## Evidence Summary",
        "",
        f"- **Total Pods**: {meta.total_pods}",
        f"- **Failing Pods**: {meta.failing_pods_count}",
        f"- **Total Deployments**: {meta.total_deployments}",
        f"- **Total Events**: {meta.total_events}",
        f"- **Detected Symptoms**: {meta.symptoms_count}",
        "",
    ]


def build_symptoms_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build detected symptoms section."""
    lines = [
        "## Detected Symptoms",
        "",
    ]

    if not bundle.symptoms:
        lines.extend([
            "_No symptoms detected in captured evidence._",
            "",
        ])
    else:
        # Group by severity
        errors = [s for s in bundle.symptoms if s.severity == "error"]
        warnings = [s for s in bundle.symptoms if s.severity == "warning"]

        if errors:
            lines.append("### Critical (Error)")
            lines.append("")
            for symptom in errors:
                lines.append(f"- **{symptom.symptom_type}**")
                if symptom.pod_name:
                    lines.append(f"  - Pod: `{symptom.pod_name}`")
                lines.append(f"  - {symptom.message}")
                lines.append("")
        else:
            lines.append("### Critical (Error)")
            lines.append("")
            lines.append("_No critical symptoms detected._")
            lines.append("")

        if warnings:
            lines.append("### Warning")
            lines.append("")
            for symptom in warnings:
                lines.append(f"- **{symptom.symptom_type}**")
                if symptom.pod_name:
                    lines.append(f"  - Pod: `{symptom.pod_name}`")
                lines.append(f"  - {symptom.message}")
                lines.append("")
        else:
            lines.append("### Warning")
            lines.append("")
            lines.append("_No warning symptoms detected._")
            lines.append("")

    return lines


def build_failing_pods_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build failing pods section."""
    lines = [
        "## Failing Pods",
        "",
    ]

    failing_pods = [p for p in bundle.pods if p.is_failing]

    if not failing_pods:
        lines.extend([
            "_No failing pods detected._",
            "",
        ])
    else:
        lines.append(f"Found {len(failing_pods)} failing pod(s):")
        lines.append("")
        lines.append("| Pod Name | Status | Restarts | Reason |")
        lines.append("|---------|--------|---------|-------|")
        for pod in failing_pods:
            lines.append(
                f"| `{pod.name}` | {pod.health_status.value} | "
                f"{pod.restart_count} | {pod.reason or '-'} |"
            )
        lines.append("")

    return lines


def build_deployment_health_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build deployment health section."""
    lines = [
        "## Deployment Health",
        "",
    ]

    if not bundle.deployments:
        lines.extend([
            "_No deployments found in namespace._",
            "",
        ])
    else:
        lines.append("| Deployment | Replicas | Ready | Available |")
        lines.append("|------------|----------|-------|-----------|")
        for deploy in bundle.deployments:
            available = "✅" if deploy.available else "❌"
            lines.append(
                f"| `{deploy.name}` | {deploy.replicas} | "
                f"{deploy.ready_replicas}/{deploy.updated_replicas} | {available} |"
            )
        lines.append("")

        # Highlight unhealthy deployments
        unhealthy = [d for d in bundle.deployments if not d.available]
        if unhealthy:
            lines.extend([
                "**Unhealthy Deployments:**",
                "",
            ])
            for deploy in unhealthy:
                diff = deploy.replicas - deploy.available_replicas
                lines.append(
                    f"- `{deploy.name}`: {diff} replica(s) unavailable "
                    f"({deploy.ready_replicas}/{deploy.updated_replicas} ready)"
                )
            lines.append("")

    return lines


def build_warning_events_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build warning events section."""
    lines = [
        "## Warning Events",
        "",
    ]

    warning_events = [e for e in bundle.events if e.type.lower() == "warning"]

    if not warning_events:
        lines.extend([
            "_No warning events in captured time window._",
            "",
        ])
    else:
        lines.append(f"{len(warning_events)} warning event(s) in captured time window:")
        lines.append("")
        lines.append("| Event | Reason | Involved Object | Count |")
        lines.append("|-------|--------|-----------------|-------|")
        for event in warning_events[:20]:  # Limit to 20 events
            involved = f"{event.involved_object_kind}:{event.involved_object_name}" if event.involved_object_name else "-"
            lines.append(
                f"| {event.name} | {event.reason} | {involved} | {event.count} |"
            )
        if len(warning_events) > 20:
            lines.append("")
            lines.append(f"_... and {len(warning_events) - 20} more events (truncated for packet size)_")
        lines.append("")

    return lines


def build_collection_errors_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build collection errors section."""
    lines = [
        "## Collection Errors",
        "",
    ]

    if not bundle.collection_errors:
        lines.extend([
            "_No collection errors._",
            "",
        ])
    else:
        lines.append(f"{len(bundle.collection_errors)} error(s) during collection:")
        lines.append("")
        for error in bundle.collection_errors:
            lines.append(f"- {error}")
        lines.append("")
        lines.append("**Note:** Collection errors may indicate incomplete evidence. ")
        lines.append("Consider re-capturing or investigating the affected components.")
        lines.append("")

    return lines


def build_known_limitations_section() -> list[str]:
    """Build known limitations section."""
    return [
        "## Known Limitations",
        "",
        "This packet captures a snapshot of cluster state at capture time. The following "
        "limitations apply:",
        "",
        "1. **Pod logs are NOT included**: Container logs are not part of this packet. "
        "Use k9b's diagnostic drilldown to capture pod logs.",
        "",
        "2. **Time-scoped evidence**: Events are filtered to the last 2 hours by default. "
        "Older events may contain relevant context but are not captured.",
        "",
        "3. **Namespace scope**: Only resources in the specified namespace are captured. "
        "Cross-namespace dependencies may not be visible.",
        "",
        "4. **Single context**: Collection targets one Kubernetes context (cluster). "
        "Multi-cluster correlation requires separate captures.",
        "",
        "5. **No historical comparison**: This packet shows current state. "
        "Historical drift detection requires baseline comparison.",
        "",
    ]


def build_raw_evidence_index(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build raw evidence index section."""
    meta = bundle.metadata
    return [
        "## Raw Evidence Index",
        "",
        f"This packet references the following raw evidence from bundle `{meta.bundle_id}`:",
        "",
        f"- **Pods**: {meta.total_pods} pod summary record(s)",
        f"- **Deployments**: {meta.total_deployments} deployment summary record(s)",
        f"- **Events**: {meta.total_events} event summary record(s)",
        f"- **Symptoms**: {meta.symptoms_count} symptom detection record(s)",
        "",
        "The raw evidence is available in the incident bundle artifact for detailed inspection.",
        "",
    ]


def build_next_evidence_questions(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build questions for next evidence collection."""
    lines = [
        "---",
        "",
        "## Questions for Next Evidence Collection",
        "",
        "To continue the investigation, consider:",
        "",
    ]

    # Dynamic questions based on evidence
    if any(p.health_status.value == "crash_loop" for p in bundle.pods):
        lines.extend([
            "1. **CrashLoop investigation**: Capture container logs for the crashing pod",
            "   - Use k9b pod log drilldown to collect container logs",
        ])

    if any(p.health_status.value == "image_pull_error" for p in bundle.pods):
        lines.extend([
            "2. **Image pull investigation**: Check image pull configuration",
            "   - Use k9b to capture ImagePullSecrets on the namespace and pod",
        ])

    if any(p.health_status.value == "pending" for p in bundle.pods):
        lines.extend([
            "3. **Pending pod investigation**: Collect scheduler and node resource evidence:",
            "   - Use k9b pod describe evidence capture for scheduling events",
            "   - Use k9b node capacity evidence capture to verify resource availability",
        ])

    # Check for OOMKill indicators
    if any("oom" in e.reason.lower() or "oom" in e.message.lower() for e in bundle.events):
        lines.extend([
            "4. **Memory pressure investigation**: Check resource limits and node memory:",
            "   - Use k9b node detail evidence capture for memory pressure signals",
            "   - Use k9b to capture pod resource limits and requests",
        ])

    # Default questions if no specific patterns
    if len(lines) == 5:  # Only the static text
        lines.extend([
            "1. **Pod log capture**: Capture container logs for failing pods",
            "2. **Event timeline**: Check for warning events in adjacent namespaces",
            "3. **Node health**: Collect node-level evidence for scheduling issues",
        ])

    lines.append("")
    lines.append("**Remember**: Collect additional evidence before proposing remediation.")
    lines.append("")

    return lines


def build_candidates_section(bundle: IncidentEvidenceBundle) -> list[str]:
    """Build incident candidates section."""
    lines = [
        "## Incident Candidates",
        "",
        "**Note:** Candidates are deterministic signals, not root cause determinations. "
        "No remediation is claimed.",
        "",
    ]

    if not bundle.candidates:
        lines.extend([
            "_No incident candidates detected in captured evidence._",
            "",
        ])
    else:
        lines.append(f"**{len(bundle.candidates)}** candidate(s) detected:")
        lines.append("")

        # Group by severity
        errors = [c for c in bundle.candidates if c.severity.value == "error"]
        warnings = [c for c in bundle.candidates if c.severity.value == "warning"]

        if errors:
            lines.append("### Critical (Error)")
            lines.append("")
            for candidate in errors:
                lines.extend(_format_candidate(candidate))
                lines.append("")

        if warnings:
            lines.append("### Warning")
            lines.append("")
            for candidate in warnings:
                lines.extend(_format_candidate(candidate))
                lines.append("")

    return lines


def _format_candidate(candidate: IncidentCandidate) -> list[str]:
    """Format a single candidate for the review packet."""
    # Include raw_object_kind in display for disambiguation when object_kind is UNKNOWN
    kind_display = candidate.object_kind.value
    if candidate.raw_object_kind:
        kind_display = candidate.raw_object_kind

    lines = [
        f"- **{candidate.candidate_class.value}**",
        f"  - Object: `{kind_display}/{candidate.object_name}`",
        f"  - Namespace: `{candidate.namespace}`",
        f"  - Evidence needed: {', '.join(candidate.evidence_needed)}",
    ]

    # Add signals summary
    if candidate.signals:
        lines.append("  - Signals:")
        for signal in candidate.signals[:3]:  # Limit to 3 signals per candidate
            lines.append(f"    - {signal.reason}: {signal.message[:80]}{'...' if len(signal.message) > 80 else ''}")

    return lines


__all__ = [
    "build_metadata_section",
    "build_evidence_summary",
    "build_symptoms_section",
    "build_failing_pods_section",
    "build_deployment_health_section",
    "build_warning_events_section",
    "build_collection_errors_section",
    "build_known_limitations_section",
    "build_raw_evidence_index",
    "build_next_evidence_questions",
    "build_candidates_section",
]

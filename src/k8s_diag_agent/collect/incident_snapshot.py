"""Incident snapshot collection - compatibility facade.

This module provides read-only Kubernetes incident evidence collection for
k9b's internal reviewer pipeline. It captures namespace-scoped evidence into
a deterministic bundle without mutating the cluster.

**Self-Contained k9b-Only Constraint:**

The complete incident investigation workflow must run inside k9b:
- no Cline required
- no manual kubectl required
- no operator exec into pods required
- no local CLI required
- no copy/paste to external tools required
- no external artifact massaging required

Development-time helpers are allowed, but every helper must either:
1. become an internal k9b backend/UI capability, or
2. be explicitly marked as temporary scaffolding and removed before the epic closes.

**Current Implementation Note:**

This module is a compatibility facade that re-exports from split modules.
The actual implementation is distributed across:
- incident_models.py: dataclasses and enums
- incident_parsers.py: parsing functions
- incident_collectors.py: kubectl collection (TEMPORARY SCAFFOLD - to be replaced with in-process API)
- incident_triage.py: symptom detection
- incident_writer.py: bundle persistence

For review packet generation, see: incident_review_packet.py

This file remains for backward compatibility with existing imports.
"""

from __future__ import annotations

from typing import Any

from ..datetime_utils import now_utc
from .incident_candidates import detect_incident_candidates
from .incident_collectors import (
    DEFAULT_SINCE_HOURS,
    collect_deployments,
    collect_events,
    collect_pods,
)
from .incident_models import (
    DeploymentSummary,
    EventSummary,
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    IncidentSymptom,
    PodHealthStatus,
    PodSummary,
)
from .incident_parsers import (
    parse_deployment_summary,
    parse_event_summary,
    parse_pod_summary,
)
from .incident_triage import detect_symptoms
from .incident_writer import write_incident_bundle

# Re-export for backward compatibility with tests
_parse_pod_summary = parse_pod_summary
_parse_deployment_summary = parse_deployment_summary
_parse_event_summary = parse_event_summary
_detect_symptoms = detect_symptoms

__all__ = [
    "IncidentEvidenceBundle",
    "IncidentBundleMetadata",
    "IncidentSymptom",
    "PodHealthStatus",
    "PodSummary",
    "DeploymentSummary",
    "EventSummary",
    "collect_incident_snapshot",
    "write_incident_bundle",
    "DEFAULT_SINCE_HOURS",
    "_parse_pod_summary",
    "_parse_deployment_summary",
    "_parse_event_summary",
    "_detect_symptoms",
]


def collect_incident_snapshot(
    namespace: str,
    context: str | None = None,
    since_hours: int = DEFAULT_SINCE_HOURS,
) -> IncidentEvidenceBundle:
    """Collect incident evidence for a namespace.

    Args:
        namespace: Kubernetes namespace to capture
        context: Kubernetes context (None for in-cluster)
        since_hours: Lookback window for events

    Returns:
        IncidentEvidenceBundle with sanitized evidence
    """
    errors: list[str] = []
    now = now_utc()

    # Generate deterministic bundle ID
    bundle_id = f"{namespace}-{now.strftime('%Y%m%d-%H%M%S')}"

    # Projection metadata from tool output budget/spill infrastructure
    tool_output_projection: dict[str, Any] = {}

    # Collect pods
    pods, pod_errors, pod_projection_metadata = collect_pods(namespace, context)
    errors.extend(pod_errors)
    if pod_projection_metadata:
        tool_output_projection["pods"] = pod_projection_metadata

    # Collect deployments
    deployments, deploy_errors = collect_deployments(namespace, context)
    errors.extend(deploy_errors)

    # Collect events
    events, event_errors, event_projection_metadata = collect_events(namespace, context, since_hours)
    errors.extend(event_errors)
    if event_projection_metadata:
        tool_output_projection["events"] = event_projection_metadata

    # Identify failing pods
    failing_pods = [p for p in pods if p.is_failing]

    # Detect symptoms
    symptoms = detect_symptoms(pods, events)

    # Detect incident candidates from collected evidence
    candidates = detect_incident_candidates(
        pods=pods,
        deployments=deployments,
        events=events,
    )

    metadata = IncidentBundleMetadata(
        bundle_id=bundle_id,
        captured_at=now,
        namespace=namespace,
        since_hours=since_hours,
        context=context,
        total_pods=len(pods),
        total_events=len(events),
        total_deployments=len(deployments),
        failing_pods_count=len(failing_pods),
        symptoms_count=len(symptoms),
        candidates_count=len(candidates),
    )

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=tuple(errors),
        candidates=candidates,
        tool_output_projection=tool_output_projection,
    )

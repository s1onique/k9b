"""Deterministic next-check serialization functions for the operator UI.

This module contains serializer functions for deterministic next-check payloads:
- Single deterministic next-check summary serialization
- Cluster-level deterministic next-check view serialization
- Full deterministic next-check view serialization

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    DeterministicNextCheckClusterPayload,
    DeterministicNextChecksPayload,
    DeterministicNextCheckSummaryPayload,
)
from .model import (
    DeterministicNextCheckClusterView,
    DeterministicNextCheckSummaryView,
    DeterministicNextChecksView,
)


def _serialize_deterministic_next_check_summary(
    view: DeterministicNextCheckSummaryView,
) -> DeterministicNextCheckSummaryPayload:
    return {
        "description": view.description,
        "owner": view.owner,
        "method": view.method,
        "evidenceNeeded": list(view.evidence_needed),
        "workstream": view.workstream,
        "urgency": view.urgency,
        "isPrimaryTriage": view.is_primary_triage,
        "whyNow": view.why_now,
    }


def _serialize_deterministic_next_check_cluster(
    view: DeterministicNextCheckClusterView,
) -> DeterministicNextCheckClusterPayload:
    return {
        "label": view.label,
        "context": view.context,
        "topProblem": view.top_problem,
        "deterministicNextCheckCount": view.deterministic_next_check_count,
        "deterministicNextCheckSummaries": [_serialize_deterministic_next_check_summary(entry) for entry in view.deterministic_next_check_summaries],
        "drilldownAvailable": view.drilldown_available,
        "assessmentArtifactPath": view.assessment_artifact_path,
        "drilldownArtifactPath": view.drilldown_artifact_path,
    }


def _serialize_deterministic_next_checks(
    view: DeterministicNextChecksView | None,
) -> DeterministicNextChecksPayload | None:
    if not view:
        return None
    return {
        "clusterCount": view.cluster_count,
        "totalNextCheckCount": view.total_next_check_count,
        "clusters": [_serialize_deterministic_next_check_cluster(entry) for entry in view.clusters],
    }

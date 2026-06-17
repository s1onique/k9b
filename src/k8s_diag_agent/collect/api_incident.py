"""Backend API handlers for incident snapshot capture.

This module provides a server-side API for capturing incident evidence
bundles from within the k9b runtime context, triggered by the UI.

NOTE: Pod log collection is NOT implemented in this ACT.
Current bundle scope: pods, deployments, events, symptoms only.
Pod logs (logs/ directory) are explicitly deferred to a future ACT
due to:
- Safe bounded retrieval needed (size limits per pod)
- Log sanitization requirements beyond string-level patterns
- Test coverage for redaction

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..security import sanitize_exception_message
from .incident_snapshot import (
    collect_incident_snapshot,
)

_logger = logging.getLogger(__name__)


# Maximum log lines per pod (safety bound)
MAX_LOG_LINES_PER_POD = 500


@dataclass
class IncidentSnapshotRequest:
    """Request shape for incident snapshot API."""

    namespace: str
    since_hours: int = 2
    context: str | None = None  # None = in-cluster


@dataclass
class IncidentSnapshotResponse:
    """Response shape for incident snapshot API."""

    bundle_id: str
    captured_at: str
    namespace: str
    summary: dict[str, Any]
    bundle: dict[str, Any] | None = None
    error: str | None = None
    download_url: str | None = None
    # Incident promotion fields
    candidates_count: int = 0
    incidents_promoted_count: int = 0
    promoted_incidents: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "bundle_id": self.bundle_id,
            "captured_at": self.captured_at,
            "namespace": self.namespace,
            "summary": self.summary,
        }
        if self.bundle is not None:
            result["bundle"] = self.bundle
        if self.error is not None:
            result["error"] = self.error
        if self.download_url is not None:
            result["download_url"] = self.download_url
        # Always include incident promotion info in summary
        result["summary"] = {
            **self.summary,
            "candidates_count": self.candidates_count,
            "incidents_promoted_count": self.incidents_promoted_count,
        }
        if self.promoted_incidents:
            result["promoted_incidents"] = self.promoted_incidents
        return result


def handle_incident_snapshot(request: IncidentSnapshotRequest) -> IncidentSnapshotResponse:
    """Capture an incident evidence bundle for a namespace.

    This function performs read-only Kubernetes collection to produce
    a sanitized, bounded evidence bundle.

    On successful capture, it promotes any incident candidates into the
    in-memory IncidentStore using the bundle ID.

    Args:
        request: IncidentSnapshotRequest with namespace and options

    Returns:
        IncidentSnapshotResponse with bundle or error
    """
    # Import here to avoid circular imports
    from .incident_store_provider import get_incident_store

    try:
        bundle = collect_incident_snapshot(
            namespace=request.namespace,
            context=request.context,
            since_hours=request.since_hours,
        )

        # Build summary
        summary = {
            "total_pods": bundle.metadata.total_pods,
            "failing_pods_count": bundle.metadata.failing_pods_count,
            "total_deployments": bundle.metadata.total_deployments,
            "total_events": bundle.metadata.total_events,
            "symptoms_count": bundle.metadata.symptoms_count,
            "candidates_count": bundle.metadata.candidates_count,
        }

        # Promote candidates into incident store
        promoted_incidents: list[dict[str, Any]] = []
        incidents_promoted_count = 0

        if bundle.candidates:
            try:
                store = get_incident_store()
                promoted = store.promote_candidates_from_bundle(
                    bundle_id=bundle.metadata.bundle_id,
                    candidates=bundle.candidates,
                    observed_at=bundle.metadata.captured_at,
                )
                # Convert to dicts for API response
                promoted_incidents = [inc.to_dict() for inc in promoted]
                incidents_promoted_count = len(promoted_incidents)
            except Exception as exc:
                # Promotion errors must not mask successful evidence capture
                # Log but don't fail the response
                # Use sanitized message to prevent credential/exception leakage
                sanitized_message = sanitize_exception_message(exc, max_length=200)
                _logger.warning(
                    "Incident promotion failed for bundle %s: %s",
                    bundle.metadata.bundle_id,
                    sanitized_message,
                )

        return IncidentSnapshotResponse(
            bundle_id=bundle.metadata.bundle_id,
            captured_at=bundle.metadata.captured_at.isoformat(),
            namespace=bundle.metadata.namespace,
            summary=summary,
            bundle=bundle.to_dict(),
            candidates_count=bundle.metadata.candidates_count,
            incidents_promoted_count=incidents_promoted_count,
            promoted_incidents=promoted_incidents,
        )

    except (RuntimeError, json.JSONDecodeError, OSError) as exc:
        # Handle expected collection failures (subprocess errors, JSON parse errors, file errors)
        # All errors are sanitized before being returned to the operator
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Incident snapshot collection failed for namespace %s: %s",
            request.namespace,
            sanitized_message,
        )
        return IncidentSnapshotResponse(
            bundle_id="",
            captured_at=datetime.now(UTC).isoformat(),
            namespace=request.namespace,
            summary={
                "total_pods": 0,
                "failing_pods_count": 0,
                "total_deployments": 0,
                "total_events": 0,
                "symptoms_count": 0,
                "candidates_count": 0,
            },
            error=sanitized_message,
        )


__all__ = [
    "IncidentSnapshotRequest",
    "IncidentSnapshotResponse",
    "handle_incident_snapshot",
    "MAX_LOG_LINES_PER_POD",
]

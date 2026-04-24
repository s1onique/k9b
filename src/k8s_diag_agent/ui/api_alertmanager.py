"""Alertmanager serialization functions for the operator UI.

This module contains serializer functions for Alertmanager-related payloads:
- Compact alert summary view
- Single Alertmanager source
- Full Alertmanager source inventory

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    AlertmanagerCompactPayload,
    AlertmanagerSourcePayload,
    AlertmanagerSourcesPayload,
    ClusterAlertSummaryPayload,
)
from .model import (
    AlertmanagerCompactView,
    AlertmanagerSourcesView,
    AlertmanagerSourceView,
)


def _serialize_alertmanager_compact(
    view: AlertmanagerCompactView | None,
) -> AlertmanagerCompactPayload | None:
    """Serialize the Alertmanager compact alert summary view to payload dict."""
    if not view:
        return None
    # Serialize per-cluster summaries
    by_cluster_payload: list[ClusterAlertSummaryPayload] = []
    for summary in view.by_cluster:
        by_cluster_payload.append({
            "cluster": summary.cluster,
            "alert_count": summary.alert_count,
            "severity_counts": {str(k): v for k, v in summary.severity_counts},
            "state_counts": {str(k): v for k, v in summary.state_counts},
            "top_alert_names": list(summary.top_alert_names),
            "affected_namespaces": list(summary.affected_namespaces),
            "affected_services": list(summary.affected_services),
        })
    return {
        "status": view.status,
        "alert_count": view.alert_count,
        "severity_counts": {str(k): v for k, v in view.severity_counts},
        "state_counts": {str(k): v for k, v in view.state_counts},
        "top_alert_names": list(view.top_alert_names),
        "affected_namespaces": list(view.affected_namespaces),
        "affected_clusters": list(view.affected_clusters),
        "affected_services": list(view.affected_services),
        "truncated": view.truncated,
        "captured_at": view.captured_at,
        "by_cluster": by_cluster_payload,
    }


def _serialize_alertmanager_source(view: AlertmanagerSourceView) -> AlertmanagerSourcePayload:
    """Serialize a single Alertmanager source to payload dict."""
    return {
        "source_id": view.source_id,
        "endpoint": view.endpoint,
        "namespace": view.namespace,
        "name": view.name,
        "origin": view.origin,
        "state": view.state,
        "discovered_at": view.discovered_at,
        "verified_at": view.verified_at,
        "last_check": view.last_check,
        "last_error": view.last_error,
        "verified_version": view.verified_version,
        "confidence_hints": list(view.confidence_hints),
        # Deduplication provenance fields
        "merged_provenances": list(view.merged_provenances),
        "display_provenance": view.display_provenance,
        # Computed UI fields
        "is_manual": view.is_manual,
        "is_tracking": view.is_tracking,
        "can_disable": view.can_disable,
        "can_promote": view.can_promote,
        "display_origin": view.display_origin,
        "display_state": view.display_state,
        "provenance_summary": view.provenance_summary,
        # Manual source mode for distinct status display
        "manual_source_mode": view.manual_source_mode,
        # Cluster association for per-cluster UI filtering
        "cluster_label": view.cluster_label,
        # Identity fields for cross-run historical tracking
        # canonical_entity_id: deterministic hash from normalized defining facts
        "canonicalEntityId": view.canonical_entity_id,
        # Identity anchors for cross-cluster disambiguation
        "cluster_uid": view.cluster_uid,
        "object_uid": view.object_uid,
    }


def _serialize_alertmanager_sources(
    view: AlertmanagerSourcesView | None,
) -> AlertmanagerSourcesPayload | None:
    """Serialize the full Alertmanager source inventory to payload."""
    if not view:
        return None
    return {
        "sources": [_serialize_alertmanager_source(s) for s in view.sources],
        "total_count": view.total_count,
        "tracked_count": view.tracked_count,
        "manual_count": view.manual_count,
        "degraded_count": view.degraded_count,
        "missing_count": view.missing_count,
        "discovery_timestamp": view.discovery_timestamp,
        "cluster_context": view.cluster_context,
    }

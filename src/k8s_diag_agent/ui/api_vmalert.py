"""vmalert serialization functions for the operator UI.

This module contains serializer functions for vmalert-related payloads:
- Single vmalert source
- Full vmalert source inventory

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    VmalertRuleStateAlertPayload,
    VmalertRuleStateFetchErrorPayload,
    VmalertRuleStatePayload,
    VmalertRuleStateRuleGroupPayload,
    VmalertSourcePayload,
    VmalertSourcesPayload,
)
from .model import (
    VmalertRuleStateAlertView,
    VmalertRuleStateFetchErrorView,
    VmalertRuleStateRuleGroupView,
    VmalertRuleStateView,
    VmalertSourcesView,
    VmalertSourceView,
)


def _serialize_vmalert_source(view: VmalertSourceView) -> VmalertSourcePayload:
    """Serialize a single vmalert source to payload dict."""
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


def _serialize_vmalert_sources(
    view: VmalertSourcesView | None,
) -> VmalertSourcesPayload | None:
    """Serialize the full vmalert source inventory to payload."""
    if not view:
        return None
    return {
        "sources": [_serialize_vmalert_source(s) for s in view.sources],
        "total_count": view.total_count,
        "source_count": view.source_count,
        "discovered_count": view.discovered_count,
        "discovered_but_unverified_count": view.discovered_but_unverified_count,
        "auto_tracked_count": view.auto_tracked_count,
        "manual_count": view.manual_count,
        "discovery_timestamp": view.discovery_timestamp,
        "cluster_context": view.cluster_context,
    }


def _serialize_vmalert_rule_state_alert(
    view: VmalertRuleStateAlertView,
) -> VmalertRuleStateAlertPayload:
    """Serialize a single vmalert alert to payload dict."""
    return {
        "alertname": view.alertname,
        "state": view.state,
        "severity": view.severity,
        "cluster_label": view.cluster_label,
        "namespace": view.namespace,
        "workload": view.workload,
        "pod": view.pod,
        "instance": view.instance,
        "summary": view.summary,
        "description": view.description,
        "active_at": view.active_at,
        "starts_at": view.starts_at,
        "source_endpoint": view.source_endpoint,
        "group_name": view.group_name,
        "rule_name": view.rule_name,
    }


def _serialize_vmalert_rule_state_rule_group(
    view: VmalertRuleStateRuleGroupView,
) -> VmalertRuleStateRuleGroupPayload:
    """Serialize a vmalert rule group to payload dict."""
    return {
        "name": view.name,
        "file": view.file,
        "interval": view.interval,
        "rule_count": view.rule_count,
        "firing_alert_count": view.firing_alert_count,
        "error_count": view.error_count,
    }


def _serialize_vmalert_rule_state_fetch_error(
    view: VmalertRuleStateFetchErrorView,
) -> VmalertRuleStateFetchErrorPayload:
    """Serialize a vmalert fetch error to payload dict."""
    return {
        "source_endpoint": view.source_endpoint,
        "source_id": view.source_id,
        "status": view.status,
        "error": view.error,
    }


def _serialize_vmalert_rule_state(
    view: VmalertRuleStateView | None,
) -> VmalertRuleStatePayload | None:
    """Serialize vmalert rule state to payload.

    Returns None when artifact is missing (not an error).
    """
    if not view:
        return None
    return {
        "source_count": view.source_count,
        "fetched_source_count": view.fetched_source_count,
        "failed_source_count": view.failed_source_count,
        "alert_count": view.alert_count,
        "firing_alert_count": view.firing_alert_count,
        "pending_alert_count": view.pending_alert_count,
        "critical_firing_count": view.critical_firing_count,
        "rule_group_count": view.rule_group_count,
        "fetch_error_count": view.fetch_error_count,
        "captured_at": view.captured_at,
        "alerts": [_serialize_vmalert_rule_state_alert(a) for a in view.alerts],
        "rule_groups": [_serialize_vmalert_rule_state_rule_group(g) for g in view.rule_groups],
        "fetch_errors": [_serialize_vmalert_rule_state_fetch_error(e) for e in view.fetch_errors],
    }

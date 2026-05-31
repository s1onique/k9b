"""TypedDict payload definitions for Alertmanager contracts.

This module contains pure data contracts (TypedDict definitions) for Alertmanager
alert summaries and source inventory.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.

Extraction rationale:
    - Separating Alertmanager contracts makes the API boundary easier to audit.
    - Allows focused testing and documentation for Alertmanager payloads.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "ClusterAlertSummaryPayload",
    "AlertmanagerCompactPayload",
    "AlertmanagerSourcePayload",
    "AlertmanagerSourcesPayload",
]


class ClusterAlertSummaryPayload(TypedDict, total=False):
    """Payload for per-cluster alert summary."""

    cluster: str
    alert_count: int
    severity_counts: dict[str, int]
    state_counts: dict[str, int]
    top_alert_names: list[str]
    affected_namespaces: list[str]
    affected_services: list[str]


class AlertmanagerCompactPayload(TypedDict, total=False):
    """Payload for the Alertmanager compact alert summary view."""

    status: str
    alert_count: int
    severity_counts: dict[str, int]
    state_counts: dict[str, int]
    top_alert_names: list[str]
    affected_namespaces: list[str]
    affected_clusters: list[str]
    affected_services: list[str]
    truncated: bool
    captured_at: str
    by_cluster: list[ClusterAlertSummaryPayload]


class AlertmanagerSourcePayload(TypedDict, total=False):
    """Payload for a single Alertmanager source."""

    source_id: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str
    state: str
    discovered_at: str | None
    verified_at: str | None
    last_check: str | None
    last_error: str | None
    verified_version: str | None
    confidence_hints: list[str]
    # Deduplication provenance fields
    merged_provenances: list[str]  # all contributing origins
    display_provenance: str  # human-readable provenance string
    # Manual provenance: distinguishes operator-configured vs operator-promoted
    manual_source_mode: str | None  # operator-configured, operator-promoted, or not-present
    # Computed UI fields
    is_manual: bool
    is_tracking: bool
    can_disable: bool
    can_promote: bool
    display_origin: str
    display_state: str
    provenance_summary: str
    # Cluster association for per-cluster UI filtering
    cluster_label: str | None
    # Deterministic identity fields for historical/debug tracking
    canonicalEntityId: str | None
    cluster_uid: str | None
    object_uid: str | None


class AlertmanagerSourcesPayload(TypedDict, total=False):
    """Payload for the full Alertmanager source inventory."""

    sources: list[AlertmanagerSourcePayload]
    total_count: int
    tracked_count: int
    manual_count: int
    degraded_count: int
    missing_count: int
    discovery_timestamp: str | None
    cluster_context: str | None

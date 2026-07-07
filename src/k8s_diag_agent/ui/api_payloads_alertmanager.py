"""TypedDict payload definitions for Alertmanager contracts.

This module contains pure data contracts (TypedDict definitions) for Alertmanager
alert summaries and source inventory.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.

Extraction rationale:
    - Separating Alertmanager contracts makes the API boundary easier to audit.
    - Allows focused testing and documentation for Alertmanager payloads.

CANONICAL WIRE SCHEMAS:
    - k9b.alertmanager_sources.review_packet.v1 (AlertmanagerSourcesReviewPacketPayload)
    - k9b.alertmanager_source.debug_packet.v1 (AlertmanagerSourceDebugPacketPayload)
    - k9b.alertmanager_source.promotion_review.v1 (AlertmanagerSourcePromotionReviewPayload)

These TypedDicts mirror the canonical dataclasses in external_analysis modules:
    - alertmanager_sources_review_packet.py
    - alertmanager_source_debug_packet.py
    - alertmanager_source_promotion_review.py

BACKWARD COMPATIBILITY:
    - Some wire-level fields are aliased for UI compatibility.
    - Legacy aliases are explicitly documented as "UI compatibility alias".
    - Schema versions are frozen; breaking changes require a new version.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "ClusterAlertSummaryPayload",
    "AlertmanagerCompactPayload",
    "AlertmanagerSourceAliasPayload",
    "AlertmanagerSourcePayload",
    "AlertmanagerSourcesPayload",
    # Review packet payloads (canonical: k9b.alertmanager_sources.review_packet.v1)
    "AlertmanagerSourcesReviewPacketPayload",
    "AlertmanagerSourcesSummaryPayload",
    "AlertmanagerSourceReviewEntryPayload",
    "RuntimeIdentityPayload",
    "KubernetesIdentityPayload",
    "EndpointIdentityPayload",
    # Debug packet payloads (canonical: k9b.alertmanager_source.debug_packet.v1)
    "AlertmanagerSourceDebugPacketPayload",
    "HttpProbeResultPayload",
    "HttpProbeResultsPayload",
    "KubernetesProbeDataPayload",
    "DiscoveryReasonPayload",
    # Promotion review payloads (canonical: k9b.alertmanager_source.promotion_review.v1)
    "AlertmanagerSourcePromotionReviewPayload",
    "PromotionRiskPayload",
    "TrackedSourceSpecPayload",
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


class AlertmanagerSourceAliasPayload(TypedDict, total=False):
    """Payload for an Alertmanager source alias (tracked Kubernetes service alias)."""

    alias_name: str
    alias_namespace: str
    alias_endpoint: str
    discovery_method: str
    management_type: str


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
    # Discovered aliases: Kubernetes services that are aliases of this logical source
    # Used to preserve provenance when multiple services are collapsed into one source
    aliases: list[AlertmanagerSourceAliasPayload]


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


# =============================================================================
# Review packet payloads for "2 AlertManagers" debugging
# =============================================================================


class RuntimeIdentityPayload(TypedDict, total=False):
    """Runtime identity from Alertmanager /api/v2/status probe."""

    probe_attempted: bool
    ready: bool
    healthy: bool
    alertmanager_version: str | None
    cluster_status: str | None
    cluster_peer_count: int
    config_sha256: str | None
    receiver_count: int | None
    silence_count: int | None
    alert_group_count: int | None


class KubernetesIdentityPayload(TypedDict, total=False):
    """Kubernetes-level identity for the Alertmanager source."""

    service_uid: str | None
    service_type: str | None
    labels: dict[str, str]
    annotations_redacted: dict[str, str]
    selector: dict[str, str]
    ports: list[dict[str, object]]
    owner_references: list[dict[str, object]]


class EndpointIdentityPayload(TypedDict, total=False):
    """Endpoint-level identity for the Alertmanager source."""

    endpoint_uid: str | None
    addresses: list[str]
    not_ready_addresses: list[str]
    ports: list[dict[str, object]]


class DuplicateAnalysisPayload(TypedDict, total=False):
    """Analysis of whether this source is a duplicate of another."""

    is_duplicate: bool
    duplicate_of: str | None
    evidence: list[str]
    action: str  # collapse_as_aliases, keep_separate, requires_manual_review
    explanation: str


class AlertmanagerSourceReviewEntryPayload(TypedDict, total=False):
    """A single source entry in the review packet."""

    source_id: str
    name: str | None
    namespace: str | None
    endpoint: str
    origin: str
    state: str
    runtime: RuntimeIdentityPayload
    kubernetes: KubernetesIdentityPayload
    endpoint_info: EndpointIdentityPayload
    duplicate_analysis: DuplicateAnalysisPayload
    discovered_at: str | None


class AlertmanagerSourcesSummaryPayload(TypedDict, total=False):
    """Summary section of the review packet."""

    total_sources: int
    unique_logical_sources: int
    duplicate_count: int
    cluster_context: str
    discovery_run_id: str
    discovery_timestamp: str


class AlertmanagerSourcesReviewPacketPayload(TypedDict, total=False):
    """Payload for the Alertmanager sources review packet."""

    schema_version: str
    artifact_id: str
    generated_at: str
    run_id: str
    cluster_label: str
    summary: AlertmanagerSourcesSummaryPayload
    sources: list[AlertmanagerSourceReviewEntryPayload]


# =============================================================================
# Debug packet payloads for per-source debugging
# =============================================================================


class HttpProbeResultPayload(TypedDict, total=False):
    """Result of an HTTP probe to an Alertmanager endpoint."""

    url: str
    status_code: int | None
    latency_ms: float | None
    error: str | None


class HttpProbeResultsPayload(TypedDict, total=False):
    """Results from all HTTP probes to Alertmanager endpoints."""

    healthy: HttpProbeResultPayload | None
    ready: HttpProbeResultPayload | None
    status: HttpProbeResultPayload | None


class KubernetesProbeDataPayload(TypedDict, total=False):
    """Results from Kubernetes API probes for the source."""

    service: dict[str, object]
    endpoints: dict[str, object]
    endpoint_slices: list[dict[str, object]]
    pods: list[dict[str, object]]
    alertmanager_cr_matches: list[dict[str, object]]
    statefulset_matches: list[dict[str, object]]


class DiscoveryReasonPayload(TypedDict, total=False):
    """Why this source was discovered."""

    method: str  # crd, service_heuristic, manual
    matched_pattern: str | None
    owner_reference_kind: str | None
    owner_reference_name: str | None


class AlertmanagerSourceDebugPacketPayload(TypedDict, total=False):
    """Payload for the per-source debug packet."""

    schema_version: str
    artifact_id: str
    generated_at: str
    run_id: str
    cluster_label: str
    source_id: str
    name: str | None
    namespace: str | None
    endpoint: str
    origin: str
    state: str
    http_probes: HttpProbeResultsPayload
    kubernetes: KubernetesProbeDataPayload
    discovery_reason: DiscoveryReasonPayload


# =============================================================================
# Promotion review payloads
# =============================================================================


class PromotionRiskPayload(TypedDict, total=False):
    """Risk assessment for promotion."""

    risk_level: str  # low, medium, high
    duplicate_risk: str | None  # description of duplicate risk if any
    existing_manual_source: str | None  # source_id if duplicate exists


class TrackedSourceSpecPayload(TypedDict, total=False):
    """Spec of an existing tracked source that matches this one."""

    source_id: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str
    state: str


class AlertmanagerSourcePromotionReviewPayload(TypedDict, total=False):
    """Payload for the pre-promotion review packet."""

    schema_version: str
    artifact_id: str
    generated_at: str
    run_id: str
    cluster_label: str
    source_id: str
    name: str | None
    namespace: str | None
    endpoint: str
    promotion_target: str  # "manual"
    risk: PromotionRiskPayload
    tracked_source_if_duplicate: TrackedSourceSpecPayload | None

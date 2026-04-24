"""View models for Alertmanager UI layer (UI model module).

This module contains Alertmanager-related view model dataclasses extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Dependency direction: model_alertmanager.py -> model_primitives.py
model.py imports from model_alertmanager.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_str,
    _coerce_str_tuple,
)


@dataclass(frozen=True)
class ClusterAlertSummaryView:
    """Per-cluster alert summary for cluster-scoped UI panels."""
    cluster: str
    alert_count: int
    severity_counts: tuple[tuple[str, int], ...]
    state_counts: tuple[tuple[str, int], ...]
    top_alert_names: tuple[str, ...]
    affected_namespaces: tuple[str, ...]
    affected_services: tuple[str, ...]


@dataclass(frozen=True)
class AlertmanagerEvidenceReferenceView:
    """View model for an Alertmanager evidence reference in review enrichment."""
    cluster: str
    matched_dimensions: tuple[str, ...]
    reason: str
    used_for: str


@dataclass(frozen=True)
class AlertmanagerCompactView:
    """View model for Alertmanager compact context - run-scoped snapshot of alerts."""
    status: str
    alert_count: int
    severity_counts: tuple[tuple[str, int], ...]
    state_counts: tuple[tuple[str, int], ...]
    top_alert_names: tuple[str, ...]
    affected_namespaces: tuple[str, ...]
    affected_clusters: tuple[str, ...]
    affected_services: tuple[str, ...]
    truncated: bool
    captured_at: str
    # Per-cluster breakdown for cluster-scoped UI panels
    by_cluster: tuple[ClusterAlertSummaryView, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AlertmanagerProvenanceView:
    matched_dimensions: tuple[str, ...]
    matched_values: dict[str, tuple[str, ...]]
    applied_bonus: int
    base_bonus: int = 0
    severity_summary: dict[str, int] | None = None
    signal_status: str | None = None


@dataclass(frozen=True)
class AlertmanagerSourceView:
    """View model for a single Alertmanager source in the inventory."""
    source_id: str
    matching_key: str  # Stable key for cross-run deduplication (UI-derived fallback)
    # Canonical identity from discovery layer - the stable identity used for registry matching
    # This must match the identity used by the health loop for cross-run persistence
    canonical_identity: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str  # origin enum value as string
    state: str  # state enum value as string
    discovered_at: str | None
    verified_at: str | None
    last_check: str | None
    last_error: str | None
    verified_version: str | None
    confidence_hints: tuple[str, ...]
    # Deduplication provenance: all origins that contributed to this source
    merged_provenances: tuple[str, ...]  # list of origin enum values
    # Human-readable provenance for UI tooltip
    display_provenance: str  # e.g., "Alertmanager CRD, Prometheus Config, Service Heuristic"
    # Computed UI fields
    is_manual: bool
    is_tracking: bool  # auto-tracked or manual
    can_disable: bool  # can be disabled from auto-tracking
    can_promote: bool  # can be promoted to manual
    display_origin: str  # human-readable origin
    display_state: str  # human-readable state with color hint
    provenance_summary: str  # short provenance string for UI
    cluster_label: str | None  # Operator-facing cluster label for per-cluster UI filtering
    # Manual source mode: distinguishes operator-configured vs operator-promoted
    # Values: "operator-configured", "operator-promoted", or None (not manual or legacy)
    manual_source_mode: str | None
    # Canonical entity ID: deterministic hash from normalized defining facts for historical tracking
    # Same source facts => same canonicalEntityId (for cross-run historical continuity)
    # Different source facts => different canonicalEntityId
    canonical_entity_id: str | None
    # Identity anchors for cross-cluster disambiguation
    # cluster_uid: Cluster UID from kube-system namespace (optional)
    # object_uid: Native Kubernetes object UID (optional, highest confidence anchor)
    cluster_uid: str | None
    object_uid: str | None


@dataclass(frozen=True)
class AlertmanagerSourcesView:
    """View model for the full Alertmanager source inventory."""
    sources: tuple[AlertmanagerSourceView, ...]
    total_count: int
    tracked_count: int  # auto-tracked + manual
    manual_count: int
    degraded_count: int
    missing_count: int
    discovery_timestamp: str | None
    cluster_context: str | None


# Re-export primitives for convenience in builder helpers
from .model_primitives import _ORIGIN_LABELS, _STATE_LABELS  # noqa: E402


def _build_alertmanager_evidence_reference_view(
    raw: Mapping[str, object],
) -> AlertmanagerEvidenceReferenceView:
    """Build AlertmanagerEvidenceReferenceView from raw JSON data."""
    return AlertmanagerEvidenceReferenceView(
        cluster=_coerce_str(raw.get("cluster")),
        matched_dimensions=_coerce_str_tuple(
            raw.get("matchedDimensions") or raw.get("matched_dimensions")
        ),
        reason=_coerce_str(raw.get("reason")),
        used_for=_coerce_str(raw.get("usedFor") or raw.get("used_for")),
    )


def _build_alertmanager_provenance_view(
    raw: object | None,
) -> AlertmanagerProvenanceView | None:
    """Build AlertmanagerProvenanceView from raw JSON data (snake_case keys from planner)."""
    if not isinstance(raw, Mapping):
        return None
    matched_dimensions_raw = raw.get("matchedDimensions") or raw.get("matched_dimensions") or ()
    matched_dimensions: tuple[str, ...] = ()
    if isinstance(matched_dimensions_raw, Sequence) and not isinstance(
        matched_dimensions_raw, str | bytes
    ):
        matched_dimensions = tuple(str(d) for d in matched_dimensions_raw)

    matched_values_raw = raw.get("matchedValues") or raw.get("matched_values") or {}
    matched_values: dict[str, tuple[str, ...]] = {}
    if isinstance(matched_values_raw, Mapping):
        for dim, vals in matched_values_raw.items():
            if isinstance(vals, Sequence) and not isinstance(vals, str | bytes):
                matched_values[str(dim)] = tuple(str(v) for v in vals)
            elif vals:
                matched_values[str(dim)] = (str(vals),)

    severity_summary_raw = raw.get("severitySummary") or raw.get("severity_summary")
    severity_summary: dict[str, int] | None = None
    if isinstance(severity_summary_raw, Mapping):
        severity_summary = {str(k): int(v) for k, v in severity_summary_raw.items()}

    return AlertmanagerProvenanceView(
        matched_dimensions=matched_dimensions,
        matched_values=matched_values,
        applied_bonus=_coerce_int(raw.get("appliedBonus") or raw.get("applied_bonus")),
        base_bonus=_coerce_int(raw.get("baseBonus") or raw.get("base_bonus") or 0),
        severity_summary=severity_summary,
        signal_status=_coerce_optional_str(raw.get("signalStatus") or raw.get("signal_status")),
    )


def _build_alertmanager_compact_view(
    raw: object | None,
) -> AlertmanagerCompactView | None:
    """Build AlertmanagerCompactView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    severity_raw = raw.get("severity_counts")
    severity_counts: tuple[tuple[str, int], ...] = ()
    if isinstance(severity_raw, Mapping):
        severity_counts = tuple((str(k), int(v)) for k, v in severity_raw.items())
    state_raw = raw.get("state_counts")
    state_counts: tuple[tuple[str, int], ...] = ()
    if isinstance(state_raw, Mapping):
        state_counts = tuple((str(k), int(v)) for k, v in state_raw.items())

    # Build per-cluster summaries
    by_cluster: tuple[ClusterAlertSummaryView, ...] = ()
    by_cluster_raw = raw.get("by_cluster")
    if isinstance(by_cluster_raw, Sequence) and not isinstance(by_cluster_raw, str | bytes):
        cluster_summaries: list[ClusterAlertSummaryView] = []
        for entry in by_cluster_raw:
            if not isinstance(entry, Mapping):
                continue
            entry_severity_raw = entry.get("severity_counts")
            entry_severity: tuple[tuple[str, int], ...] = ()
            if isinstance(entry_severity_raw, Mapping):
                entry_severity = tuple((str(k), int(v)) for k, v in entry_severity_raw.items())
            entry_state_raw = entry.get("state_counts")
            entry_state: tuple[tuple[str, int], ...] = ()
            if isinstance(entry_state_raw, Mapping):
                entry_state = tuple((str(k), int(v)) for k, v in entry_state_raw.items())
            cluster_summaries.append(
                ClusterAlertSummaryView(
                    cluster=_coerce_str(entry.get("cluster")),
                    alert_count=_coerce_int(entry.get("alert_count")),
                    severity_counts=entry_severity,
                    state_counts=entry_state,
                    top_alert_names=_coerce_str_tuple(entry.get("top_alert_names")),
                    affected_namespaces=_coerce_str_tuple(entry.get("affected_namespaces")),
                    affected_services=_coerce_str_tuple(entry.get("affected_services")),
                )
            )
        by_cluster = tuple(cluster_summaries)

    return AlertmanagerCompactView(
        status=_coerce_str(raw.get("status")),
        alert_count=_coerce_int(raw.get("alert_count")),
        severity_counts=severity_counts,
        state_counts=state_counts,
        top_alert_names=_coerce_str_tuple(raw.get("top_alert_names")),
        affected_namespaces=_coerce_str_tuple(raw.get("affected_namespaces")),
        affected_clusters=_coerce_str_tuple(raw.get("affected_clusters")),
        affected_services=_coerce_str_tuple(raw.get("affected_services")),
        truncated=bool(raw.get("truncated")),
        captured_at=_coerce_str(raw.get("captured_at")),
        by_cluster=by_cluster,
    )


def _build_alertmanager_sources_view(
    raw: object | None,
) -> AlertmanagerSourcesView | None:
    """Build AlertmanagerSourcesView from raw JSON data (alertmanager_sources field).

    This function applies effective state overrides from operator actions
    (promote/disable) when computing UI fields like is_manual, is_tracking,
    can_disable, can_promote, and display_state.
    """
    if not isinstance(raw, Mapping):
        return None

    sources_raw = raw.get("sources") or ()
    sources: list[AlertmanagerSourceView] = []
    for src in sources_raw:
        if not isinstance(src, Mapping):
            continue
        origin = _coerce_str(src.get("origin", "service-heuristic"))
        state = _coerce_str(src.get("state", "discovered"))

        # Apply effective state from operator override (promote/disable)
        # This overrides the discovery-based state
        effective_state = _coerce_optional_str(src.get("effective_state"))
        if effective_state:
            state = effective_state

        # Compute manual_source_mode - prefer explicit field, then derive from origin
        manual_source_mode = _coerce_optional_str(src.get("manual_source_mode"))

        # Compute UI fields based on (possibly overridden) state and manual_source_mode
        is_manual = (
            state == "manual" or manual_source_mode in ("operator-configured", "operator-promoted")
        )
        is_tracking = state in ("auto-tracked", "manual")
        # Sources with effective_state "disabled" cannot be disabled again
        # Sources that are already manual cannot be promoted
        can_disable = not is_manual and state == "auto-tracked"
        can_promote = not is_manual and state in ("auto-tracked", "discovered")
        display_origin = _ORIGIN_LABELS.get(origin, origin)
        display_state = _STATE_LABELS.get(state, state)

        # Build provenance summary from confidence_hints
        hints = _coerce_str_tuple(src.get("confidence_hints"))
        provenance_summary = "; ".join(hints) if hints else "-"

        # Build merged_provenances for deduplication display
        merged_provenances_raw = src.get("merged_provenances")
        if isinstance(merged_provenances_raw, Sequence) and not isinstance(
            merged_provenances_raw, str | bytes
        ):
            merged_provenances = tuple(str(p) for p in merged_provenances_raw)
        else:
            merged_provenances = (origin,)

        # Build human-readable display_provenance
        display_provenance_raw = src.get("display_provenance")
        if display_provenance_raw:
            display_provenance = _coerce_str(display_provenance_raw)
        else:
            # Derive from merged_provenances if not explicitly set
            labels = [_ORIGIN_LABELS.get(p, p) for p in merged_provenances]
            display_provenance = ", ".join(labels) if labels else display_origin

        # Build matching_key for cross-run deduplication
        # Use explicit matching_key if provided, otherwise derive from endpoint
        matching_key = _coerce_optional_str(src.get("matching_key"))
        if not matching_key:
            # Derive from endpoint as fallback
            endpoint_val = _coerce_str(src.get("endpoint"))
            matching_key = endpoint_val

        # Build canonical_identity from discovery layer - the stable identity used for registry matching
        # This must match the identity used by the health loop for cross-run persistence
        canonical_identity = _coerce_optional_str(src.get("canonical_identity"))
        if not canonical_identity:
            # Fallback to matching_key if canonical_identity not present in artifact
            # (for backwards compatibility with older artifacts)
            canonical_identity = matching_key

        sources.append(
            AlertmanagerSourceView(
                source_id=_coerce_str(src.get("source_id")),
                matching_key=matching_key,
                canonical_identity=canonical_identity,
                endpoint=_coerce_str(src.get("endpoint")),
                namespace=_coerce_optional_str(src.get("namespace")),
                name=_coerce_optional_str(src.get("name")),
                origin=origin,
                state=state,
                discovered_at=_coerce_optional_str(src.get("discovered_at")),
                verified_at=_coerce_optional_str(src.get("verified_at")),
                last_check=_coerce_optional_str(src.get("last_check")),
                last_error=_coerce_optional_str(src.get("last_error")),
                verified_version=_coerce_optional_str(src.get("verified_version")),
                confidence_hints=hints,
                merged_provenances=merged_provenances,
                display_provenance=display_provenance,
                is_manual=is_manual,
                is_tracking=is_tracking,
                can_disable=can_disable,
                can_promote=can_promote,
                display_origin=display_origin,
                display_state=display_state,
                provenance_summary=provenance_summary,
                cluster_label=_coerce_optional_str(src.get("cluster_label")),
                manual_source_mode=manual_source_mode,
                # Identity fields for cross-run historical tracking
                canonical_entity_id=_coerce_optional_str(src.get("canonicalEntityId")),
                cluster_uid=_coerce_optional_str(src.get("cluster_uid")),
                object_uid=_coerce_optional_str(src.get("object_uid")),
            )
        )

    # Count by category
    manual_count = sum(1 for s in sources if s.is_manual)
    tracked_count = sum(1 for s in sources if s.is_tracking)
    degraded_count = sum(1 for s in sources if s.state == "degraded")
    missing_count = sum(1 for s in sources if s.state == "missing")

    return AlertmanagerSourcesView(
        sources=tuple(sources),
        total_count=len(sources),
        tracked_count=tracked_count,
        manual_count=manual_count,
        degraded_count=degraded_count,
        missing_count=missing_count,
        discovery_timestamp=_coerce_optional_str(raw.get("discovery_timestamp")),
        cluster_context=_coerce_optional_str(raw.get("cluster_context")),
    )

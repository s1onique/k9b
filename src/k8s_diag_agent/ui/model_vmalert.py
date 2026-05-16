"""View models for vmalert UI layer (UI model module).

This module contains vmalert-related view model dataclasses extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Dependency direction: model_vmalert.py -> model_primitives.py
model.py imports from model_vmalert.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_primitives import (
    _coerce_optional_str,
    _coerce_str,
    _coerce_str_tuple,
)

# Origin labels for display
_ORIGIN_LABELS: dict[str, str] = {
    "manual": "Manual",
    "vmalert-crd": "VMAlert CRD",
    "service-heuristic": "Service Heuristic",
}

# State labels for display
_STATE_LABELS: dict[str, str] = {
    "discovered": "Discovered",
    "discovered-but-unverified": "Discovered (Unverified)",
    "auto-tracked": "Auto-tracked",
    "degraded": "Degraded",
    "missing": "Missing",
    "manual": "Manual",
}


@dataclass(frozen=True)
class VmalertSourceView:
    """View model for a single vmalert source in the inventory."""
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
    display_provenance: str  # e.g., "VMAlert CRD, Service Heuristic"
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
class VmalertSourcesView:
    """View model for the full vmalert source inventory."""
    sources: tuple[VmalertSourceView, ...]
    total_count: int
    source_count: int
    discovered_count: int
    discovered_but_unverified_count: int
    auto_tracked_count: int
    manual_count: int
    discovery_timestamp: str | None
    cluster_context: str | None


def _build_vmalert_sources_view(
    raw: object | None,
) -> VmalertSourcesView | None:
    """Build VmalertSourcesView from raw JSON data (vmalert_sources field).

    This function applies effective state overrides from operator actions
    (promote/disable) when computing UI fields like is_manual, is_tracking,
    can_disable, can_promote, and display_state.
    """
    if not isinstance(raw, Mapping):
        return None

    sources_raw = raw.get("sources") or ()
    sources: list[VmalertSourceView] = []
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
        can_promote = not is_manual and state in ("auto-tracked", "discovered", "discovered-but-unverified")
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
            VmalertSourceView(
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
    auto_tracked_count = sum(1 for s in sources if s.state == "auto-tracked")
    discovered_count = sum(1 for s in sources if s.state == "discovered")
    discovered_but_unverified_count = sum(1 for s in sources if s.state == "discovered-but-unverified")

    # source_count is total sources (for backward compatibility)
    source_count = len(sources)

    return VmalertSourcesView(
        sources=tuple(sources),
        total_count=len(sources),
        source_count=source_count,
        discovered_count=discovered_count,
        discovered_but_unverified_count=discovered_but_unverified_count,
        auto_tracked_count=auto_tracked_count,
        manual_count=manual_count,
        discovery_timestamp=_coerce_optional_str(raw.get("discovery_timestamp")),
        cluster_context=_coerce_optional_str(raw.get("cluster_context")),
    )

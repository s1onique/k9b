"""Alertmanager source models and contracts.

This module contains the core data models for Alertmanager discovery:
- AlertmanagerSourceOrigin, AlertmanagerSourceState, AlertmanagerSourceMode (enums)
- AlertmanagerSource: core source representation with identity methods
- AlertmanagerSourceInventory: source collection with merge semantics
- DiscoveryResult: result wrapper for discovery strategies

Key identity model:
- canonical_entity_id: Deterministic hash from normalized defining facts
- operator_intent_key: For durable operator actions (promote/disable)
- canonical_identity: namespace/name string for registry matching
- Display fields: cluster_label, cluster_context, endpoint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..identity.artifact import new_artifact_id

# --- Enums ---


class AlertmanagerSourceOrigin(StrEnum):
    """Origin of an Alertmanager source.

    Priority is explicit via _ORIGIN_PRIORITY map (not string value order).
    """

    MANUAL = "manual"
    ALERTMANAGER_CRD = "alertmanager-crd"
    # NOTE: prometheus-runtime referred to actual Prometheus /api/v1/alertmanagers
    # which requires Prometheus server access. Using CRD config inference instead.
    PROMETHEUS_CRD_CONFIG = "prometheus-crd-config"
    SERVICE_HEURISTIC = "service-heuristic"


# Explicit priority map: lower number = higher priority
# Used by inventory merge to determine precedence when same source_id exists
_ORIGIN_PRIORITY: dict[AlertmanagerSourceOrigin, int] = {
    AlertmanagerSourceOrigin.MANUAL: 0,  # Highest - authoritative, never overwritten
    AlertmanagerSourceOrigin.ALERTMANAGER_CRD: 10,  # CRD is canonical declaration
    AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG: 20,  # CRD config inference
    AlertmanagerSourceOrigin.SERVICE_HEURISTIC: 30,  # Lowest confidence fallback
}


def _normalize_endpoint_for_identity(endpoint: str) -> str:
    """Strip scheme and trailing slash to get a canonical identity key.

    e.g., 'http://alertmanager-main.monitoring:9093/' -> 'alertmanager-main.monitoring:9093'
    This allows deduplication across discovery strategies that generate
    different source_id prefixes (crd:, prom-crd-config:, service:, pod:).
    """
    normalized = endpoint.rstrip('/')
    # Strip scheme if present
    if normalized.startswith('http://'):
        normalized = normalized[7:]
    elif normalized.startswith('https://'):
        normalized = normalized[8:]
    return normalized


class AlertmanagerSourceState(StrEnum):
    """Current state of an Alertmanager source."""

    DISCOVERED = "discovered"  # Found but not yet verified
    AUTO_TRACKED = "auto-tracked"  # Verified and being tracked
    DEGRADED = "degraded"  # Verification failed or became unavailable
    MISSING = "missing"  # Was tracked but no longer available
    MANUAL = "manual"  # User-configured (authoritative)


class AlertmanagerSourceMode(StrEnum):
    """How a source entered manual tracking.

    This field preserves the distinction between:
    - operator-configured: user typed endpoint manually in config
    - operator-promoted: user promoted a discovered source to manual

    The origin field preserves the discovery mechanism (e.g., alertmanager-crd).
    """

    NOT_MANUAL = "not-manual"  # Source is auto-discovered, not in manual tracking
    OPERATOR_CONFIGURED = "operator-configured"  # User typed endpoint manually
    OPERATOR_PROMOTED = "operator-promoted"  # User promoted from auto-discovery


# --- Core Models ---


@dataclass(frozen=True)
class AlertmanagerSource:
    """A discovered or configured Alertmanager source with explicit provenance."""

    source_id: str  # Stable identity (typically namespace/name)
    endpoint: str  # Full URL to the Alertmanager API
    namespace: str | None = None  # Kubernetes namespace (if applicable)
    name: str | None = None  # Kubernetes resource name (if applicable)
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.SERVICE_HEURISTIC
    state: AlertmanagerSourceState = AlertmanagerSourceState.DISCOVERED
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified_at: datetime | None = None
    last_check: datetime | None = None
    last_error: str | None = None
    verified_version: str | None = None  # Alertmanager version from /api/v2/status
    confidence_hints: tuple[str, ...] = field(default_factory=tuple)  # e.g., (from-crd, has-service)
    merged_provenances: tuple[AlertmanagerSourceOrigin, ...] = field(default_factory=tuple)  # All contributing origins for UI
    cluster_label: str | None = None  # Operator-facing cluster label for per-cluster UI filtering
    cluster_context: str | None = None  # Kubernetes context used for discovery (required for registry matching)
    # Identity anchors for canonical entity ID (cross-cluster disambiguation)
    # cluster_uid: Cluster UID from kube-system namespace (optional but preferred when available)
    # object_uid: Native Kubernetes object UID (optional, highest confidence anchor)
    # These are included in canonical_entity_id when available, excluded when not
    cluster_uid: str | None = None
    object_uid: str | None = None
    # Manual provenance: distinguishes operator-configured vs operator-promoted sources
    # Not serialized for discovered sources (defaults to NOT_MANUAL)
    manual_source_mode: AlertmanagerSourceMode = AlertmanagerSourceMode.NOT_MANUAL

    def __post_init__(self) -> None:
        # Ensure endpoint has no trailing slash for consistency
        object.__setattr__(self, 'endpoint', self.endpoint.rstrip('/'))
        # Ensure merged_provenances includes current origin if not already present
        if self.origin not in self.merged_provenances:
            object.__setattr__(self, 'merged_provenances', self.merged_provenances + (self.origin,))

    @property
    def canonical_identity(self) -> str:
        """Canonical identity for deduplication across strategies.

        Uses namespace/name as the canonical identity when available (all origins).
        Falls back to normalized endpoint only when namespace/name is not available.

        This allows sources discovered by different strategies (CRD, Prometheus config,
        service heuristic) to merge when they have matching namespace+name.
        """
        # Use namespace/name for canonical identity when available (all origins)
        if self.namespace and self.name:
            return f"{self.namespace}/{self.name}"

        # Fallback to normalized endpoint when namespace/name not available
        return _normalize_endpoint_for_identity(self.endpoint)

    @property
    def canonical_entity_id(self) -> str:
        """Canonical historical identity - deterministic hash from normalized defining facts.

        This is the canonical_entity_id for historical tracking across runs.
        Same source facts => same canonical_entity_id.
        Different source facts => different canonical_entity_id.

        Uses the identity module helpers to ensure consistent construction.
        Display-only fields (cluster_label, cluster_context) do NOT affect this ID.

        Mixed-discovery policy:
        - cluster_uid and object_uid are OPTIONAL identity anchors
        - When available, they are INCLUDED in the hash (changes the ID)
        - When not available, they are EXCLUDED (based on namespace/name/origin/endpoint only)
        - IMPORTANT: The same Alertmanager may have DIFFERENT canonical_entity_id
          depending on whether cluster_uid/object_uid were captured in that run
        - For rediscovery continuity, prefer sources that have consistent anchor capture

        Note: This is distinct from operator_intent_key which is used for durable
        operator actions (promote/disable) and prefers cluster_label for stability.
        """
        # Import here to avoid circular import at module level
        from ..identity.alertmanager_source import build_alertmanager_canonical_entity_id

        return build_alertmanager_canonical_entity_id(
            namespace=self.namespace,
            name=self.name,
            origin=self.origin.value if self.origin else None,
            endpoint=self.endpoint,
            cluster_uid=self.cluster_uid,  # None if not set - optional anchor
            object_uid=self.object_uid,  # None if not set - optional anchor
        )

    @property
    def operator_intent_key(self) -> str:
        """Operator-intent persistence key for durable actions.

        This key is used ONLY for durable operator actions (promote/disable)
        and override persistence. It is NOT the canonical historical identity.

        Design rationale:
        - cluster_label is preferred over cluster_context because it is
          operator-controlled and stable across kubeconfig edits/renames
        - cluster_context can change with kubeconfig edits, aliases, or renames

        Returns:
            Operator-intent key string (format: "cluster_key:source_identity")
        """
        # Import here to avoid circular import at module level
        from ..identity.alertmanager_source import build_alertmanager_operator_intent_key

        return build_alertmanager_operator_intent_key(
            cluster_label=self.cluster_label,
            cluster_context=self.cluster_context,
            namespace=self.namespace,
            name=self.name,
            endpoint=self.endpoint,
        )

    @property
    def identity_key(self) -> str:
        """Legacy identity key - prefer canonical_identity for deduplication."""
        return self.source_id

    @property
    def display_provenance(self) -> str:
        """Human-readable provenance showing all merged origins.

        Always returns human-readable labels, never raw enum values.
        """
        origins = [p.value for p in self.merged_provenances]
        # Map to human-readable labels
        labels = {
            'manual': 'Manual',
            'alertmanager-crd': 'Alertmanager CRD',
            'prometheus-crd-config': 'Prometheus Config',
            'service-heuristic': 'Service Heuristic',
        }
        return ', '.join(labels.get(o, o) for o in origins)

    def to_dict(self) -> dict[str, Any]:
        result = {
            'source_id': self.source_id,
            'endpoint': self.endpoint,
            'namespace': self.namespace,
            'name': self.name,
            'origin': self.origin.value,
            'state': self.state.value,
            'discovered_at': self.discovered_at.isoformat(),
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_error': self.last_error,
            'verified_version': self.verified_version,
            'confidence_hints': list(self.confidence_hints),
            'merged_provenances': [p.value for p in self.merged_provenances],
            'display_provenance': self.display_provenance,
            'cluster_label': self.cluster_label,
            'cluster_context': self.cluster_context,
            # Include canonical_identity for cross-run registry matching
            # This is the stable identity (namespace/name) used by the health loop registry
            'canonical_identity': self.canonical_identity,
            # Include canonicalEntityId for historical tracking across runs
            # This is the deterministic hash from normalized defining facts
            'canonicalEntityId': self.canonical_entity_id,
        }
        # Include cluster_uid and object_uid when available (optional anchors)
        if self.cluster_uid is not None:
            result['cluster_uid'] = self.cluster_uid
        if self.object_uid is not None:
            result['object_uid'] = self.object_uid
        # Include manual_source_mode only when not NOT_MANUAL (backward compatibility)
        if self.manual_source_mode != AlertmanagerSourceMode.NOT_MANUAL:
            result['manual_source_mode'] = self.manual_source_mode.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSource:
        """Reconstruct source from serialized dict."""
        merged_raw = data.get('merged_provenances')
        merged_provenances: tuple[AlertmanagerSourceOrigin, ...] = ()
        if merged_raw:
            merged_provenances = tuple(
                AlertmanagerSourceOrigin(v) if isinstance(v, str) else v
                for v in merged_raw
            )
        # Parse manual_source_mode if present (backward compatibility)
        manual_source_mode_raw = data.get('manual_source_mode')
        if manual_source_mode_raw:
            manual_source_mode = AlertmanagerSourceMode(manual_source_mode_raw)
        else:
            manual_source_mode = AlertmanagerSourceMode.NOT_MANUAL
        return cls(
            source_id=str(data['source_id']),
            endpoint=str(data['endpoint']),
            namespace=data.get('namespace'),
            name=data.get('name'),
            origin=AlertmanagerSourceOrigin(data.get('origin', 'service-heuristic')),
            state=AlertmanagerSourceState(data.get('state', 'discovered')),
            discovered_at=_parse_datetime(data.get('discovered_at')),
            verified_at=_parse_datetime(data.get('verified_at')),
            last_check=_parse_datetime(data.get('last_check')),
            last_error=data.get('last_error'),
            verified_version=data.get('verified_version'),
            confidence_hints=tuple(data.get('confidence_hints', [])),
            merged_provenances=merged_provenances,
            cluster_label=data.get('cluster_label'),
            cluster_context=data.get('cluster_context'),
            # Parse optional identity anchors (may not be present in older artifacts)
            cluster_uid=data.get('cluster_uid'),
            object_uid=data.get('object_uid'),
            manual_source_mode=manual_source_mode,
        )


@dataclass
class AlertmanagerSourceInventory:
    """Collection of Alertmanager sources with merge semantics.

    Manual sources take precedence over discovered ones. When the same
    source_id exists with different origins, manual wins.
    """

    sources: dict[str, AlertmanagerSource] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cluster_context: str | None = None  # Kubernetes context used for discovery
    # Immutable artifact instance identity (UUIDv7)
    # Optional for backward compatibility - None for legacy artifacts, generated for new
    artifact_id: str | None = field(default_factory=new_artifact_id)

    def add_source(self, source: AlertmanagerSource) -> None:
        """Add a source, respecting manual precedence.

        Manual sources are authoritative and cannot be overwritten by
        discovered sources with the same identity.
        """
        existing = self.sources.get(source.identity_key)

        if existing is None:
            # No existing source, add it
            self.sources[source.identity_key] = source
            return

        # Apply precedence rules:
        # 1. Manual always wins
        # 2. Same origin updates state if more recent
        # 3. Higher confidence origin wins for non-manual

        if existing.origin == AlertmanagerSourceOrigin.MANUAL:
            # Manual is authoritative, don't overwrite
            return

        if source.origin == AlertmanagerSourceOrigin.MANUAL:
            # New source is manual, replace
            self.sources[source.identity_key] = source
            return

        # Both are discovered, prefer higher priority origin (lower number = higher priority)
        if _ORIGIN_PRIORITY[source.origin] < _ORIGIN_PRIORITY[existing.origin]:
            self.sources[source.identity_key] = source
        elif source.origin == existing.origin:
            # Same origin, prefer more verified state
            if source.state == AlertmanagerSourceState.AUTO_TRACKED:
                self.sources[source.identity_key] = source

    def get_by_origin(self, origin: AlertmanagerSourceOrigin) -> tuple[AlertmanagerSource, ...]:
        """Get all sources with a specific origin."""
        return tuple(s for s in self.sources.values() if s.origin == origin)

    def get_by_state(self, state: AlertmanagerSourceState) -> tuple[AlertmanagerSource, ...]:
        """Get all sources with a specific state."""
        return tuple(s for s in self.sources.values() if s.state == state)

    def get_auto_tracked(self) -> tuple[AlertmanagerSource, ...]:
        """Get all sources that are being actively tracked."""
        return tuple(s for s in self.sources.values() if s.state in (AlertmanagerSourceState.AUTO_TRACKED, AlertmanagerSourceState.MANUAL))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [s.to_dict() for s in self.sources.values()],
            "discovered_at": self.discovered_at.isoformat(),
            "cluster_context": self.cluster_context,
            "source_count": len(self.sources),
            "artifact_id": self.artifact_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourceInventory:
        """Reconstruct inventory from serialized dict."""
        sources = {s["source_id"]: AlertmanagerSource.from_dict(s) for s in data.get("sources", [])}
        # artifact_id is optional for backward compatibility
        # Legacy artifacts without artifact_id will have None
        artifact_id: str | None = None
        if data.get("artifact_id"):
            artifact_id = str(data["artifact_id"])
        return cls(
            sources=sources,
            discovered_at=_parse_datetime(data.get("discovered_at")),
            cluster_context=data.get("cluster_context"),
            artifact_id=artifact_id,
        )


@dataclass(frozen=True)
class DiscoveryResult:
    """Result from a discovery strategy."""

    sources: tuple[AlertmanagerSource, ...]
    strategy: str  # Name of the strategy used
    errors: tuple[str, ...] = field(default_factory=tuple)


# --- Utility Functions ---


def _parse_datetime(value: str | None) -> datetime:
    """Parse ISO format datetime string to timezone-aware UTC datetime.

    Uses centralized datetime_utils to ensure all parsed datetimes
    are timezone-aware UTC for safe comparison operations.
    """
    if not value:
        return datetime.now(UTC)
    try:
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return datetime.now(UTC)
    # Ensure the result is timezone-aware UTC
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
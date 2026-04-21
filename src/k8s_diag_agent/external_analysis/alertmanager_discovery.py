"""Alertmanager auto-discovery for local installations.

This module discovers Alertmanager instances running in the cluster through multiple
strategies, verifies their health, and manages a source inventory with explicit
provenance tracking.

Discovery strategies (in priority order):
1. monitoring.coreos.com/v1 Alertmanager CRDs (high confidence)
2. Prometheus CRD alertmanagers configuration (medium confidence)
3. Service/pod heuristics (low confidence, fallback only)

Key invariants:
- Manual sources are authoritative and never overwritten by discovered sources
- Candidates must pass /-/healthy and /-/ready verification before auto-tracking
- All sources track explicit origin and state for UI provenance
- Discovery queries all namespaces using kubectl -A flag

Identity model:
- canonical_entity_id: Deterministic hash from normalized defining facts (namespace, name, origin, cluster_uid, etc.)
- operator_intent_key: For durable operator actions (promote/disable) - prefers cluster_label over cluster_context
- canonical_identity: namespace/name string for human-readable registry matching (distinct from canonical_entity_id)
- Display fields: cluster_label, cluster_context, endpoint - never sole identity anchor
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..identity.artifact import new_artifact_id

# Module logger for debug output
_logger = logging.getLogger(__name__)


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
    '''Strip scheme and trailing slash to get a canonical identity key.
    
    e.g., 'http://alertmanager-main.monitoring:9093/' -> 'alertmanager-main.monitoring:9093'
    This allows deduplication across discovery strategies that generate
    different source_id prefixes (crd:, prom-crd-config:, service:, pod:).
    '''
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
        '''Canonical identity for deduplication across strategies.
        
        Uses namespace/name as the canonical identity when available (all origins).
        Falls back to normalized endpoint only when namespace/name is not available.
        
        This allows sources discovered by different strategies (CRD, Prometheus config,
        service heuristic) to merge when they have matching namespace+name.
        '''
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
        '''Legacy identity key - prefer canonical_identity for deduplication.'''
        return self.source_id
    
    @property
    def display_provenance(self) -> str:
        '''Human-readable provenance showing all merged origins.
        
        Always returns human-readable labels, never raw enum values.
        '''
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
        '''Reconstruct source from serialized dict.'''
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
        '''Add a source, respecting manual precedence.

        Manual sources are authoritative and cannot be overwritten by
        discovered sources with the same identity.
        '''
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
        '''Get all sources with a specific origin.'''
        return tuple(s for s in self.sources.values() if s.origin == origin)

    def get_by_state(self, state: AlertmanagerSourceState) -> tuple[AlertmanagerSource, ...]:
        '''Get all sources with a specific state.'''
        return tuple(s for s in self.sources.values() if s.state == state)

    def get_auto_tracked(self) -> tuple[AlertmanagerSource, ...]:
        '''Get all sources that are being actively tracked.'''
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
        '''Reconstruct inventory from serialized dict.'''
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


# --- Discovery Strategy Interfaces ---


@dataclass(frozen=True)
class DiscoveryResult:
    """Result from a discovery strategy."""

    sources: tuple[AlertmanagerSource, ...]
    strategy: str  # Name of the strategy used
    errors: tuple[str, ...] = field(default_factory=tuple)


class DiscoveryStrategy:
    """Base class for Alertmanager discovery strategies."""

    name: str = "base"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Discover Alertmanager sources.

        Args:
            context: Kubernetes context to use for discovery
            cluster_uid: Canonical cluster identity for cross-cluster disambiguation

        Returns:
            DiscoveryResult with found sources and any errors
        """
        raise NotImplementedError


class CRDDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via monitoring.coreos.com/v1 Alertmanager CRDs.

    This is the highest-confidence discovery method as it uses the official
    Kubernetes API for Alertmanager resources. Uses -A flag to search all namespaces.
    """

    name = "alertmanager-crd"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Query Alertmanager CRDs using kubectl.

        Uses `kubectl get alertmanagers -A` to find all Alertmanager resources
        in all namespaces, then resolves their service endpoints.

        The -A flag is required because kube contexts may default to namespace
        'default' while Alertmanager resources typically live in 'monitoring'.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            # Use -A to search ALL namespaces (required for cross-namespace discovery)
            cmd = ["kubectl", "get", "alertmanagers", "-A", "-o", "json"]
            if context:
                cmd.extend(["--context", context])

            _logger.debug(
                "Alertmanager CRD discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # CRD may not be installed or kubectl may not be available
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    # CRD not present, return empty
                    _logger.debug(
                        "Alertmanager CRD discovery: no Alertmanager CRDs found in any namespace",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl failed: {result.stderr[:200]}")
                _logger.warning(
                    "Alertmanager CRD discovery failed: %s",
                    errors[-1],
                )
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Alertmanager CRD discovery: found %d Alertmanager CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_crd_item(item, context, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Alertmanager CRD discovery: found source %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get alertmanagers timed out")
            _logger.warning("Alertmanager CRD discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for Alertmanager CRD discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse Alertmanager CRD discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_crd_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse an Alertmanager CRD item into a source."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        if not name:
            return None

        # Capture native Kubernetes object UID (highest confidence identity anchor)
        object_uid: str | None = metadata.get("uid")

        # Build the service URL - Alertmanager is typically on port 9093
        # For in-cluster access, we construct the service DNS name
        endpoint = f"http://alertmanager-operated.{namespace}:9093"  # conventional for Prometheus Operator

        source_id = f"crd:{namespace}/{name}"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=("from-crd", f"namespace={namespace}"),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


class PrometheusCRDConfigDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via Prometheus CRD alertmanagers configuration.

    This method looks for Prometheus instances that reference Alertmanagers
    in their alerting.alertmanagers spec. Lower confidence than direct CRD
    as it relies on Prometheus configuration rather than direct inspection.
    Uses -A flag to search all namespaces.
    """

    name = "prometheus-crd-config"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Look for Prometheus resources and their Alertmanager configurations.

        Uses `kubectl get prometheuses -A` to search all namespaces.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        try:
            # Use -A to search ALL namespaces
            cmd = ["kubectl", "get", "prometheuses", "-A", "-o", "json"]
            if context:
                cmd.extend(["--context", context])

            _logger.debug(
                "Prometheus CRD config discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Prometheus CRD may not be installed
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug(
                        "Prometheus CRD config discovery: no Prometheus CRDs found",
                    )
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl prometheuses failed: {result.stderr[:200]}")
                _logger.warning(
                    "Prometheus CRD config discovery failed: %s",
                    errors[-1],
                )
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Prometheus CRD config discovery: found %d Prometheus CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_prometheus_item(item, context, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Prometheus CRD config discovery: found Alertmanager reference %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get prometheuses timed out")
            _logger.warning("Prometheus CRD config discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for Prometheus CRD config discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse Prometheus CRD config discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_prometheus_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a Prometheus CRD item to extract Alertmanager info."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        spec = item.get("spec", {})

        # Look for alerting configuration
        alerting = spec.get("alerting", {})
        alertmanagers = alerting.get("alertmanagers", [])

        for am in alertmanagers:
            # Prometheus Operator alertmanagers typically point to the operated service
            namespace = am.get("namespace", namespace)
            name = am.get("name", "alertmanager-main")

            source_id = f"prom-crd-config:{namespace}/{name}"
            endpoint = f"http://alertmanager-operated.{namespace}:9093"

            return AlertmanagerSource(
                source_id=source_id,
                endpoint=endpoint,
                namespace=namespace,
                name=name,
                origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
                state=AlertmanagerSourceState.DISCOVERED,
                confidence_hints=("from-prometheus-crd-config",),
                cluster_uid=cluster_uid,
            )

        return None


class ServiceHeuristicDiscoveryStrategy(DiscoveryStrategy):
    """Discover Alertmanagers via service/pod heuristics.

    Lowest confidence method - looks for conventional service patterns
    and port configurations. Only used as fallback when CRD and Prometheus
    discovery methods fail or return empty results. Uses -A flag to search all namespaces.
    """

    name = "service-heuristic"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Search for Alertmanager-like services by name pattern.

        Uses `kubectl get svc -A` and `kubectl get pods -A -l app=alertmanager`
        to search all namespaces. This is required because kube contexts may
        default to namespace 'default' while Alertmanager resources typically
        live in 'monitoring'.
        """
        import subprocess

        sources: list[AlertmanagerSource] = []
        errors: list[str] = []

        # Search for services with alertmanager-related names

        try:
            # Use -A to search ALL namespaces for services
            cmd = ["kubectl", "get", "svc", "-A", "-o", "json"]
            if context:
                cmd.extend(["--context", context])

            _logger.debug(
                "Service heuristic discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(f"kubectl get svc failed: {result.stderr[:200]}")
                _logger.warning(
                    "Service heuristic discovery failed: %s",
                    errors[-1],
                )
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "Service heuristic discovery: found %d services across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_service_item(item, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "Service heuristic discovery: found service %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

            # Use -A to search ALL namespaces for pods with app=alertmanager label
            pod_cmd = ["kubectl", "get", "pods", "-A", "-o", "json", "-l", "app=alertmanager"]
            if context:
                pod_cmd.extend(["--context", context])

            _logger.debug(
                "Service heuristic discovery: searching all namespaces for pods with command: %s",
                " ".join(pod_cmd),
            )

            pod_result = subprocess.run(
                pod_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if pod_result.returncode == 0:
                pod_data = json.loads(pod_result.stdout)
                pod_items = pod_data.get("items", [])

                _logger.debug(
                    "Service heuristic discovery: found %d pods with app=alertmanager label",
                    len(pod_items),
                )

                for pod in pod_items:
                    source = self._parse_pod_item(pod, context, cluster_uid)
                    if source:
                        # Avoid duplicates from service discovery
                        if not any(s.source_id == source.source_id for s in sources):
                            sources.append(source)
                            _logger.debug(
                                "Service heuristic discovery: found pod %s in namespace %s",
                                source.name,
                                source.namespace,
                            )

        except subprocess.TimeoutExpired:
            errors.append("Service/pod discovery timed out")
            _logger.warning("Service heuristic discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for service heuristic discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse service heuristic output: {exc}")
            _logger.warning("Failed to parse service heuristic discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_service_item(
        self,
        item: dict[str, Any],
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a service to check if it's an Alertmanager service."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")

        # Check if name matches alertmanager patterns
        name_lower = name.lower()
        if "alertmanager" not in name_lower:
            return None

        # Check for port 9093 (standard Alertmanager port)
        ports = item.get("spec", {}).get("ports", [])
        has_am_port = any(p.get("port") == 9093 for p in ports)

        if not has_am_port:
            # Still might be Alertmanager, just different port
            pass

        source_id = f"service:{namespace}/{name}"

        # Construct cluster-internal URL
        endpoint = f"http://{name}.{namespace}:9093"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=(
                "from-service",
                "port=9093" if has_am_port else "port=unknown",
            ),
            cluster_uid=cluster_uid,
        )

    def _parse_pod_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> AlertmanagerSource | None:
        """Parse a pod to extract Alertmanager info."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")

        # Extract pod IP
        pod_ip = item.get("status", {}).get("podIP")
        if not pod_ip:
            return None

        # Capture native Kubernetes object UID (optional identity anchor)
        object_uid: str | None = metadata.get("uid")

        source_id = f"pod:{namespace}/{name}"

        return AlertmanagerSource(
            source_id=source_id,
            endpoint=f"http://{pod_ip}:9093",
            namespace=namespace,
            name=name,
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.DISCOVERED,
            confidence_hints=("from-pod-label",),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


# --- Verification ---


@dataclass(frozen=True)
class VerificationResult:
    """Result of Alertmanager endpoint verification."""

    healthy: bool
    ready: bool
    version: str | None = None
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def verify_alertmanager_endpoint(endpoint: str, timeout_seconds: float = 5.0) -> VerificationResult:
    """Verify an Alertmanager endpoint by checking /-/healthy and /-/ready.

    Both endpoints must respond successfully for a candidate to become
    auto-tracked. This ensures we don't track non-functional Alertmanagers.

    Args:
        endpoint: Base URL of the Alertmanager instance
        timeout_seconds: Timeout for each health check request

    Returns:
        VerificationResult with health/ready status and version info
    """

    endpoint = endpoint.rstrip("/")

    # Check /-/healthy endpoint
    healthy, healthy_error = _check_endpoint(f"{endpoint}/-/healthy", timeout_seconds)

    if not healthy:
        return VerificationResult(
            healthy=False,
            ready=False,
            error=healthy_error,
        )

    # Check /-/ready endpoint
    ready, ready_error = _check_endpoint(f"{endpoint}/-/ready", timeout_seconds)

    if not ready:
        return VerificationResult(
            healthy=True,
            ready=False,
            error=ready_error,
        )

    # Get version info from /api/v2/status (auxiliary, non-blocking)
    version, _ = _get_version(f"{endpoint}/api/v2/status", timeout_seconds)

    return VerificationResult(
        healthy=True,
        ready=True,
        version=version,
    )


def _check_endpoint(url: str, timeout: float) -> tuple[bool, str | None]:
    """Check if an endpoint returns a successful response."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Connection failed: {exc.reason}"
    except TimeoutError:
        return False, "Request timed out"


def _get_version(url: str, timeout: float) -> tuple[str | None, str | None]:
    """Get Alertmanager version from status endpoint."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
            version_info = data.get("data", {}).get("versionInfo", {})
            version = version_info.get("version")
            return version, None
    except Exception as exc:
        return None, str(exc)


# --- Orchestrated Discovery ---


def discover_alertmanagers(
    context: str | None = None,
    manual_sources: tuple[AlertmanagerSource, ...] = (),
    cluster_uid: str | None = None,
) -> AlertmanagerSourceInventory:
    """Orchestrate Alertmanager discovery across all strategies.

    This is the main entry point for auto-discovery. It runs all strategies
    in priority order and merges results with proper precedence handling.

    All strategies search across ALL namespaces using kubectl -A flag.
    This is required because kube contexts may default to namespace 'default'
    while Alertmanager resources typically live in 'monitoring'.

    Args:
        context: Kubernetes context to use for discovery
        manual_sources: Pre-existing manual sources (never overwritten)
        cluster_uid: Canonical cluster identity (kube-system namespace UID) for
            cross-cluster disambiguation. Included in canonical_entity_id when available.

    Returns:
        AlertmanagerSourceInventory with all discovered sources
    """
    _logger.debug(
        "Starting Alertmanager discovery for context=%s, manual_sources=%d, cluster_uid=%s",
        context,
        len(manual_sources),
        cluster_uid,
    )

    inventory = AlertmanagerSourceInventory(cluster_context=context)

    # Add manual sources first (they take precedence)
    for source in manual_sources:
        inventory.add_source(source)
        _logger.debug(
            "Alertmanager discovery: added manual source %s from namespace %s",
            source.name,
            source.namespace,
        )

    # Run discovery strategies in priority order
    strategies: list[DiscoveryStrategy] = [
        CRDDiscoveryStrategy(),
        PrometheusCRDConfigDiscoveryStrategy(),
        ServiceHeuristicDiscoveryStrategy(),
    ]

    for strategy in strategies:
        _logger.debug(
            "Alertmanager discovery: running strategy %s",
            strategy.name,
        )
        result = strategy.discover(context, cluster_uid=cluster_uid)

        for source in result.sources:
            inventory.add_source(source)

        if result.errors:
            _logger.warning(
                "Alertmanager discovery strategy %s completed with errors: %s",
                strategy.name,
                result.errors,
            )
        else:
            _logger.debug(
                "Alertmanager discovery strategy %s completed: found %d sources",
                strategy.name,
                len(result.sources),
            )

    _logger.debug(
        "Alertmanager discovery complete: total sources=%d",
        len(inventory.sources),
    )

    return inventory


def verify_and_update_inventory(
    inventory: AlertmanagerSourceInventory,
    timeout_seconds: float = 5.0,
) -> AlertmanagerSourceInventory:
    """Verify all discovered sources and update their states.

    Sources that pass verification become auto-tracked.
    Sources that fail verification become degraded.
    Manual sources are not verified but maintain their manual state.

    Args:
        inventory: The source inventory to verify
        timeout_seconds: Timeout for verification requests

    Returns:
        Updated inventory with verified states
    """
    verified_sources: dict[str, AlertmanagerSource] = {}

    for source in inventory.sources.values():
        # Manual sources don't need verification
        if source.origin == AlertmanagerSourceOrigin.MANUAL:
            verified_sources[source.identity_key] = source
            continue

        # Verify non-manual sources
        result = verify_alertmanager_endpoint(source.endpoint, timeout_seconds)

        if result.healthy and result.ready:
            # Source passed verification
            verified_sources[source.identity_key] = AlertmanagerSource(
                source_id=source.source_id,
                endpoint=source.endpoint,
                namespace=source.namespace,
                name=source.name,
                origin=source.origin,
                state=AlertmanagerSourceState.AUTO_TRACKED,
                discovered_at=source.discovered_at,
                verified_at=result.checked_at,
                last_check=result.checked_at,
                last_error=None,
                verified_version=result.version,
                confidence_hints=source.confidence_hints,
                merged_provenances=source.merged_provenances,
                cluster_label=source.cluster_label,
                cluster_context=source.cluster_context,
                cluster_uid=source.cluster_uid,
                object_uid=source.object_uid,
            )
        else:
            # Source failed verification
            verified_sources[source.identity_key] = AlertmanagerSource(
                source_id=source.source_id,
                endpoint=source.endpoint,
                namespace=source.namespace,
                name=source.name,
                origin=source.origin,
                state=AlertmanagerSourceState.DEGRADED,
                discovered_at=source.discovered_at,
                verified_at=None,
                last_check=result.checked_at,
                last_error=result.error,
                verified_version=None,
                confidence_hints=source.confidence_hints,
                merged_provenances=source.merged_provenances,
                cluster_label=source.cluster_label,
                cluster_context=source.cluster_context,
                cluster_uid=source.cluster_uid,
                object_uid=source.object_uid,
            )

    return AlertmanagerSourceInventory(
        sources=verified_sources,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
    )


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


def build_endpoint_for_manual(
    endpoint: str,
    namespace: str | None = None,
    name: str | None = None,
) -> AlertmanagerSource:
    """Build a manual Alertmanager source from user-provided endpoint.
    
    The source is marked as operator-configured to distinguish it from
    promoted sources (which preserve their discovery origin).
    """
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    source_id = f"manual:{endpoint}"
    if namespace and name:
        source_id = f"manual:{namespace}/{name}"

    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
        manual_source_mode=AlertmanagerSourceMode.OPERATOR_CONFIGURED,
    )


# --- Prometheus Operator Alias Resolution ---

def _resolve_prometheus_operator_alias(
    source: AlertmanagerSource,
    all_sources: dict[str, AlertmanagerSource],
) -> AlertmanagerSource:
    '''Resolve Prometheus Operator alias: alertmanager-operated -> CRD-backed AM.
    
    In Prometheus Operator deployments:
    - CRD is named 'alertmanager-main' (or similar)
    - The actual service is 'alertmanager-operated' (conventional suffix)
    
    When a service heuristic finds 'alertmanager-operated', it should share the
    same canonical identity as the CRD-backed Alertmanager in the same namespace
    IF there's an unambiguous mapping (only one CRD Alertmanager in that namespace).
    
    This ensures that:
    - CRD source: monitoring/alertmanager-main (points to alertmanager-operated.monitoring:9093)
    - Service source: monitoring/alertmanager-operated (same endpoint)
    
    Both resolve to canonical identity 'monitoring/alertmanager-main' (the CRD's name).
    '''
    # Only apply alias resolution for service heuristic sources
    if source.origin != AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
        return source
    
    # Check if this is the alertmanager-operated pattern
    name = source.name or ''
    if not name.endswith('-operated'):
        return source
    
    # Find CRD sources in the same namespace
    crd_in_namespace = [
        s for s in all_sources.values()
        if s.namespace == source.namespace
        and s.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    ]
    
    # Only apply when there's exactly one CRD Alertmanager in this namespace
    # (unambiguous mapping)
    if len(crd_in_namespace) != 1:
        return source
    
    crd_source = crd_in_namespace[0]
    
    # Create aliased source with CRD's namespace/name but keep service's endpoint
    # (since they both point to the same endpoint: alertmanager-operated.svc:9093)
    # Preserve identity anchors from the source (cluster_uid/object_uid)
    aliased_source = AlertmanagerSource(
        source_id=f'service:{source.namespace}/{crd_source.name}',  # Use CRD name
        endpoint=source.endpoint,  # Keep the actual endpoint
        namespace=source.namespace,
        name=crd_source.name,  # Use CRD name for canonical identity
        origin=source.origin,
        state=source.state,
        discovered_at=source.discovered_at,
        verified_at=source.verified_at,
        last_check=source.last_check,
        last_error=source.last_error,
        verified_version=source.verified_version,
        confidence_hints=source.confidence_hints + ('prometheus-operator-alias',),
        merged_provenances=source.merged_provenances,
        cluster_label=source.cluster_label,
        cluster_context=source.cluster_context,
        cluster_uid=source.cluster_uid,
        object_uid=source.object_uid,
    )
    
    _logger.debug(
        'Resolved Prometheus Operator alias: %s/%s -> %s/%s (endpoint %s)',
        source.namespace,
        source.name,
        source.namespace,
        crd_source.name,
        source.endpoint,
    )
    
    return aliased_source


# --- Canonical Deduplication ---


def merge_deduplicate_inventory(
    inventory: AlertmanagerSourceInventory,
) -> AlertmanagerSourceInventory:
    """Deduplicate sources based on canonical endpoint identity and merge provenance.
    
    Different discovery strategies generate different source_ids for the same
    Alertmanager instance:
    - CRD: crd:monitoring/alertmanager-main
    - Prometheus Config: prom-crd-config:monitoring/alertmanager-main
    - Service: service:monitoring/alertmanager-operated (aliased to CRD name)
    
    This function:
    1. First resolves Prometheus Operator aliases (alertmanager-operated -> CRD name)
    2. Then merges sources with the same canonical identity
    3. Tracks all contributing origins in merged_provenances
    
    Rules:
    - Manual sources are authoritative and never deduplicated away
    - Higher-priority origin wins for display (CRD > Prometheus Config > Service)
    - All contributing origins are preserved in merged_provenances
    
    Args:
        inventory: Source inventory with potentially duplicate sources
        
    Returns:
        New inventory with deduplicated sources and merged provenance
    """
    # Step 1: Apply Prometheus Operator alias resolution
    # This transforms service:monitoring/alertmanager-operated -> service:monitoring/alertmanager-main
    # when there's exactly one CRD Alertmanager in that namespace
    # Collect ALL sources with their (possibly aliased) canonical identities
    sources_by_canonical: dict[str, list[AlertmanagerSource]] = {}
    for source in inventory.sources.values():
        aliased = _resolve_prometheus_operator_alias(source, inventory.sources)
        canon_key = aliased.canonical_identity
        if canon_key not in sources_by_canonical:
            sources_by_canonical[canon_key] = []
        sources_by_canonical[canon_key].append(aliased)
    
    # Step 2: For each canonical identity, select highest-priority source for the "winner" slot
    # but keep ALL sources for provenance merging
    sources_with_aliases: dict[str, AlertmanagerSource] = {}
    for canon_key, group in sources_by_canonical.items():
        # Find the highest-priority source to represent this identity
        priority_winner = min(group, key=lambda s: _ORIGIN_PRIORITY[s.origin])
        sources_with_aliases[canon_key] = priority_winner
    
    # Step 3: Re-group ALL sources (with aliases applied) by canonical identity for merging
    canonical_groups: dict[str, list[AlertmanagerSource]] = {}
    for source in inventory.sources.values():
        aliased = _resolve_prometheus_operator_alias(source, inventory.sources)
        canon_key = aliased.canonical_identity
        if canon_key not in canonical_groups:
            canonical_groups[canon_key] = []
        canonical_groups[canon_key].append(aliased)
    
    # Merge each group into a single source
    # Use canonical_identity as key to ensure duplicates merge properly
    merged_sources: dict[str, AlertmanagerSource] = {}
    
    for canon_key, group in canonical_groups.items():
        if len(group) == 1:
            # No deduplication needed, preserve as-is
            source = group[0]
            merged_sources[canon_key] = source
        else:
            # Merge multiple sources with same canonical identity
            # Find the authoritative source (manual first, then highest priority)
            manual_source = None
            best_source: AlertmanagerSource | None = None
            best_priority = float('inf')
            
            for source in group:
                priority = _ORIGIN_PRIORITY[source.origin]
                if source.origin == AlertmanagerSourceOrigin.MANUAL:
                    manual_source = source
                if priority < best_priority:
                    best_priority = priority
                    best_source = source
            
            # Use manual if present, otherwise use best priority source
            winner: AlertmanagerSource | None = manual_source if manual_source else best_source
            if winner is None:
                winner = group[0]  # Fallback to first
            
            # Merge all provenances
            all_provenances: set[AlertmanagerSourceOrigin] = set()
            for source in group:
                all_provenances.update(source.merged_provenances)
            
            # Preserve ordering by priority
            sorted_provenances = sorted(
                all_provenances,
                key=lambda p: _ORIGIN_PRIORITY[p]
            )
            
            # Create merged source with the winner's data but merged provenance
            # Preserve identity anchors from the winner (cluster_uid/object_uid)
            merged_source = AlertmanagerSource(
                source_id=winner.source_id,
                endpoint=winner.endpoint,
                namespace=winner.namespace,
                name=winner.name,
                origin=winner.origin,
                state=winner.state,
                discovered_at=winner.discovered_at,
                verified_at=winner.verified_at,
                last_check=winner.last_check,
                last_error=winner.last_error,
                verified_version=winner.verified_version,
                confidence_hints=winner.confidence_hints,
                merged_provenances=tuple(sorted_provenances),
                cluster_label=winner.cluster_label,
                cluster_context=winner.cluster_context,
                cluster_uid=winner.cluster_uid,
                object_uid=winner.object_uid,
            )
            
            merged_sources[canon_key] = merged_source
            
            _logger.debug(
                "Deduplicated %d sources to 1 for canonical identity %s, "
                "merged provenances: %s",
                len(group),
                canon_key,
                [p.value for p in sorted_provenances],
            )
    
    return AlertmanagerSourceInventory(
        sources=merged_sources,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
    )

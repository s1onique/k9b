"""vmalert auto-discovery for VictoriaMetrics stack installations.

This module discovers vmalert instances running in the cluster through service
heuristics and label-based discovery, verifies their health, and manages a source
inventory with explicit provenance tracking.

Discovery strategies (in priority order):
1. VMAlert CRD (via kubernetes custom resources)
2. Service heuristics by name pattern and labels (fallback)

Key invariants:
- Candidates should be verified for basic HTTP reachability
- Probe failures must not fail health collection; mark as discovered-but-unverified
- All sources track explicit origin and state for UI provenance

Identity model:
- canonical_entity_id: Deterministic hash from normalized defining facts (namespace, name, origin, cluster_uid, etc.)
- canonical_identity: namespace/name string for human-readable matching
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


# In-cluster context sentinel (matches live_snapshot.py behavior)
_IN_CLUSTER_CONTEXT = "in-cluster"


class VmalertSourceOrigin(StrEnum):
    """Origin of a vmalert source."""

    MANUAL = "manual"
    VMALERT_CRD = "vmalert-crd"
    SERVICE_HEURISTIC = "service-heuristic"


# Explicit priority map: lower number = higher priority
_ORIGIN_PRIORITY: dict[VmalertSourceOrigin, int] = {
    VmalertSourceOrigin.MANUAL: 0,
    VmalertSourceOrigin.VMALERT_CRD: 10,
    VmalertSourceOrigin.SERVICE_HEURISTIC: 20,
}


def _normalize_endpoint_for_identity(endpoint: str) -> str:
    """Strip scheme and trailing slash to get a canonical identity key."""
    normalized = endpoint.rstrip('/')
    if normalized.startswith('http://'):
        normalized = normalized[7:]
    elif normalized.startswith('https://'):
        normalized = normalized[8:]
    return normalized


class VmalertSourceState(StrEnum):
    """Current state of a vmalert source."""

    DISCOVERED = "discovered"
    DISCOVERED_BUT_UNVERIFIED = "discovered-but-unverified"
    AUTO_TRACKED = "auto-tracked"
    DEGRADED = "degraded"
    MISSING = "missing"
    MANUAL = "manual"


class VmalertSourceMode(StrEnum):
    """How a source entered manual tracking."""

    NOT_MANUAL = "not-manual"
    OPERATOR_CONFIGURED = "operator-configured"
    OPERATOR_PROMOTED = "operator-promoted"


@dataclass(frozen=True)
class VmalertSource:
    """A discovered or configured vmalert source with explicit provenance."""

    source_id: str
    endpoint: str
    namespace: str | None = None
    name: str | None = None
    origin: VmalertSourceOrigin = VmalertSourceOrigin.SERVICE_HEURISTIC
    state: VmalertSourceState = VmalertSourceState.DISCOVERED
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified_at: datetime | None = None
    last_check: datetime | None = None
    last_error: str | None = None
    verified_version: str | None = None
    confidence_hints: tuple[str, ...] = field(default_factory=tuple)
    merged_provenances: tuple[VmalertSourceOrigin, ...] = field(default_factory=tuple)
    cluster_label: str | None = None
    cluster_context: str | None = None
    cluster_uid: str | None = None
    object_uid: str | None = None
    manual_source_mode: VmalertSourceMode = VmalertSourceMode.NOT_MANUAL

    def __post_init__(self) -> None:
        object.__setattr__(self, 'endpoint', self.endpoint.rstrip('/'))
        if self.origin not in self.merged_provenances:
            object.__setattr__(self, 'merged_provenances', self.merged_provenances + (self.origin,))

    @property
    def canonical_identity(self) -> str:
        """Canonical identity for deduplication across strategies."""
        if self.namespace and self.name:
            return f"{self.namespace}/{self.name}"
        return _normalize_endpoint_for_identity(self.endpoint)

    @property
    def canonical_entity_id(self) -> str:
        """Canonical historical identity - deterministic hash from normalized defining facts."""
        from ..identity.vmalert_source import build_vmalert_canonical_entity_id
        return build_vmalert_canonical_entity_id(
            namespace=self.namespace,
            name=self.name,
            origin=self.origin.value if self.origin else None,
            endpoint=self.endpoint,
            cluster_uid=self.cluster_uid,
            object_uid=self.object_uid,
        )

    @property
    def operator_intent_key(self) -> str:
        """Operator-intent persistence key for durable actions."""
        from ..identity.vmalert_source import build_vmalert_operator_intent_key
        return build_vmalert_operator_intent_key(
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
        """Human-readable provenance showing all merged origins."""
        origins = [p.value for p in self.merged_provenances]
        labels = {
            'manual': 'Manual',
            'vmalert-crd': 'VMAlert CRD',
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
            'canonical_identity': self.canonical_identity,
            'canonicalEntityId': self.canonical_entity_id,
        }
        if self.cluster_uid is not None:
            result['cluster_uid'] = self.cluster_uid
        if self.object_uid is not None:
            result['object_uid'] = self.object_uid
        if self.manual_source_mode != VmalertSourceMode.NOT_MANUAL:
            result['manual_source_mode'] = self.manual_source_mode.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VmalertSource:
        """Reconstruct source from serialized dict."""
        merged_raw = data.get('merged_provenances')
        merged_provenances: tuple[VmalertSourceOrigin, ...] = ()
        if merged_raw:
            merged_provenances = tuple(
                VmalertSourceOrigin(v) if isinstance(v, str) else v
                for v in merged_raw
            )
        manual_source_mode_raw = data.get('manual_source_mode')
        if manual_source_mode_raw:
            manual_source_mode = VmalertSourceMode(manual_source_mode_raw)
        else:
            manual_source_mode = VmalertSourceMode.NOT_MANUAL
        return cls(
            source_id=str(data['source_id']),
            endpoint=str(data['endpoint']),
            namespace=data.get('namespace'),
            name=data.get('name'),
            origin=VmalertSourceOrigin(data.get('origin', 'service-heuristic')),
            state=VmalertSourceState(data.get('state', 'discovered')),
            discovered_at=_parse_datetime(data.get('discovered_at')),
            verified_at=_parse_datetime(data.get('verified_at')),
            last_check=_parse_datetime(data.get('last_check')),
            last_error=data.get('last_error'),
            verified_version=data.get('verified_version'),
            confidence_hints=tuple(data.get('confidence_hints', [])),
            merged_provenances=merged_provenances,
            cluster_label=data.get('cluster_label'),
            cluster_context=data.get('cluster_context'),
            cluster_uid=data.get('cluster_uid'),
            object_uid=data.get('object_uid'),
            manual_source_mode=manual_source_mode,
        )


@dataclass
class VmalertSourceInventory:
    """Collection of vmalert sources with merge semantics."""

    sources: dict[str, VmalertSource] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cluster_context: str | None = None
    artifact_id: str | None = field(default_factory=new_artifact_id)

    def add_source(self, source: VmalertSource) -> None:
        """Add a source, respecting manual precedence."""
        existing = self.sources.get(source.identity_key)
        if existing is None:
            self.sources[source.identity_key] = source
            return

        if existing.origin == VmalertSourceOrigin.MANUAL:
            return

        if source.origin == VmalertSourceOrigin.MANUAL:
            self.sources[source.identity_key] = source
            return

        if _ORIGIN_PRIORITY[source.origin] < _ORIGIN_PRIORITY[existing.origin]:
            self.sources[source.identity_key] = source
        elif source.origin == existing.origin:
            if source.state == VmalertSourceState.AUTO_TRACKED:
                self.sources[source.identity_key] = source

    def get_by_origin(self, origin: VmalertSourceOrigin) -> tuple[VmalertSource, ...]:
        """Get all sources with a specific origin."""
        return tuple(s for s in self.sources.values() if s.origin == origin)

    def get_by_state(self, state: VmalertSourceState) -> tuple[VmalertSource, ...]:
        """Get all sources with a specific state."""
        return tuple(s for s in self.sources.values() if s.state == state)

    def get_auto_tracked(self) -> tuple[VmalertSource, ...]:
        """Get all sources that are being actively tracked."""
        return tuple(s for s in self.sources.values() if s.state in (VmalertSourceState.AUTO_TRACKED, VmalertSourceState.MANUAL))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [s.to_dict() for s in self.sources.values()],
            "discovered_at": self.discovered_at.isoformat(),
            "cluster_context": self.cluster_context,
            "source_count": len(self.sources),
            "artifact_id": self.artifact_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VmalertSourceInventory:
        """Reconstruct inventory from serialized dict."""
        sources = {s["source_id"]: VmalertSource.from_dict(s) for s in data.get("sources", [])}
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

    sources: tuple[VmalertSource, ...]
    strategy: str
    errors: tuple[str, ...] = field(default_factory=tuple)


class DiscoveryStrategy:
    """Base class for vmalert discovery strategies."""

    name: str = "base"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Discover vmalert sources."""
        raise NotImplementedError


def _should_add_context_flag(context: str | None) -> bool:
    """Determine if kubectl should use --context flag."""
    if context is None:
        return False
    return context != _IN_CLUSTER_CONTEXT


def _kubectl_context_args(context: str | None) -> list[str]:
    """Return kubectl --context args based on context value."""
    if context is None or context == _IN_CLUSTER_CONTEXT:
        return []
    return ["--context", context]


class ServiceHeuristicDiscoveryStrategy(DiscoveryStrategy):
    """Discover vmalert via service heuristics.

    Lowest confidence method - looks for conventional service patterns
    and port configurations. Primary fallback when CRD is not available.
    """

    name = "service-heuristic"

    # Likely namespace patterns for VictoriaMetrics stack
    LIKELY_NAMESPACES = frozenset({
        'victoria-metrics-k8s-stack',
        'monitoring',
        'victoria-metrics',
        'vm',
    })

    # Likely port names for vmalert HTTP endpoints
    LIKELY_PORT_NAMES = frozenset({
        'http',
        'web',
        'metrics',
        'api',
        'vmalert',
    })

    # Likely port numbers
    LIKELY_PORTS = frozenset({8080, 8880})

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Search for vmalert services by name pattern and labels."""
        import subprocess

        sources: list[VmalertSource] = []
        errors: list[str] = []

        try:
            # Search all namespaces for services
            cmd = ["kubectl", "get", "svc", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "vmalert service heuristic discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug("vmalert service discovery: no services found")
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl get svc failed: {result.stderr[:200]}")
                _logger.warning("vmalert service heuristic discovery failed: %s", errors[-1])
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "vmalert service heuristic discovery: found %d services across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_service_item(item, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "vmalert service heuristic discovery: found service %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("vmalert service discovery timed out")
            _logger.warning("vmalert service heuristic discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for vmalert service heuristic discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse vmalert service heuristic output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_service_item(
        self,
        item: dict[str, Any],
        cluster_uid: str | None,
    ) -> VmalertSource | None:
        """Parse a service to check if it's a vmalert service."""
        metadata = item.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        labels = metadata.get("labels", {})

        # Check name patterns for vmalert - name match is primary
        name_lower = name.lower()
        if not self._matches_vmalert_name(name_lower):
            return None

        # Check labels - optional if name match is strong, but raises confidence
        has_labels = self._matches_vmalert_labels(labels)
        # Require label match only if name doesn't clearly indicate vmalert
        if not has_labels and not name_lower.startswith("vmalert-"):
            return None

        # Extract port information
        spec = item.get("spec", {})
        ports = spec.get("ports", [])
        target_port = self._extract_vmalert_port(ports)

        if target_port is None:
            return None

        # Capture object UID
        object_uid: str | None = metadata.get("uid")

        source_id = f"service:{namespace}/{name}"

        # Construct canonical in-cluster DNS URL
        endpoint = f"http://{name}.{namespace}.svc:{target_port}"

        # Build confidence hints
        confidence_hints: list[str] = ["from-service"]
        if self._matches_likely_namespace(namespace):
            confidence_hints.append("likely-namespace")
        if self._matches_likely_port(ports):
            confidence_hints.append("likely-port")

        return VmalertSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
            state=VmalertSourceState.DISCOVERED,
            confidence_hints=tuple(confidence_hints),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )

    def _matches_vmalert_name(self, name_lower: str) -> bool:
        """Check if service name matches vmalert patterns."""
        # Exact or prefix match
        if name_lower.startswith("vmalert-"):
            return True
        # Contains match
        if "vmalert" in name_lower:
            return True
        return False

    def _matches_vmalert_labels(self, labels: dict[str, str]) -> bool:
        """Check if service labels indicate vmalert/VM operator ownership."""
        # Check for app.kubernetes.io labels
        app_name = labels.get("app.kubernetes.io/name", "")
        if "vmalert" in app_name.lower():
            return True

        component = labels.get("app.kubernetes.io/component", "")
        if "vmalert" in component.lower():
            return True

        # Check for VM operator labels
        if labels.get("operator.victoriametrics.com/name"):
            return True
        if labels.get("app") and "vmalert" in labels["app"].lower():
            return True

        return False

    def _extract_vmalert_port(self, ports: list[dict[str, Any]]) -> int | None:
        """Extract the most likely vmalert HTTP port from service ports."""
        # First, look for ports by likely names
        for port_spec in ports:
            port_name = port_spec.get("name", "").lower()
            port_num = port_spec.get("port")
            if port_num and port_name in self.LIKELY_PORT_NAMES:
                return int(port_num)

        # Second, look for likely port numbers
        for port_spec in ports:
            port_num = port_spec.get("port")
            if port_num and int(port_num) in self.LIKELY_PORTS:
                return int(port_num)

        # Fallback: return first TCP port if available
        for port_spec in ports:
            if port_spec.get("protocol") == "TCP":
                return int(port_spec.get("port", 0))

        return None

    def _matches_likely_namespace(self, namespace: str) -> bool:
        """Check if namespace matches likely VM stack namespaces."""
        return namespace in self.LIKELY_NAMESPACES

    def _matches_likely_port(self, ports: list[dict[str, Any]]) -> bool:
        """Check if any port matches likely vmalert ports."""
        for port_spec in ports:
            if int(port_spec.get("port", 0)) in self.LIKELY_PORTS:
                return True
        return False


class VMAlertCRDDiscoveryStrategy(DiscoveryStrategy):
    """Discover vmalert via VMAlert CRDs (VictoriaMetrics Operator)."""

    name = "vmalert-crd"

    def discover(self, context: str | None = None, cluster_uid: str | None = None) -> DiscoveryResult:
        """Query VMAlert CRDs using kubectl."""
        import subprocess

        sources: list[VmalertSource] = []
        errors: list[str] = []

        try:
            # Try VictoriaMetrics Operator CRDs
            cmd = ["kubectl", "get", "vmalerts", "-A", "-o", "json"]
            cmd.extend(_kubectl_context_args(context))

            _logger.debug(
                "vmalert CRD discovery: searching all namespaces with command: %s",
                " ".join(cmd),
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "not found" in stderr or "no resources" in stderr:
                    _logger.debug("vmalert CRD discovery: VMAlert CRD not installed")
                    return DiscoveryResult(sources=(), errors=(), strategy=self.name)
                errors.append(f"kubectl failed: {result.stderr[:200]}")
                _logger.warning("vmalert CRD discovery failed: %s", errors[-1])
                return DiscoveryResult(sources=(), errors=tuple(errors), strategy=self.name)

            data = json.loads(result.stdout)
            items = data.get("items", [])

            _logger.debug(
                "vmalert CRD discovery: found %d VMAlert CRDs across all namespaces",
                len(items),
            )

            for item in items:
                source = self._parse_crd_item(item, context, cluster_uid)
                if source:
                    sources.append(source)
                    _logger.debug(
                        "vmalert CRD discovery: found source %s in namespace %s",
                        source.name,
                        source.namespace,
                    )

        except subprocess.TimeoutExpired:
            errors.append("kubectl get vmalerts timed out")
            _logger.warning("vmalert CRD discovery timed out")
        except FileNotFoundError:
            errors.append("kubectl not found in PATH")
            _logger.warning("kubectl not found in PATH for vmalert CRD discovery")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse kubectl output: {exc}")
            _logger.warning("Failed to parse vmalert CRD discovery output: %s", exc)

        return DiscoveryResult(sources=tuple(sources), errors=tuple(errors), strategy=self.name)

    def _parse_crd_item(
        self,
        item: dict[str, Any],
        context: str | None,
        cluster_uid: str | None,
    ) -> VmalertSource | None:
        """Parse a VMAlert CRD item into a source."""
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", "default")

        if not name:
            return None

        object_uid: str | None = metadata.get("uid")

        # Extract port from spec (VMAlert CRD typically specifies port)
        spec = item.get("spec", {})
        port = spec.get("port", 8080)  # Default to 8080

        source_id = f"crd:{namespace}/{name}"
        endpoint = f"http://{name}.{namespace}.svc:{port}"

        return VmalertSource(
            source_id=source_id,
            endpoint=endpoint,
            namespace=namespace,
            name=name,
            origin=VmalertSourceOrigin.VMALERT_CRD,
            state=VmalertSourceState.DISCOVERED,
            confidence_hints=("from-crd", f"namespace={namespace}"),
            cluster_uid=cluster_uid,
            object_uid=object_uid,
        )


# --- Verification ---


@dataclass(frozen=True)
class VerificationResult:
    """Result of vmalert endpoint verification."""

    reachable: bool
    version: str | None = None
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def verify_vmalert_endpoint(endpoint: str, timeout_seconds: float = 5.0) -> VerificationResult:
    """Verify a vmalert endpoint by checking basic HTTP reachability.

    Unlike Alertmanager verification, vmalert probing is gentle and non-fatal.
    Failures are marked as discovered-but-unverified, not degraded.

    Args:
        endpoint: Base URL of the vmalert instance
        timeout_seconds: Timeout for the health check request

    Returns:
        VerificationResult with reachability status
    """
    endpoint = endpoint.rstrip("/")

    # Try vmalert's main endpoint (may redirect or return 404 but connection is success)
    reachable, error = _check_endpoint(endpoint, timeout_seconds)

    if not reachable:
        return VerificationResult(
            reachable=False,
            error=error,
        )

    # Version info is auxiliary - don't fail if unavailable
    version, _ = _get_version(f"{endpoint}/api/v1/status/buildinfo", timeout_seconds)

    return VerificationResult(
        reachable=True,
        version=version,
    )


def _check_endpoint(url: str, timeout: float) -> tuple[bool, str | None]:
    """Check if an endpoint returns a successful response."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Any 2xx or redirect is considered reachable
            if 200 <= response.status < 400:
                return True, None
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # 404 or other HTTP errors still mean the service is reachable
        if exc.code in (404, 405):
            return True, None
        return False, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Connection failed: {exc.reason}"
    except TimeoutError:
        return False, "Request timed out"


def _get_version(url: str, timeout: float) -> tuple[str | None, str | None]:
    """Get vmalert version from buildinfo endpoint."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
            version = data.get("version", data.get("data", {}).get("version"))
            return version, None
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        return None, None


# --- Orchestrated Discovery ---


def discover_vmalerts(
    context: str | None = None,
    manual_sources: tuple[VmalertSource, ...] = (),
    cluster_uid: str | None = None,
) -> VmalertSourceInventory:
    """Orchestrate vmalert discovery across all strategies.

    Args:
        context: Kubernetes context to use for discovery
        manual_sources: Pre-existing manual sources (never overwritten)
        cluster_uid: Canonical cluster identity for cross-cluster disambiguation

    Returns:
        VmalertSourceInventory with all discovered sources
    """
    _logger.debug(
        "Starting vmalert discovery for context=%s, manual_sources=%d, cluster_uid=%s",
        context,
        len(manual_sources),
        cluster_uid,
    )

    inventory = VmalertSourceInventory(cluster_context=context)

    # Add manual sources first (they take precedence)
    for source in manual_sources:
        inventory.add_source(source)
        _logger.debug(
            "vmalert discovery: added manual source %s from namespace %s",
            source.name,
            source.namespace,
        )

    # Run discovery strategies in priority order
    strategies: list[DiscoveryStrategy] = [
        VMAlertCRDDiscoveryStrategy(),
        ServiceHeuristicDiscoveryStrategy(),
    ]

    for strategy in strategies:
        _logger.debug(
            "vmalert discovery: running strategy %s",
            strategy.name,
        )
        result = strategy.discover(context, cluster_uid=cluster_uid)

        for source in result.sources:
            inventory.add_source(source)

        if result.errors:
            _logger.warning(
                "vmalert discovery strategy %s completed with errors: %s",
                strategy.name,
                result.errors,
            )
        else:
            _logger.debug(
                "vmalert discovery strategy %s completed: found %d sources",
                strategy.name,
                len(result.sources),
            )

    _logger.debug(
        "vmalert discovery complete: total sources=%d",
        len(inventory.sources),
    )

    # Return deduplicated inventory by default
    return merge_deduplicate_inventory(inventory)


def verify_and_update_inventory(
    inventory: VmalertSourceInventory,
    timeout_seconds: float = 5.0,
) -> VmalertSourceInventory:
    """Verify discovered sources and update their states.

    Unlike Alertmanager verification, vmalert failures are non-fatal.
    Failed sources are marked as discovered-but-unverified, not degraded.

    Args:
        inventory: The source inventory to verify
        timeout_seconds: Timeout for verification requests

    Returns:
        Updated inventory with verified states
    """
    verified_sources: dict[str, VmalertSource] = {}

    for source in inventory.sources.values():
        # Manual sources don't need verification
        if source.origin == VmalertSourceOrigin.MANUAL:
            verified_sources[source.identity_key] = source
            continue

        # Verify non-manual sources (non-fatal)
        result = verify_vmalert_endpoint(source.endpoint, timeout_seconds)

        if result.reachable:
            verified_sources[source.identity_key] = VmalertSource(
                source_id=source.source_id,
                endpoint=source.endpoint,
                namespace=source.namespace,
                name=source.name,
                origin=source.origin,
                state=VmalertSourceState.DISCOVERED,
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
            # Probe failure is non-fatal - mark as discovered-but-unverified
            verified_sources[source.identity_key] = VmalertSource(
                source_id=source.source_id,
                endpoint=source.endpoint,
                namespace=source.namespace,
                name=source.name,
                origin=source.origin,
                state=VmalertSourceState.DISCOVERED_BUT_UNVERIFIED,
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

    return VmalertSourceInventory(
        sources=verified_sources,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
        artifact_id=inventory.artifact_id,
    )


# --- Utility Functions ---


def _parse_datetime(value: str | None) -> datetime:
    """Parse ISO format datetime string to timezone-aware UTC datetime."""
    if not value:
        return datetime.now(UTC)
    try:
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_endpoint_for_manual(
    endpoint: str,
    namespace: str | None = None,
    name: str | None = None,
) -> VmalertSource:
    """Build a manual vmalert source from user-provided endpoint."""
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    source_id = f"manual:{endpoint}"
    if namespace and name:
        source_id = f"manual:{namespace}/{name}"

    return VmalertSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=VmalertSourceOrigin.MANUAL,
        state=VmalertSourceState.MANUAL,
        manual_source_mode=VmalertSourceMode.OPERATOR_CONFIGURED,
    )


# --- Canonical Deduplication ---


def merge_deduplicate_inventory(
    inventory: VmalertSourceInventory,
) -> VmalertSourceInventory:
    """Deduplicate sources based on canonical identity and merge provenance.

    Args:
        inventory: Source inventory with potentially duplicate sources

    Returns:
        New inventory with deduplicated sources and merged provenance
    """
    # Group sources by canonical identity
    canonical_groups: dict[str, list[VmalertSource]] = {}
    for source in inventory.sources.values():
        canon_key = source.canonical_identity
        if canon_key not in canonical_groups:
            canonical_groups[canon_key] = []
        canonical_groups[canon_key].append(source)

    # Merge each group
    merged_sources: dict[str, VmalertSource] = {}

    for canon_key, group in canonical_groups.items():
        if len(group) == 1:
            merged_sources[canon_key] = group[0]
        else:
            # Find the authoritative source
            manual_source = None
            best_source: VmalertSource | None = None
            best_priority = float('inf')

            for source in group:
                priority = _ORIGIN_PRIORITY[source.origin]
                if source.origin == VmalertSourceOrigin.MANUAL:
                    manual_source = source
                if priority < best_priority:
                    best_priority = priority
                    best_source = source

            winner: VmalertSource | None = manual_source if manual_source else best_source
            if winner is None:
                winner = group[0]

            # Merge all provenances
            all_provenances: set[VmalertSourceOrigin] = set()
            for source in group:
                all_provenances.update(source.merged_provenances)

            sorted_provenances = sorted(all_provenances, key=lambda p: _ORIGIN_PRIORITY[p])

            merged_source = VmalertSource(
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
                "Deduplicated %d vmalert sources to 1 for canonical identity %s, merged provenances: %s",
                len(group),
                canon_key,
                [p.value for p in sorted_provenances],
            )

    return VmalertSourceInventory(
        sources=merged_sources,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
        artifact_id=inventory.artifact_id,
    )

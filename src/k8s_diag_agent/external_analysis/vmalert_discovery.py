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

This module is a compatibility surface. Actual implementations are in submodules:
- vmalert_discovery_models: Core data models and enums
- vmalert_discovery_crd_strategy: CRD-based discovery and context helpers
- vmalert_discovery_service_strategy: Service heuristic discovery
- vmalert_discovery_sources: Source construction helpers
- vmalert_discovery_strategies: Strategy façade for imports
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Import models from dedicated module
from .vmalert_discovery_models import (
    _ORIGIN_PRIORITY,
    DiscoveryResult,
    VmalertSource,
    VmalertSourceInventory,
    VmalertSourceMode,
    VmalertSourceOrigin,
    VmalertSourceState,
    _parse_datetime,
)

# Import sources/strategies from dedicated modules
from .vmalert_discovery_sources import (
    _IN_CLUSTER_CONTEXT,
    _kubectl_context_args,
    _should_add_context_flag,
    build_endpoint_for_manual,
)
from .vmalert_discovery_strategies import (
    DiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
    VMAlertCRDDiscoveryStrategy,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


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


# --- Re-exports for backward compatibility ---
# These allow existing code to import from vmalert_discovery instead of the submodules

__all__ = [
    # Enums
    "VmalertSourceOrigin",
    "VmalertSourceState",
    "VmalertSourceMode",
    # Core models
    "VmalertSource",
    "VmalertSourceInventory",
    "DiscoveryResult",
    # Constants
    "_ORIGIN_PRIORITY",
    "_IN_CLUSTER_CONTEXT",
    # Utility
    "_parse_datetime",
    # From vmalert_discovery_sources
    "_should_add_context_flag",
    "_kubectl_context_args",
    "build_endpoint_for_manual",
    # From vmalert_discovery_strategies
    "DiscoveryStrategy",
    "VMAlertCRDDiscoveryStrategy",
    "ServiceHeuristicDiscoveryStrategy",
    # Verification
    "VerificationResult",
    "verify_vmalert_endpoint",
    # Orchestration
    "discover_vmalerts",
    "verify_and_update_inventory",
    "merge_deduplicate_inventory",
]

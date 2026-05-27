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

# Import models from dedicated module
from .alertmanager_discovery_models import (
    _ORIGIN_PRIORITY,
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
    _parse_datetime,
)

# Import sources/strategies from dedicated module
from .alertmanager_discovery_sources import (
    _IN_CLUSTER_CONTEXT,
    CRDDiscoveryStrategy,
    DiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
    _kubectl_context_args,
    _resolve_prometheus_operator_alias,
    _should_add_context_flag,
    build_endpoint_for_manual,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


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
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        # REVIEWED: Non-fatal version fetch fallback.
        # Version is auxiliary info - failures should not block Alertmanager discovery.
        return None, None


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


# --- Re-exports for backward compatibility ---
# These allow existing code to import from alertmanager_discovery instead of the submodules

__all__ = [
    # Enums
    "AlertmanagerSourceOrigin",
    "AlertmanagerSourceState",
    "AlertmanagerSourceMode",
    # Core models
    "AlertmanagerSource",
    "AlertmanagerSourceInventory",
    "DiscoveryResult",
    # Constants
    "_ORIGIN_PRIORITY",
    "_IN_CLUSTER_CONTEXT",
    # Utility
    "_parse_datetime",
    # From alertmanager_discovery_sources
    "_should_add_context_flag",
    "_kubectl_context_args",
    "DiscoveryStrategy",
    "CRDDiscoveryStrategy",
    "PrometheusCRDConfigDiscoveryStrategy",
    "ServiceHeuristicDiscoveryStrategy",
    "build_endpoint_for_manual",
    "_resolve_prometheus_operator_alias",
    # Verification
    "VerificationResult",
    "verify_alertmanager_endpoint",
]
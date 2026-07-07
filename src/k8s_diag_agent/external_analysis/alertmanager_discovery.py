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

import logging

from .alertmanager_discovery_dedup_helpers import (
    ServiceHeuristicDedupGroup,
    _is_chart_alertmanager_service,
    _is_headless_operated_service,
    deduplicate_service_heuristic_sources,
)

# Import models from dedicated module
from .alertmanager_discovery_models import (
    _ORIGIN_PRIORITY,
    AlertmanagerSource,
    AlertmanagerSourceAlias,
    AlertmanagerSourceInventory,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
    _parse_datetime,
)

# Import orchestration functions
from .alertmanager_discovery_orchestration import (
    discover_alertmanagers,
    verify_and_update_inventory,
)

# Import sources/strategies from dedicated modules
from .alertmanager_discovery_sources import (
    _IN_CLUSTER_CONTEXT,
    _kubectl_context_args,
    _resolve_prometheus_operator_alias,
    _should_add_context_flag,
    build_endpoint_for_manual,
)

# Import strategies for re-export
from .alertmanager_discovery_strategies import (
    CRDDiscoveryStrategy,
    DiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
)

# Import verification from dedicated module
from .alertmanager_discovery_verification import (
    VerificationResult,
    verify_alertmanager_endpoint,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


def _infer_management_type(source: AlertmanagerSource) -> str:
    """Infer management type from service name heuristics."""
    name = source.name or ''
    if name.lower().endswith('-operated'):
        return "operator-managed"
    name_lower = name.lower()
    if 'alertmanager' in name_lower:
        return "chart-managed"
    return "unknown"


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
    1. Deduplicates SERVICE_HEURISTIC sources by endpoint (same endpoint = same Alertmanager)
    2. Resolves Prometheus Operator aliases (alertmanager-operated -> CRD name)
    3. Merges sources with the same canonical identity
    4. Tracks all contributing origins in merged_provenances

    Rules:
    - Manual sources are authoritative and never deduplicated away
    - Higher-priority origin wins for display (CRD > Prometheus Config > Service)
    - SERVICE_HEURISTIC sources are deduplicated by endpoint first
    - All contributing origins are preserved in merged_provenances

    Args:
        inventory: Source inventory with potentially duplicate sources

    Returns:
        New inventory with deduplicated sources and merged provenance
    """
    # Step 1: Separate SERVICE_HEURISTIC sources from others
    service_heuristic_sources: list[AlertmanagerSource] = []
    other_sources: list[AlertmanagerSource] = []

    for source in inventory.sources.values():
        if source.origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
            service_heuristic_sources.append(source)
        else:
            other_sources.append(source)

    # Step 2: Deduplicate SERVICE_HEURISTIC sources by endpoint
    merged_service_heuristic: dict[str, AlertmanagerSource] = {}

    if service_heuristic_sources:
        dedup_groups = deduplicate_service_heuristic_sources(service_heuristic_sources)

        # Create lookup dict of all sources for alias resolution
        all_sources_for_alias: dict[str, AlertmanagerSource] = {}
        for s in service_heuristic_sources:
            all_sources_for_alias[s.source_id] = s
        for s in other_sources:
            all_sources_for_alias[s.source_id] = s

        for group in dedup_groups:
            # Create aliases for non-preferred sources
            aliases_list: list[AlertmanagerSourceAlias] = []
            for alias_source in group.aliases:
                alias_mgmt = _infer_management_type(alias_source)
                aliases_list.append(AlertmanagerSourceAlias(
                    alias_name=alias_source.name or '',
                    alias_namespace=alias_source.namespace or '',
                    alias_endpoint=alias_source.endpoint,
                    discovery_method=alias_source.origin,
                    management_type=alias_mgmt,
                ))

            # Apply Prometheus Operator alias resolution
            aliased = _resolve_prometheus_operator_alias(group.preferred, all_sources_for_alias)

            # Create the merged source with aliases
            merged_source = AlertmanagerSource(
                source_id=aliased.source_id,
                endpoint=aliased.endpoint,
                namespace=aliased.namespace,
                name=aliased.name,
                origin=aliased.origin,
                state=aliased.state,
                discovered_at=aliased.discovered_at,
                verified_at=aliased.verified_at,
                last_check=aliased.last_check,
                last_error=aliased.last_error,
                verified_version=aliased.verified_version,
                confidence_hints=aliased.confidence_hints,
                merged_provenances=aliased.merged_provenances,
                cluster_label=aliased.cluster_label,
                cluster_context=aliased.cluster_context,
                cluster_uid=aliased.cluster_uid,
                object_uid=aliased.object_uid,
                aliases=tuple(aliases_list) if aliases_list else (),
            )

            # Use canonical_identity as key so SERVICE_HEURISTIC sources aliased to CRD
            # names will merge with CRD sources
            canon_key = merged_source.canonical_identity
            merged_service_heuristic[canon_key] = merged_source

            _logger.debug(
                "Deduplicated %d SERVICE_HEURISTIC sources to 1 for canonical identity %s, "
                "preferred: %s, aliases: %s",
                len(group.aliases) + 1,
                canon_key,
                merged_source.name,
                [a.alias_name for a in aliases_list],
            )

    # Step 3: Combine all sources and merge by canonical identity
    by_canonical: dict[str, list[AlertmanagerSource]] = {}

    for source in merged_service_heuristic.values():
        canon_key = source.canonical_identity
        if canon_key not in by_canonical:
            by_canonical[canon_key] = []
        by_canonical[canon_key].append(source)

    for source in other_sources:
        canon_key = source.canonical_identity
        if canon_key not in by_canonical:
            by_canonical[canon_key] = []
        by_canonical[canon_key].append(source)

    # Final merge pass - merge sources with same canonical identity
    final_sources: dict[str, AlertmanagerSource] = {}

    for canon_key, sources_list in by_canonical.items():
        if len(sources_list) == 1:
            final_sources[canon_key] = sources_list[0]
        else:
            # Merge multiple sources with same canonical identity
            manual_src = None
            best_src: AlertmanagerSource | None = None
            best_priority = float('inf')

            for src in sources_list:
                priority = _ORIGIN_PRIORITY[src.origin]
                if src.origin == AlertmanagerSourceOrigin.MANUAL:
                    manual_src = src
                if priority < best_priority:
                    best_priority = priority
                    best_src = src

            # Use manual if present, otherwise use best priority source
            winning_source: AlertmanagerSource | None = manual_src if manual_src else best_src
            if winning_source is None:
                winning_source = sources_list[0]

            # Merge all provenances
            merged_provenances: set[AlertmanagerSourceOrigin] = set()
            for src in sources_list:
                merged_provenances.update(src.merged_provenances)

            sorted_provenances = sorted(merged_provenances, key=lambda p: _ORIGIN_PRIORITY[p])

            merged_source = AlertmanagerSource(
                source_id=winning_source.source_id,
                endpoint=winning_source.endpoint,
                namespace=winning_source.namespace,
                name=winning_source.name,
                origin=winning_source.origin,
                state=winning_source.state,
                discovered_at=winning_source.discovered_at,
                verified_at=winning_source.verified_at,
                last_check=winning_source.last_check,
                last_error=winning_source.last_error,
                verified_version=winning_source.verified_version,
                confidence_hints=winning_source.confidence_hints,
                merged_provenances=tuple(sorted_provenances),
                cluster_label=winning_source.cluster_label,
                cluster_context=winning_source.cluster_context,
                cluster_uid=winning_source.cluster_uid,
                object_uid=winning_source.object_uid,
                aliases=winning_source.aliases,
            )

            final_sources[canon_key] = merged_source

            _logger.debug(
                "Deduplicated %d sources to 1 for canonical identity %s, "
                "merged provenances: %s",
                len(sources_list),
                canon_key,
                [p.value for p in sorted_provenances],
            )

    return AlertmanagerSourceInventory(
        sources=final_sources,
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
    # Orchestration functions
    "discover_alertmanagers",
    "verify_and_update_inventory",
    # Verification
    "VerificationResult",
    "verify_alertmanager_endpoint",
    # Strategies
    "DiscoveryStrategy",
    "CRDDiscoveryStrategy",
    "PrometheusCRDConfigDiscoveryStrategy",
    "ServiceHeuristicDiscoveryStrategy",
    # Sources
    "_should_add_context_flag",
    "_kubectl_context_args",
    "build_endpoint_for_manual",
    "_resolve_prometheus_operator_alias",
    # Deduplication
    "merge_deduplicate_inventory",
    # Dedup helpers
    "ServiceHeuristicDedupGroup",
    "_is_chart_alertmanager_service",
    "_is_headless_operated_service",
    "deduplicate_service_heuristic_sources",
]

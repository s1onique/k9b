"""Alertmanager discovery orchestration.

This module orchestrates Alertmanager discovery across all strategies and manages
the inventory lifecycle including verification and deduplication.
"""

from __future__ import annotations

import logging

# Import models from dedicated module
from .alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)

# Import strategies from dedicated module
from .alertmanager_discovery_strategies import (
    CRDDiscoveryStrategy,
    DiscoveryStrategy,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
)

# Import verification from dedicated module
from .alertmanager_discovery_verification import (
    verify_alertmanager_endpoint,
)

# Import structured logging helper
from .discovery_structured_logging import emit_discovery_strategy_failure

# Module logger for debug output
_logger = logging.getLogger(__name__)


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
            # Emit structured WARNING event for strategy failure (uses shared helper)
            # Do NOT emit unstructured log - strategy failures are handled via structured events
            emit_discovery_strategy_failure(
                component="alertmanager-discovery",
                strategy_name=strategy.name,
                errors=result.errors,
                cluster_context=context,
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

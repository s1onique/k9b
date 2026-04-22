"""Alertmanager discovery runner for health loop.

Extracts the Alertmanager discovery flow from HealthLoopRunner into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the discovery logic that:
1. Discovers Alertmanager sources per cluster target
2. Aggregates sources with cluster provenance tagging
3. Applies registry state from durable storage
4. Writes the inventory artifact for downstream processing
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.alertmanager_artifact import write_alertmanager_sources
from ..external_analysis.alertmanager_discovery import (
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    discover_alertmanagers,
    merge_deduplicate_inventory,
)
from ..external_analysis.alertmanager_source_registry import (
    RegistryDesiredState,
    apply_registry_to_inventory,
    lookup_registry_state,
    read_source_registry,
)

if TYPE_CHECKING:
    from .loop import HealthSnapshotRecord


def run_alertmanager_discovery(
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
    log_event: Callable[..., None],
    run_id: str,
) -> AlertmanagerSourceInventory:
    """Run Alertmanager discovery for each cluster target and persist the inventory.
    
    Discovers Alertmanager instances in each cluster, verifies them, and writes
    the aggregated inventory to a run-scoped artifact.
    
    This is non-fatal: discovery failures are logged but do not stop the run.
    
    Args:
        records: List of health snapshot records from cluster collection.
        directories: Dict with "root" key pointing to health run directory.
        log_event: Callback for structured logging (component, severity, message, **metadata).
        run_id: Run identifier for artifact naming.
    
    Returns:
        Verified AlertmanagerSourceInventory with registry state applied.
    """
    if not records:
        log_event(
            "alertmanager-discovery",
            "DEBUG",
            "Alertmanager discovery skipped: no cluster records",
            event="alertmanager-discovery-skipped",
            reason="no_records",
        )
        return AlertmanagerSourceInventory()
    
    # Aggregate all discovered sources across all targets
    aggregated_inventory: AlertmanagerSourceInventory | None = None
    
    for record in records:
        target_context = record.target.context
        cluster_label = record.target.label
        
        # Log discovery start for this target
        log_event(
            "alertmanager-discovery",
            "DEBUG",
            "Starting Alertmanager discovery for cluster target",
            event="alertmanager-discovery-start",
            cluster_label=cluster_label,
            cluster_context=target_context,
            artifact_directory=str(directories["root"]),
        )
        
        try:
            # Derive cluster_uid for this context (canonical identity anchor)
            # This is used for cross-cluster disambiguation in canonical_entity_id
            from ..identity.cluster import derive_cluster_uid
            cluster_uid = derive_cluster_uid(kube_context=target_context)
            
            # Run discovery for this context with cluster_uid for identity threading
            discovered_inventory = discover_alertmanagers(
                context=target_context,
                cluster_uid=cluster_uid,
            )
            
            # Log discovery result counts by origin
            crd_count = len(discovered_inventory.get_by_origin(
                AlertmanagerSourceOrigin.ALERTMANAGER_CRD
            ))
            prom_crd_count = len(discovered_inventory.get_by_origin(
                AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG
            ))
            service_count = len(discovered_inventory.get_by_origin(
                AlertmanagerSourceOrigin.SERVICE_HEURISTIC
            ))
            manual_count = len(discovered_inventory.get_by_origin(
                AlertmanagerSourceOrigin.MANUAL
            ))
            
            log_event(
                "alertmanager-discovery",
                "DEBUG",
                "Alertmanager discovery completed for cluster target",
                event="alertmanager-discovery-result",
                cluster_label=cluster_label,
                cluster_context=target_context,
                candidates_found=len(discovered_inventory.sources),
                by_origin={
                    "alertmanager-crd": crd_count,
                    "prometheus-crd-config": prom_crd_count,
                    "service-heuristic": service_count,
                    "manual": manual_count,
                },
            )
            
            # Merge into aggregated inventory, tagging each source with cluster provenance.
            # Tag all discovered sources with cluster_label (for UI) and cluster_context (for execution).
            for source in discovered_inventory.sources.values():
                # Set both cluster_label and cluster_context for full provenance:
                # - cluster_label: operator-facing label for per-cluster UI filtering
                # - cluster_context: kube context for execution (kubectl, port-forward, snapshots)
                source_with_cluster = replace(
                    source,
                    cluster_label=cluster_label,
                    cluster_context=target_context,
                )
                if aggregated_inventory is None:
                    # First cluster: start the aggregated inventory with tagged sources
                    aggregated_inventory = AlertmanagerSourceInventory(
                        cluster_context=target_context,
                    )
                aggregated_inventory.add_source(source_with_cluster)
                    
        except Exception as exc:
            log_event(
                "alertmanager-discovery",
                "WARNING",
                "Alertmanager discovery failed for cluster target",
                event="alertmanager-discovery-failed",
                cluster_label=cluster_label,
                cluster_context=target_context,
                severity_reason=str(exc),
                reason="discovery-error",
                # Run should continue (non-fatal)
            )
            continue
    
    # If we have no inventory, create empty one
    if aggregated_inventory is None:
        aggregated_inventory = AlertmanagerSourceInventory()
    
    # Note: verification step is intentionally skipped to keep discovery fast.
    # Call verify_and_update_inventory() if you need to validate source reachability.
    verified_inventory = aggregated_inventory
    
    # Deduplicate sources: merge multiple discovery strategies for the same
    # Alertmanager (e.g., CRD + Prometheus config + service heuristic) into
    # a single source with merged provenance tracking all contributing origins.
    verified_inventory = merge_deduplicate_inventory(verified_inventory)
    
    # Load durable registry and apply registry state to discovered sources.
    # This ensures that operator promote/disable actions persist across runs.
    # Registry entries are keyed by cluster_context + canonical_identity.
    registry = read_source_registry(directories["root"])
    
    if registry is not None:
        # Use shared lookup helper for registry matching.
        # This centralizes the label-first key logic and avoids duplicating key construction.
        # lookup_registry_state() uses source.cluster_label (not inventory-level label)
        # for cross-run persistence.
        registry_disabled_count = 0
        registry_manual_count = 0
        for source in verified_inventory.sources.values():
            # Use shared helper - uses source.cluster_label for canonical key
            desired_state = lookup_registry_state(
                registry,
                verified_inventory.cluster_context,
                source,
            )
            if desired_state == RegistryDesiredState.MANUAL:
                registry_manual_count += 1
            elif desired_state == RegistryDesiredState.DISABLED:
                registry_disabled_count += 1
        
        verified_inventory = apply_registry_to_inventory(
            verified_inventory, registry, verified_inventory.cluster_context
        )
        
        log_event(
            "alertmanager-discovery",
            "DEBUG",
            "Alertmanager registry state applied",
            event="alertmanager-registry-applied",
            registry_entries=len(registry.entries),
            sources_promoted=registry_manual_count,
            sources_disabled=registry_disabled_count,
        )
    else:
        log_event(
            "alertmanager-discovery",
            "DEBUG",
            "No Alertmanager source registry found",
            event="alertmanager-registry-absent",
        )
    
    # Log verification result summary
    auto_tracked_count = len(verified_inventory.get_by_state(
        AlertmanagerSourceState.AUTO_TRACKED
    ))
    manual_count = len(verified_inventory.get_by_state(
        AlertmanagerSourceState.MANUAL
    ))
    degraded_count = len(verified_inventory.get_by_state(
        AlertmanagerSourceState.DEGRADED
    ))
    discovered_count = len(verified_inventory.get_by_state(
        AlertmanagerSourceState.DISCOVERED
    ))
    
    log_event(
        "alertmanager-discovery",
        "DEBUG",
        "Alertmanager verification result",
        event="alertmanager-verification-result",
        total_sources=len(verified_inventory.sources),
        by_state={
            "auto-tracked": auto_tracked_count,
            "manual": manual_count,
            "degraded": degraded_count,
            "discovered": discovered_count,
        },
    )
    
    # Write the inventory artifact
    try:
        artifact_path = write_alertmanager_sources(
            directories["root"],
            verified_inventory,
            run_id,
        )
        
        log_event(
            "alertmanager-discovery",
            "INFO",
            "Alertmanager sources inventory written",
            event="alertmanager-sources-written",
            source_count=len(verified_inventory.sources),
            artifact_path=str(artifact_path),
        )
    except Exception as exc:
        log_event(
            "alertmanager-discovery",
            "ERROR",
            "Failed to write Alertmanager sources inventory",
            event="alertmanager-sources-write-failed",
            severity_reason=str(exc),
            reason="write-error",
        )
        # Continue without failing the run
    
    return verified_inventory

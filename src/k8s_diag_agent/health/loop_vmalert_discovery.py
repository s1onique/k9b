"""vmalert discovery runner for health loop.

Extracts the vmalert discovery flow from HealthLoopRunner into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the discovery logic that:
1. Discovers vmalert sources per cluster target
2. Aggregates sources with cluster provenance tagging
3. Verifies source reachability (non-fatal)
4. Writes the inventory artifact for downstream processing
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.vmalert_artifact import write_vmalert_sources
from ..external_analysis.vmalert_discovery import (
    VmalertSourceInventory,
    VmalertSourceOrigin,
    VmalertSourceState,
    discover_vmalerts,
    merge_deduplicate_inventory,
    verify_and_update_inventory,
)

if TYPE_CHECKING:
    from .loop_types import HealthSnapshotRecord


def run_vmalert_discovery(
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
    log_event: Callable[..., None],
    run_id: str,
) -> VmalertSourceInventory:
    """Run vmalert discovery for each cluster target and persist the inventory.
    
    Discovers vmalert instances in each cluster, verifies them, and writes
    the aggregated inventory to a run-scoped artifact.
    
    This is non-fatal: discovery/verification failures are logged but do not stop the run.
    
    Args:
        records: List of health snapshot records from cluster collection.
        directories: Dict with "root" key pointing to health run directory.
        log_event: Callback for structured logging (component, severity, message, **metadata).
        run_id: Run identifier for artifact naming.
    
    Returns:
        Verified VmalertSourceInventory with all sources aggregated.
    """
    if not records:
        log_event(
            "vmalert-discovery",
            "DEBUG",
            "vmalert discovery skipped: no cluster records",
            event="vmalert-discovery-skipped",
            reason="no_records",
        )
        return VmalertSourceInventory()
    
    # Aggregate all discovered sources across all targets
    aggregated_inventory: VmalertSourceInventory | None = None
    
    for record in records:
        target_context = record.target.context
        cluster_label = record.target.label
        
        # Log discovery start for this target
        log_event(
            "vmalert-discovery",
            "DEBUG",
            "Starting vmalert discovery for cluster target",
            event="vmalert-discovery-start",
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
            discovered_inventory = discover_vmalerts(
                context=target_context,
                cluster_uid=cluster_uid,
            )
            
            # Log discovery result counts by origin
            crd_count = len(discovered_inventory.get_by_origin(
                VmalertSourceOrigin.VMALERT_CRD
            ))
            service_count = len(discovered_inventory.get_by_origin(
                VmalertSourceOrigin.SERVICE_HEURISTIC
            ))
            manual_count = len(discovered_inventory.get_by_origin(
                VmalertSourceOrigin.MANUAL
            ))
            
            log_event(
                "vmalert-discovery",
                "DEBUG",
                "vmalert discovery completed for cluster target",
                event="vmalert-discovery-result",
                cluster_label=cluster_label,
                cluster_context=target_context,
                candidates_found=len(discovered_inventory.sources),
                by_origin={
                    "vmalert-crd": crd_count,
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
                    aggregated_inventory = VmalertSourceInventory(
                        cluster_context=target_context,
                    )
                aggregated_inventory.add_source(source_with_cluster)
            
            # REVIEWED: kubectl/cluster discovery boundary.
            # Subprocess failures (OSError), context resolution (RuntimeError), and
            # timeout/connectivity errors (TimeoutError) are all non-fatal discovery failures.
            # Narrowed to explicit operational failure types -- discovery failures result in
            # empty inventory, which is the correct non-fatal fallback behavior.
            # No credential exposure in error string.
        except (OSError, RuntimeError, TimeoutError) as exc:
            log_event(
                "vmalert-discovery",
                "WARNING",
                "vmalert discovery failed for cluster target",
                event="vmalert-discovery-failed",
                cluster_label=cluster_label,
                cluster_context=target_context,
                severity_reason=str(exc),
                reason="discovery-error",
                # Run should continue (non-fatal)
            )
            continue
    
    # If we have no inventory, create empty one
    if aggregated_inventory is None:
        aggregated_inventory = VmalertSourceInventory()
    
    # Deduplicate sources: merge multiple discovery strategies for the same
    # vmalert (e.g., CRD + service heuristic) into a single source with
    # merged provenance tracking all contributing origins.
    aggregated_inventory = merge_deduplicate_inventory(aggregated_inventory)
    
    # Verify sources for reachability (non-fatal)
    # Verification failures mark sources as discovered-but-unverified, not degraded
    # REVIEWED: Broad except is intentional - verification is an operational boundary where
    # all failures (network, DNS, HTTP, timeout) should be treated as non-fatal.
    # Programming errors (TypeError, AttributeError) here indicate bugs in verify_and_update_inventory
    # or downstream helpers, but catching them prevents a single source's verification from
    # failing the entire health loop run. This matches Alertmanager's non-fatal verification model.
    try:
        verified_inventory = verify_and_update_inventory(aggregated_inventory)
        
        log_event(
            "vmalert-discovery",
            "DEBUG",
            "vmalert verification completed",
            event="vmalert-verification-completed",
            total_sources=len(verified_inventory.sources),
        )
    except Exception as exc:
        # Verification failures are non-fatal; use unverified inventory
        log_event(
            "vmalert-discovery",
            "WARNING",
            "vmalert verification failed",
            event="vmalert-verification-failed",
            severity_reason=str(exc),
            reason="verification-error",
        )
        verified_inventory = aggregated_inventory
    
    # Log verification result summary
    discovered_count = len(verified_inventory.get_by_state(
        VmalertSourceState.DISCOVERED
    ))
    discovered_but_unverified_count = len(verified_inventory.get_by_state(
        VmalertSourceState.DISCOVERED_BUT_UNVERIFIED
    ))
    auto_tracked_count = len(verified_inventory.get_by_state(
        VmalertSourceState.AUTO_TRACKED
    ))
    manual_count = len(verified_inventory.get_by_state(
        VmalertSourceState.MANUAL
    ))
    
    log_event(
        "vmalert-discovery",
        "DEBUG",
        "vmalert verification result",
        event="vmalert-verification-result",
        total_sources=len(verified_inventory.sources),
        by_state={
            "discovered": discovered_count,
            "discovered-but-unverified": discovered_but_unverified_count,
            "auto-tracked": auto_tracked_count,
            "manual": manual_count,
        },
    )
    
    # Write the inventory artifact
    try:
        artifact_path = write_vmalert_sources(
            directories["root"],
            verified_inventory,
            run_id,
        )
        
        log_event(
            "vmalert-discovery",
            "INFO",
            "vmalert sources inventory written",
            event="vmalert-sources-written",
            source_count=len(verified_inventory.sources),
            artifact_path=str(artifact_path),
        )
    except (OSError, RuntimeError) as exc:
        log_event(
            "vmalert-discovery",
            "ERROR",
            "Failed to write vmalert sources inventory",
            event="vmalert-sources-write-failed",
            severity_reason=str(exc),
            reason="write-error",
        )
        # Continue without failing the run
    
    return verified_inventory

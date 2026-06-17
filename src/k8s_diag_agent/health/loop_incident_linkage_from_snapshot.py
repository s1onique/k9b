"""Derive incident linkage context from cluster snapshot data.

This module provides the production wiring between cluster evidence and
next-check incident linkage. It extracts entity identity from snapshot
data to enable deterministic linkage in normal production runs.

Design constraints:
- Pure functions only
- No file IO
- No provider/LLM calls
- No Kubernetes calls
- No store mutation

Linkage status semantics:
- "linked": incident_id is present and sufficient for deterministic mapping
- "partial": incident_id missing but enough structured fields for fallback
- "unlinked": insufficient identity for any linkage
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..collect.cluster_snapshot import ClusterSnapshot
    from ..external_analysis.next_check_incident_linkage import IncidentLinkageContext


def derive_linkage_context_from_snapshots(
    snapshots: list[ClusterSnapshot],
    run_id: str,
) -> IncidentLinkageContext | None:
    """Derive incident linkage context from cluster snapshots for production runs.

    This function examines cluster snapshot health signals to determine if there
    are incident-class issues that should be linked to next-check plans.

    When full entity identity (namespace, object_kind, object_name) is available,
    the deterministic incident_id is computed using the same algorithm as the
    Incident aggregate (make_incident_id), enabling linkage_status="linked".

    When only partial identity is available, returns linkage_status="partial"
    or "unlinked" as appropriate.

    Args:
        snapshots: List of cluster snapshots from health assessment collection.
        run_id: The current run identifier.

    Returns:
        IncidentLinkageContext if incident-class health issues are detected,
        None otherwise.

    Example:
        >>> from k8s_diag_agent.health.loop_incident_linkage_from_snapshot import derive_linkage_context_from_snapshots
        >>> snapshots = [cluster_snapshot]  # From health loop records
        >>> context = derive_linkage_context_from_snapshots(snapshots, "run-123")
        >>> if context:
        ...     print(f"Linkage: {context.determine_linkage_status()}")
    """
    # Import here to avoid circular imports at module level
    from ..collect.cluster_snapshot import ClusterSnapshot as CS
    from ..collect.incident_lifecycle import make_incident_id
    from ..external_analysis.next_check_incident_linkage import IncidentLinkageContext

    # Find snapshots with incident-class health issues
    for snapshot in snapshots:
        if not isinstance(snapshot, CS):
            continue

        signals = snapshot.health_signals
        if signals is None:
            continue

        # Check for incident-class pod health issues
        pod_counts = signals.pod_counts
        if pod_counts is None:
            continue

        # CrashLoopBackOff is the primary incident-class health issue
        if pod_counts.crash_loop_backoff > 0:
            # Try to extract entity identity from workloads
            # The workloads dict structure varies, but typically contains
            # namespace/pod information for degraded workloads
            namespace: str | None = None
            object_name: str | None = None
            object_kind: str | None = None

            # Try to get namespace from snapshot metadata or workloads
            workloads = snapshot.workloads
            if workloads:
                # workloads is a dict - try to find pod data
                for key, value in workloads.items():
                    if isinstance(value, dict):
                        # Try common patterns for pod info
                        ns = value.get("namespace") or value.get("metadata", {}).get("namespace")
                        name = value.get("name") or value.get("metadata", {}).get("name")
                        kind = value.get("kind") or value.get("kind", "Pod")

                        if ns and name:
                            namespace = ns
                            object_name = name
                            object_kind = kind
                            break

            # If no specific pod found, use cluster-level namespace
            if namespace is None:
                # Fall back to default namespace for cluster-level incident context
                namespace = "default"

            # Compute deterministic incident_id when full entity identity is available
            # This enables linkage_status="linked" matching the Incident aggregate
            incident_id: str | None = None
            if namespace and object_name and object_kind:
                incident_id = make_incident_id(
                    namespace=namespace,
                    object_kind=object_kind,
                    object_name=object_name,
                    candidate_class="crash_loop",
                )

            return IncidentLinkageContext(
                incident_id=incident_id,
                source_candidate_id=None,
                namespace=namespace,
                object_kind=object_kind or "Pod",
                object_name=object_name,
                candidate_class="crash_loop",
                run_id=run_id,
            )

        # Check for image pull issues - another incident-class problem
        if pod_counts.image_pull_backoff > 0:
            workloads = snapshot.workloads
            namespace: str | None = "default"
            if workloads:
                for key, value in workloads.items():
                    if isinstance(value, dict):
                        ns = value.get("namespace") or value.get("metadata", {}).get("namespace")
                        if ns:
                            namespace = ns
                            break

            return IncidentLinkageContext(
                incident_id=None,  # No specific pod identified for image pull
                source_candidate_id=None,
                namespace=namespace,
                object_kind="Pod",
                object_name=None,
                candidate_class="image_pull",
                run_id=run_id,
            )

    # No incident-class health issues found
    return None

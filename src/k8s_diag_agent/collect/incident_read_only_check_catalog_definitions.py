"""Read-only check catalog definitions for automatic diagnosis loop.

This module contains all check definitions organized by domain:
- Generic checks
- Pod checks
- Deployment/ReplicaSet checks
- Service checks
- Storage checks
- Node checks
- Alertmanager context checks

Design constraints:
- All checks are read-only (list, get, logs with tail limits)
- No mutation, no exec, no kubectl shell
- Bounded timeouts and result sizes
"""

from __future__ import annotations

from .incident_read_only_check_catalog_contracts import CheckDefinition

# =============================================================================
# Generic checks
# =============================================================================

GENERIC_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="incident_identity_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=False,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=False,
        description="Summarize incident identity (namespace, object kind/name)",
        rationale="Provides context for all other checks",
    ),
    CheckDefinition(
        check_id="owner_reference_chain",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Trace owner reference chain (Deployment -> ReplicaSet -> Pod)",
        rationale="Helps identify if issue is at workload or pod level",
    ),
    CheckDefinition(
        check_id="recent_namespace_warning_events",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=False,
        description="List recent warning events in namespace",
        rationale="Warning events often indicate root cause of failures",
    ),
    CheckDefinition(
        check_id="object_recent_events",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="List recent events for specific object",
        rationale="Object-specific events show direct cause of issues",
    ),
]


# =============================================================================
# Pod checks
# =============================================================================

POD_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="pod_status_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get pod status including phase, conditions, and restarts",
        rationale="Pod status reveals current state and failure modes",
    ),
    CheckDefinition(
        check_id="pod_container_status_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get container status for all containers in pod",
        rationale="Container status shows which container is failing and why",
    ),
    CheckDefinition(
        check_id="pod_restart_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get container restart counts",
        rationale="High restart count indicates CrashLoopBackoff or frequent failures",
    ),
    CheckDefinition(
        check_id="pod_current_logs_tail",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Read current container logs (tail 100 lines)",
        rationale="Current logs show active errors or failure patterns",
    ),
    CheckDefinition(
        check_id="pod_previous_logs_tail",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Read previous container logs (tail 100 lines, previous=true)",
        rationale="Previous logs show the error that caused container restart",
    ),
    CheckDefinition(
        check_id="pod_probe_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get readiness and liveness probe status",
        rationale="Probe failures prevent pod from serving traffic or cause restarts",
    ),
    CheckDefinition(
        check_id="pod_resource_request_limit_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get container resource requests and limits",
        rationale="Resource constraints may cause OOMKilled or throttling",
    ),
]


# =============================================================================
# Deployment/ReplicaSet checks
# =============================================================================

DEPLOYMENT_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="deployment_condition_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get deployment conditions (Available, Progressing, ReplicaFailure)",
        rationale="Deployment conditions reveal why deployment is not ready",
    ),
    CheckDefinition(
        check_id="deployment_replica_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get desired vs available replica count",
        rationale="Replica mismatch shows the primary impact of the issue",
    ),
    CheckDefinition(
        check_id="deployment_selector_match_summary",
        kind="read_only_kubernetes",
        cost="medium",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Check if deployment selector matches pod labels",
        rationale="Selector mismatch prevents pods from being managed",
    ),
    CheckDefinition(
        check_id="replicaset_owner_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="low",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get ReplicaSet owner reference (Deployment)",
        rationale="Identifies parent Deployment of ReplicaSet",
    ),
]


# =============================================================================
# Service checks
# =============================================================================

SERVICE_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="service_selector_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get service selector and matching endpoint count",
        rationale="Selector issues prevent traffic routing",
    ),
    CheckDefinition(
        check_id="endpoint_slice_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get EndpointSlice addresses for service",
        rationale="Missing endpoints indicate pods not ready for traffic",
    ),
]


# =============================================================================
# Storage checks
# =============================================================================

STORAGE_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="pvc_status_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get PVC status (Pending, Bound, Lost)",
        rationale="PVC issues block pod scheduling or startup",
    ),
    CheckDefinition(
        check_id="pv_binding_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=False,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get PV binding information",
        rationale="Shows PV-PVC binding status and storage class",
    ),
    CheckDefinition(
        check_id="storageclass_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="low",
        requires_namespace=False,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get StorageClass configuration",
        rationale="StorageClass issues affect dynamic provisioning",
    ),
    CheckDefinition(
        check_id="pvc_recent_events",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get PVC-related events",
        rationale="Events reveal provisioning failures or storage issues",
    ),
]


# =============================================================================
# Node checks
# =============================================================================

NODE_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="node_condition_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=False,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=True,
        description="Get node conditions (Ready, MemoryPressure, DiskPressure, PIDPressure)",
        rationale="Node conditions explain why pods cannot be scheduled",
    ),
    CheckDefinition(
        check_id="node_pressure_summary",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=False,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=True,
        description="Get node allocatable resources and capacity",
        rationale="Resource pressure explains scheduling failures",
    ),
    CheckDefinition(
        check_id="node_recent_warning_events",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="high",
        requires_namespace=False,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=True,
        description="Get node-specific warning events",
        rationale="Node events reveal hardware or system issues",
    ),
]


# =============================================================================
# Alertmanager context checks
# =============================================================================

ALERTMANAGER_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="alert_fingerprint_context",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=False,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get related alerts with same fingerprint",
        rationale="Alert fingerprints group related incidents",
    ),
    CheckDefinition(
        check_id="related_alerts_same_namespace",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=False,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get alerts firing in same namespace",
        rationale="Related alerts may share common cause",
    ),
    CheckDefinition(
        check_id="related_alerts_same_object",
        kind="read_only_kubernetes",
        cost="low",
        expected_value="medium",
        requires_namespace=True,
        requires_object_name=True,
        requires_pod_name=False,
        requires_node_name=False,
        description="Get alerts firing for same object",
        rationale="Multiple alerts on same object may indicate cascading failure",
    ),
]


# =============================================================================
# All checks
# =============================================================================

ALL_CHECKS: tuple[CheckDefinition, ...] = tuple(
    GENERIC_CHECKS
    + POD_CHECKS
    + DEPLOYMENT_CHECKS
    + SERVICE_CHECKS
    + STORAGE_CHECKS
    + NODE_CHECKS
    + ALERTMANAGER_CHECKS
)


__all__ = [
    "GENERIC_CHECKS",
    "POD_CHECKS",
    "DEPLOYMENT_CHECKS",
    "SERVICE_CHECKS",
    "STORAGE_CHECKS",
    "NODE_CHECKS",
    "ALERTMANAGER_CHECKS",
    "ALL_CHECKS",
]

"""Read-only check catalog for automatic diagnosis loop.

This module provides:
- CheckDefinition: Individual check specification
- CheckCatalog: Catalog of all available read-only checks
- select_checks(): Select checks based on cost, value, and hypothesis targeting

Design constraints:
- All checks are read-only (list, get, logs with tail limits)
- No mutation, no exec, no kubectl shell
- Bounded timeouts and result sizes
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"

# =============================================================================
# Check Cost and Value
# =============================================================================


class CheckCost(StrEnum):
    """Check execution cost."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckExpectedValue(StrEnum):
    """Expected discriminative value of check result."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Check Definition
# =============================================================================


@dataclass(frozen=True)
class CheckDefinition:
    """Definition of a read-only check.

    Each check must declare:
    - id: Unique check identifier
    - kind: Always "read_only_kubernetes"
    - cost: LOW|MEDIUM|HIGH
    - expected_value: LOW|MEDIUM|HIGH
    - required_identity: What identity parameters are needed
    - handler: Handler function (for fake runner compatibility)
    - timeout: Maximum execution time in seconds
    - result_bound: Maximum result size
    """

    check_id: str
    kind: str  # Always "read_only_kubernetes"
    cost: str  # LOW|MEDIUM|HIGH
    expected_value: str  # LOW|MEDIUM|HIGH
    requires_namespace: bool
    requires_object_name: bool
    requires_pod_name: bool
    requires_node_name: bool
    description: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "check_id": self.check_id,
            "kind": self.kind,
            "cost": self.cost,
            "expected_value": self.expected_value,
            "requires": {
                "namespace": self.requires_namespace,
                "object_name": self.requires_object_name,
                "pod_name": self.requires_pod_name,
                "node_name": self.requires_node_name,
            },
            "description": self.description,
            "rationale": self.rationale,
        }

    def can_execute_with(self, **identity: bool | str | None) -> bool:
        """Check if this check can execute with given identity."""
        if self.requires_namespace and not identity.get("namespace"):
            return False
        if self.requires_object_name and not identity.get("object_name"):
            return False
        if self.requires_pod_name and not identity.get("pod_name"):
            return False
        if self.requires_node_name and not identity.get("node_name"):
            return False
        return True


# =============================================================================
# Check Catalog
# =============================================================================


# Generic checks
_GENERIC_CHECKS: list[CheckDefinition] = [
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

# Pod checks
_POD_CHECKS: list[CheckDefinition] = [
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

# Deployment/ReplicaSet checks
_DEPLOYMENT_CHECKS: list[CheckDefinition] = [
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

# Service checks
_SERVICE_CHECKS: list[CheckDefinition] = [
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

# Storage checks
_STORAGE_CHECKS: list[CheckDefinition] = [
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

# Node checks
_NODE_CHECKS: list[CheckDefinition] = [
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

# Alertmanager context checks
_ALERTMANAGER_CHECKS: list[CheckDefinition] = [
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

# All checks
ALL_CHECKS: tuple[CheckDefinition, ...] = tuple(
    _GENERIC_CHECKS
    + _POD_CHECKS
    + _DEPLOYMENT_CHECKS
    + _SERVICE_CHECKS
    + _STORAGE_CHECKS
    + _NODE_CHECKS
    + _ALERTMANAGER_CHECKS
)

# Check lookup by ID
CHECK_BY_ID: dict[str, CheckDefinition] = {c.check_id: c for c in ALL_CHECKS}


# =============================================================================
# Check Selection
# =============================================================================


def select_checks(
    hypotheses: list[dict[str, Any]],
    available_identity: dict[str, str | None],
    max_checks: int = 3,
) -> list[CheckDefinition]:
    """Select checks based on cost, value, and hypothesis targeting.

    Selection criteria:
    1. Highest expected_value first
    2. Lowest cost
    3. Targets top-ranked hypothesis
    4. Has bounded implementation (in catalog)
    5. Has required identity

    Args:
        hypotheses: List of hypothesis dicts with 'hypothesis_id', 'rank', 'next_best_check'
        available_identity: Available identity (namespace, object_name, pod_name, node_name)
        max_checks: Maximum number of checks to select

    Returns:
        List of selected CheckDefinition objects
    """
    selected: list[CheckDefinition] = []

    # Build set of suggested check IDs from hypotheses
    suggested_ids: set[str] = set()
    for h in hypotheses:
        next_check = h.get("next_best_check")
        if next_check:
            suggested_ids.add(next_check)

    # Sort criteria: prefer suggested > high value > low cost
    def sort_key(check: CheckDefinition) -> tuple[int, int, int]:
        # Suggested by hypothesis (lower = more preferred)
        suggested_rank = 0 if check.check_id in suggested_ids else 1

        # Expected value (high = more preferred, so invert)
        value_order = {"high": 0, "medium": 1, "low": 2}
        value_rank = value_order.get(check.expected_value, 2)

        # Cost (low = more preferred, so invert)
        cost_order = {"low": 0, "medium": 1, "high": 2}
        cost_rank = cost_order.get(check.cost, 2)

        return (suggested_rank, value_rank, cost_rank)

    # Filter and sort checks
    candidate_checks = [
        c for c in ALL_CHECKS
        if c.can_execute_with(**available_identity)
    ]
    candidate_checks.sort(key=sort_key)

    # Select top checks
    for check in candidate_checks:
        if len(selected) >= max_checks:
            break
        selected.append(check)

    return selected


# =============================================================================
# Evidence Delta Builder
# =============================================================================


def build_evidence_delta(
    check_id: str,
    check_result: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build evidence delta from check result.

    Args:
        check_id: The check that was executed
        check_result: Result from the check runner
        hypotheses: Current hypotheses

    Returns:
        Evidence delta dict with check_id, summary, and signal interpretations
    """
    # Extract summary
    summary = check_result.get("summary", "")
    if not summary:
        # Build from evidence
        evidence = check_result.get("evidence", {})
        summary = evidence.get("summary", str(evidence)[:200])

    # Determine signal impact
    signal_indicators = []
    summary_lower = summary.lower()

    # Generic signal detection
    if "warning" in summary_lower or "error" in summary_lower:
        signal_indicators.append("signal:warning_or_error_detected")
    if "not ready" in summary_lower or "unready" in summary_lower:
        signal_indicators.append("signal:readiness_failure")
    if "crashloop" in summary_lower or "crash" in summary_lower:
        signal_indicators.append("signal:crash_detected")
    if "imagepull" in summary_lower or "pull" in summary_lower:
        signal_indicators.append("signal:image_pull_issue")
    if "pending" in summary_lower or "unschedulable" in summary_lower:
        signal_indicators.append("signal:scheduling_failure")
    if "oom" in summary_lower or "killed" in summary_lower:
        signal_indicators.append("signal:memory_pressure")

    return {
        "check_id": check_id,
        "summary": summary[:500],  # Bound summary
        "signal_indicators": signal_indicators,
        "result_keys": list(check_result.keys())[:10],  # Bound keys
    }


__all__ = [
    "SCHEMA_VERSION",
    "CheckCost",
    "CheckExpectedValue",
    "CheckDefinition",
    "ALL_CHECKS",
    "CHECK_BY_ID",
    "select_checks",
    "build_evidence_delta",
]

#!/usr/bin/env python3
"""Rollout state classification for CNPG Live Lab.

This module contains the main classify_rollout_state function that
coordinates all rollout checks and returns a RolloutResult.
"""

from __future__ import annotations

import json
from typing import Any

from .k9b_cnpg_live_lab_constants import (
    FAILURE_CRASH_LOOP,
    FAILURE_DEPLOYMENT_PROGRESS_DEADLINE,
    FAILURE_DEPLOYMENT_REPLICA_FAILURE,
    FAILURE_FAILED_SCHEDULING,
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_PVC_PENDING,
    FAILURE_READINESS_PROBE_FAILED,
)
from .k9b_cnpg_live_lab_rollout_deploy import (
    _check_deployment_progress_deadline_from_json,
    _check_deployment_replica_failure_from_json,
    _check_pvc_pending_from_json,
)
from .k9b_cnpg_live_lab_rollout_events import (
    _check_failed_scheduling_from_events,
    _check_readiness_probe_failed_from_events,
    _detect_transient_volume_binding_conflict,
)
from .k9b_cnpg_live_lab_rollout_pods import (
    _check_crash_loop_from_pods,
    _check_failed_scheduling_from_pods,
    _check_image_pull_backoff_from_pods,
    _check_readiness_probe_failed_from_pods,
)
from .k9b_cnpg_live_lab_rollout_types import RolloutResult


def classify_rollout_state(
    pods_json: str,
    deployments_json: str,
    pvc_json: str,
    events_text: str,
    events_json: str = "",
    storage_class_json: str = "",
    storage_class_available: bool = True,
) -> RolloutResult:
    """Classify rollout state based on JSON inputs.

    Args:
        pods_json: JSON string of pods list
        deployments_json: JSON string of deployments list
        pvc_json: JSON string of PVCs list
        events_text: Plain text events (ignored, use events_json)
        events_json: JSON string of events list (optional for backward compatibility)
        storage_class_json: JSON string of storage class list (optional for extended checks)
        storage_class_available: Whether storage class is available (optional for backward compatibility)

    Returns:
        RolloutResult with fatal, failure_class, and diagnostics
    """
    diagnostics: dict[str, Any] = {}

    # Check for transient VolumeBinding conflict first (nonfatal - diagnostic only)
    # This is recorded as evidence but does NOT short-circuit other checks
    is_transient, transient_msg, transient_pod = _detect_transient_volume_binding_conflict(events_json)
    if is_transient:
        diagnostics["transient_volume_binding_conflict"] = True
        diagnostics["transient_volume_binding_message"] = transient_msg
        diagnostics["transient_volume_binding_pod"] = transient_pod
        # DO NOT return early - continue to check for actual failures

    # Priority order for fatal failures
    # 1. Check for missing deployments first - this catches the case where rendered
    #    chart has multiple workloads but cluster has zero deployments
    deployments_data = json.loads(deployments_json) if deployments_json else {}
    deployment_items = deployments_data.get("items", []) if isinstance(deployments_data, dict) else []
    if not deployment_items:
        # No deployments found in cluster - this is a fatal condition
        diagnostics["expected_deployment_missing"] = True
        return RolloutResult(
            fatal=True,
            failure_class="expected_deployment_missing",
            diagnostics=diagnostics,
        )

    # 2. Image pull backoff
    image_pull_affected = _check_image_pull_backoff_from_pods(pods_json)
    if image_pull_affected:
        affected_pods = [item["pod"] for item in image_pull_affected]
        diagnostics["image_pull_backoff"] = image_pull_affected
        return RolloutResult(
            fatal=True,
            failure_class=FAILURE_IMAGE_PULL_BACKOFF,
            diagnostics=diagnostics,
            affected_pods=affected_pods,
        )

    # 2. Crash loop
    crash_loop_affected = _check_crash_loop_from_pods(pods_json)
    if crash_loop_affected:
        affected_pods = [item["pod"] for item in crash_loop_affected]
        pod_phase = crash_loop_affected[0].get("phase", "CrashLoopBackOff") if crash_loop_affected else ""
        diagnostics["crash_loop"] = crash_loop_affected
        return RolloutResult(
            fatal=True,
            failure_class=FAILURE_CRASH_LOOP,
            diagnostics=diagnostics,
            affected_pods=affected_pods,
            pod_phase=pod_phase,
        )

    # 3. Failed scheduling from events
    sched_fatal, sched_reason, sched_msg = _check_failed_scheduling_from_events(events_json)
    if sched_fatal:
        diagnostics["failed_scheduling_reason"] = sched_reason
        diagnostics["failed_scheduling_message"] = sched_msg
        return RolloutResult(fatal=True, failure_class=FAILURE_FAILED_SCHEDULING, diagnostics=diagnostics)

    # 4. Failed scheduling from pods (fallback)
    scheduling_affected = _check_failed_scheduling_from_pods(pods_json)
    if scheduling_affected:
        diagnostics["failed_scheduling_pods"] = scheduling_affected
        return RolloutResult(fatal=True, failure_class=FAILURE_FAILED_SCHEDULING, diagnostics=diagnostics)

    # 5. Readiness probe failed from events
    probe_fatal, probe_reason, probe_msg = _check_readiness_probe_failed_from_events(events_json)
    if probe_fatal:
        diagnostics["readiness_probe_reason"] = probe_reason
        diagnostics["readiness_probe_message"] = probe_msg
        return RolloutResult(fatal=True, failure_class=FAILURE_READINESS_PROBE_FAILED, diagnostics=diagnostics)

    # 6. Readiness probe failed from pods (fallback) - includes ContainersNotReady waiting reason
    probe_affected = _check_readiness_probe_failed_from_pods(pods_json)
    if probe_affected:
        affected_pods = [item["pod"] for item in probe_affected]
        diagnostics["readiness_probe"] = probe_affected
        return RolloutResult(
            fatal=True,
            failure_class=FAILURE_READINESS_PROBE_FAILED,
            diagnostics=diagnostics,
            affected_pods=affected_pods,
        )

    # 7. PVC pending
    pvc_affected = _check_pvc_pending_from_json(pvc_json)
    if pvc_affected:
        diagnostics["pvc_pending"] = pvc_affected
        return RolloutResult(fatal=True, failure_class=FAILURE_PVC_PENDING, diagnostics=diagnostics)

    # 8. Deployment replica failure
    replica_failure_affected = _check_deployment_replica_failure_from_json(deployments_json)
    if replica_failure_affected:
        diagnostics["deployment_replica_failure"] = replica_failure_affected
        return RolloutResult(fatal=True, failure_class=FAILURE_DEPLOYMENT_REPLICA_FAILURE, diagnostics=diagnostics)

    # 9. Deployment progress deadline
    progress_deadline_affected = _check_deployment_progress_deadline_from_json(deployments_json)
    if progress_deadline_affected:
        diagnostics["deployment_progress_deadline"] = progress_deadline_affected
        return RolloutResult(fatal=True, failure_class=FAILURE_DEPLOYMENT_PROGRESS_DEADLINE, diagnostics=diagnostics)

    # No issues detected
    return RolloutResult(fatal=False, failure_class="", diagnostics=diagnostics)


def _format_bounded_summary(
    checks: dict[str, list[dict[str, Any]]],
    failure_class: str,
) -> str:
    """Format a bounded summary of check results."""
    lines = ["### Rollout Check Summary", ""]
    if failure_class:
        lines.append(f"**Failure Class**: `{failure_class}`")
        lines.append("")
    lines.append("| Check | Affected |")
    lines.append("|-------|----------|")
    total = sum(len(v) for v in checks.values())
    for name, items in checks.items():
        lines.append(f"| {name} | {len(items)} |")
    lines.append("")
    lines.append(f"**Total affected**: {total}")
    return "\n".join(lines)

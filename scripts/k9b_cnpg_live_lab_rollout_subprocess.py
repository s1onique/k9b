#!/usr/bin/env python3
"""Subprocess-based rollout check functions for CNPG Live Lab.

This module contains subprocess-based check functions and snapshot collection.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .k9b_cnpg_live_lab_rollout_classify import classify_rollout_state
from .k9b_cnpg_live_lab_rollout_deploy import (
    _check_deployment_complete_from_json,
    _check_deployment_progress_deadline_from_json,
    _check_deployment_replica_failure_from_json,
    _check_pvc_pending_from_json,
)
from .k9b_cnpg_live_lab_rollout_pods import (
    _check_crash_loop_from_pods,
    _check_failed_scheduling_from_pods,
    _check_image_pull_backoff_from_pods,
    _check_readiness_probe_failed_from_pods,
)


def _check_image_pull_backoff(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any pods are in ImagePullBackOff state (subprocess-based)."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return _check_image_pull_backoff_from_pods(result.stdout)


def _check_crash_loop(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any pods are in CrashLoopBackOff state (subprocess-based)."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return _check_crash_loop_from_pods(result.stdout)


def _check_failed_scheduling(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any pods have failed scheduling (subprocess-based)."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return _check_failed_scheduling_from_pods(result.stdout)


def _check_readiness_probe_failed(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if readiness probes have failed (subprocess-based)."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return _check_readiness_probe_failed_from_pods(result.stdout)


def _check_pvc_pending(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any PVCs are stuck in Pending state (subprocess-based)."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "pvc", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return _check_pvc_pending_from_json(result.stdout)


def _check_deployment_replica_failure(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any deployment replicas have failed (subprocess-based)."""
    return _check_deployment_replica_failure_from_json(json.dumps({"items": deployments}))


def _check_deployment_progress_deadline(
    kubeconfig: str,
    namespace: str,
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check if any deployment has exceeded progress deadline (subprocess-based)."""
    return _check_deployment_progress_deadline_from_json(json.dumps({"items": deployments}))


def _check_rollout_success(
    kubeconfig: str,
    namespace: str,
    release: str,
    target_count: int = 1,
) -> tuple[bool, str]:
    """Check if rollout succeeded - all replicas are ready (subprocess-based).

    DEPRECATED: Use _check_rollout_success_multi() instead for multi-deployment charts.
    This function only checks for a single deployment named `release`.
    """
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "deployments", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, f"kubectl failed: {result.stderr}"

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "Failed to parse deployment JSON"

    for deploy in data.get("items", []):
        deploy_name = deploy.get("metadata", {}).get("name", "")
        if deploy_name == release:
            status = deploy.get("status", {})
            replicas = status.get("replicas", 0)
            available = status.get("availableReplicas", 0)
            ready = status.get("readyReplicas", 0)
            if available >= target_count and ready >= target_count:
                return True, f"Deployment {release} is healthy"
            return False, f"Deployment {release} not ready: {ready}/{replicas} ready, {available} available"

    return False, f"Deployment {release} not found"


def _check_rollout_success_multi(
    kubeconfig: str,
    namespace: str,
    expected_deployments: list[str],
    target_count: int = 1,
) -> tuple[bool, str]:
    """Check if rollout succeeded for multiple expected deployments.

    Uses strict rollout-complete semantics:
    - observedGeneration >= generation
    - updatedReplicas >= desired_replicas
    - availableReplicas >= desired_replicas
    - No old replicas remain
    - unavailableReplicas == 0 (when present)

    Only checks the deployments specified in expected_deployments, not all
    deployments in the namespace.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        expected_deployments: List of expected deployment names
        target_count: Expected replica count per deployment

    Returns:
        Tuple of (success, status_message)
    """
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "deployments", "-n", namespace, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, f"kubectl failed: {result.stderr}"

    deployments_json = result.stdout

    # Parse and filter to only expected deployments
    try:
        data = json.loads(deployments_json)
    except json.JSONDecodeError:
        return False, "Failed to parse deployment JSON"

    expected_set = set(expected_deployments)
    filtered_items = [
        deploy for deploy in data.get("items", [])
        if deploy.get("metadata", {}).get("name", "") in expected_set
    ]

    # Check for missing expected deployments
    cluster_names = {deploy.get("metadata", {}).get("name", "") for deploy in filtered_items}
    missing = [name for name in expected_deployments if name not in cluster_names]
    if missing:
        return False, f"Expected deployment(s) not found: {', '.join(missing)}"

    # Check completion only for filtered (expected) deployments
    filtered_json = json.dumps({"items": filtered_items})
    all_complete, states, summary = _check_deployment_complete_from_json(filtered_json)

    if not all_complete:
        return False, summary

    return True, summary


def _collect_rollout_snapshot(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    release: str,
    snapshot_ts: str,
) -> dict[str, Any] | None:
    """Collect a snapshot of rollout state."""
    try:
        pods_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True, text=True,
        )
        pods_json = pods_result.stdout if pods_result.returncode == 0 else "{}"

        deploys_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "deployments", "-n", namespace, "-o", "json"],
            capture_output=True, text=True,
        )
        deploys_json = deploys_result.stdout if deploys_result.returncode == 0 else "{}"

        events_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "-o", "json"],
            capture_output=True, text=True,
        )
        events_json = events_result.stdout if events_result.returncode == 0 else "{}"
        events_text = events_result.stdout if events_result.returncode == 0 else ""

        pvcs_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "pvc", "-n", namespace, "-o", "json"],
            capture_output=True, text=True,
        )
        pvcs_json = pvcs_result.stdout if pvcs_result.returncode == 0 else "{}"

        result = classify_rollout_state(pods_json, deploys_json, pvcs_json, events_text, events_json)

        return {
            "timestamp": snapshot_ts,
            "namespace": namespace,
            "release": release,
            "rollout_checks": {
                "fatal": result.fatal,
                "failure_class": result.failure_class,
                "diagnostics": result.diagnostics,
            },
            "rollout_success": _check_rollout_success(kubeconfig, namespace, release) == (True, ""),
        }
    except Exception:
        return None

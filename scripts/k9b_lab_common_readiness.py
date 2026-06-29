#!/usr/bin/env python3
"""Common readiness and artifact collection helpers for k9b live labs.

This module provides reusable functions for:
- Waiting for deployments to be ready
- Collecting namespace snapshots (pods, services, events, etc.)
- Collecting pod logs (current and previous)
- Collecting events sorted by timestamp
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import (
    error,
    kubectl_describe,
    kubectl_events,
    kubectl_json,
    kubectl_logs,
    log,
    write_json_artifact,
    write_text_artifact,
)

# =============================================================================
# Readiness helpers
# =============================================================================

def _classify_deployment_lookup_failure(kubeconfig: str, namespace: str, deployment: str) -> str:
    """Classify why kubectl failed to get a deployment.

    Returns a human-readable status string that distinguishes:
    - missing (404): deployment doesn't exist
    - api_forbidden (403): RBAC issues
    - api_unauthorized (401): auth issues
    - api_timeout: kubectl command timed out
    - api_error:code: other API errors

    This helps operators quickly identify whether a deployment name is wrong
    (missing) vs. a real infrastructure problem (RBAC/auth issues).
    """
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "deployment", deployment, "-n", namespace]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except subprocess.TimeoutExpired:
        return "api_timeout"

    if result.returncode == 0:
        return "api_error"  # Unexpected success after initial failure

    stderr_lower = result.stderr.lower()

    # 404 = deployment doesn't exist (wrong name or not yet created)
    if "not found" in stderr_lower or result.returncode == 404:
        return "missing"

    # 403 = RBAC issues
    if "forbidden" in stderr_lower or result.returncode == 403:
        return "api_forbidden"

    # 401 = auth issues
    if "unauthorized" in stderr_lower or result.returncode == 401:
        return "api_unauthorized"

    # Generic API error
    return f"api_error:{result.returncode}"


def wait_for_deployments_ready(
    kubeconfig: str,
    namespace: str,
    deployments: list[str],
    timeout_seconds: int = 300,
    poll_interval: int = 15,
) -> tuple[bool, str]:
    """Wait for specified deployments to have all replicas ready.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        deployments: List of deployment names to wait for
        timeout_seconds: Maximum time to wait
        poll_interval: Polling interval in seconds
        
    Returns:
        Tuple of (success, status_message)
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        all_ready = True
        not_ready_deployments = []
        
        for deployment in deployments:
            result = kubectl_json(kubeconfig, f"deployment/{deployment}", namespace)
            if not result.success or not result.data:
                all_ready = False
                # Classify the failure to provide better diagnostics
                failure_type = _classify_deployment_lookup_failure(kubeconfig, namespace, deployment)
                not_ready_deployments.append(f"{deployment}({failure_type})")
                continue
                
            status = result.data.get("status", {})
            ready_replicas = status.get("readyReplicas", 0)
            replicas = status.get("replicas", 1)
            
            # Handle cases where status is not yet populated
            if replicas == 0:
                all_ready = False
                not_ready_deployments.append(f"{deployment}(0 replicas)")
            elif ready_replicas < replicas:
                all_ready = False
                not_ready_deployments.append(f"{deployment}({ready_replicas}/{replicas})")
        
        if all_ready:
            elapsed = int(time.time() - start_time)
            return True, f"All {len(deployments)} deployments ready after {elapsed}s"
        
        elapsed = int(time.time() - start_time)
        log(f"[{elapsed}s] Waiting for deployments: {', '.join(not_ready_deployments)}")
        time.sleep(poll_interval)
    
    elapsed = int(time.time() - start_time)
    return False, f"Timeout after {elapsed}s waiting for: {', '.join(not_ready_deployments)}"


def check_deployment_ready(
    kubeconfig: str,
    namespace: str,
    deployment: str,
) -> tuple[bool, dict[str, Any]]:
    """Check if a single deployment is ready.
    
    Returns:
        Tuple of (is_ready, status_dict)
    """
    result = kubectl_json(kubeconfig, f"deployment/{deployment}", namespace)
    if not result.success or not result.data:
        return False, {"error": "deployment not found or API error"}
    
    status = result.data.get("status", {})
    ready_replicas = status.get("readyReplicas", 0)
    replicas = status.get("replicas", 1)
    updated_replicas = status.get("updatedReplicas", 0)
    available_replicas = status.get("availableReplicas", 0)
    
    is_ready = ready_replicas >= replicas and updated_replicas >= replicas
    
    return is_ready, {
        "replicas": replicas,
        "readyReplicas": ready_replicas,
        "updatedReplicas": updated_replicas,
        "availableReplicas": available_replicas,
        "is_ready": is_ready,
    }


def get_deployment_status(
    kubeconfig: str,
    namespace: str,
    deployment: str,
) -> dict[str, Any]:
    """Get detailed deployment status."""
    result = kubectl_json(kubeconfig, f"deployment/{deployment}", namespace)
    if not result.success or not result.data:
        return {"error": "deployment not found or API error"}
    
    status = result.data.get("status", {})
    conditions = status.get("conditions", [])
    
    return {
        "readyReplicas": status.get("readyReplicas", 0),
        "replicas": status.get("replicas", 0),
        "updatedReplicas": status.get("updatedReplicas", 0),
        "availableReplicas": status.get("availableReplicas", 0),
        "conditions": [
            {"type": c.get("type"), "status": c.get("status"), "reason": c.get("reason")}
            for c in conditions
        ],
    }


# =============================================================================
# Artifact collection helpers
# =============================================================================

def collect_namespace_snapshot(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    include_previous_logs: bool = True,
) -> dict[str, Path]:
    """Collect a complete namespace snapshot for diagnostics.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        artifact_dir: Directory to write artifacts
        include_previous_logs: Whether to include previous (crashed) container logs
        
    Returns:
        Dictionary mapping artifact names to paths
    """
    artifacts: dict[str, Path] = {}
    snapshot_dir = artifact_dir / "namespace-snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    log(f"Collecting namespace snapshot for {namespace}")
    
    # Collect pods
    pods_result = kubectl_json(kubeconfig, "pods", namespace)
    if pods_result.success:
        pods_path = write_json_artifact(snapshot_dir, "pods.json", pods_result.data or {})
        artifacts["pods"] = pods_path
        log(f"  - Collected pods: {len(pods_result.data.get('items', []) if pods_result.data else [])} items")
    else:
        write_text_artifact(snapshot_dir, "pods-error.txt", pods_result.stderr)
        artifacts["pods_error"] = snapshot_dir / "pods-error.txt"
    
    # Collect services
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    if svc_result.success:
        svc_path = write_json_artifact(snapshot_dir, "services.json", svc_result.data or {})
        artifacts["services"] = svc_path
        log(f"  - Collected services: {len(svc_result.data.get('items', []) if svc_result.data else [])} items")
    else:
        write_text_artifact(snapshot_dir, "services-error.txt", svc_result.stderr)
        artifacts["services_error"] = snapshot_dir / "services-error.txt"
    
    # Collect deployments
    deploy_result = kubectl_json(kubeconfig, "deployments", namespace)
    if deploy_result.success:
        deploy_path = write_json_artifact(snapshot_dir, "deployments.json", deploy_result.data or {})
        artifacts["deployments"] = deploy_path
        log(f"  - Collected deployments: {len(deploy_result.data.get('items', []) if deploy_result.data else [])} items")
    else:
        write_text_artifact(snapshot_dir, "deployments-error.txt", deploy_result.stderr)
        artifacts["deployments_error"] = snapshot_dir / "deployments-error.txt"
    
    # Collect events
    events_result = kubectl_events(kubeconfig, namespace)
    if events_result.success:
        events_path = write_text_artifact(snapshot_dir, "events.txt", events_result.stdout)
        artifacts["events"] = events_path
        log("  - Collected events")
    else:
        write_text_artifact(snapshot_dir, "events-error.txt", events_result.stderr)
        artifacts["events_error"] = snapshot_dir / "events-error.txt"
    
    # Collect pod logs and previous logs for crash investigation
    if pods_result.success and pods_result.data:
        pods = pods_result.data.get("items", [])
        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")
            if not pod_name:
                continue
                
            pod_dir = snapshot_dir / "pod-logs" / pod_name
            pod_dir.mkdir(parents=True, exist_ok=True)
            
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                container_name = cs.get("name", "")
                if not container_name:
                    continue
                
                # Collect current logs
                logs_result = kubectl_logs(kubeconfig, pod_name, namespace, container_name)
                if logs_result.success:
                    log_path = pod_dir / f"{container_name}-current.log"
                    log_path.write_text(logs_result.stdout)
                    artifacts[f"pod-log-{pod_name}-{container_name}"] = log_path
                
                # Collect previous logs if container has restart count
                restart_count = cs.get("restartCount", 0)
                if include_previous_logs and restart_count > 0:
                    prev_result = kubectl_logs(kubeconfig, pod_name, namespace, container_name, previous=True)
                    if prev_result.success:
                        prev_path = pod_dir / f"{container_name}-previous.log"
                        prev_path.write_text(prev_result.stdout)
                        artifacts[f"pod-prev-log-{pod_name}-{container_name}"] = prev_path
    
    # Collect pod describe for each pod (for detailed state)
    if pods_result.success and pods_result.data:
        pods = pods_result.data.get("items", [])
        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")
            if not pod_name:
                continue
            
            describe_result = kubectl_describe(kubeconfig, "pod", pod_name, namespace)
            if describe_result.success:
                pod_dir = snapshot_dir / "pod-describe"
                pod_dir.mkdir(parents=True, exist_ok=True)
                desc_path = pod_dir / f"{pod_name}.txt"
                desc_path.write_text(describe_result.stdout)
                artifacts[f"pod-describe-{pod_name}"] = desc_path
    
    # Write metadata
    metadata = {
        "namespace": namespace,
        "collection_time": time.time(),
        "artifacts_collected": len(artifacts),
        "artifact_names": list(artifacts.keys()),
    }
    metadata_path = write_json_artifact(snapshot_dir, "metadata.json", metadata)
    artifacts["metadata"] = metadata_path
    
    log(f"Namespace snapshot complete: {len(artifacts)} artifacts in {snapshot_dir}")
    return artifacts


def collect_pod_logs(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
    artifact_dir: Path,
    include_previous: bool = True,
) -> dict[str, Path]:
    """Collect logs for a specific pod.
    
    Returns:
        Dictionary mapping artifact names to paths
    """
    artifacts: dict[str, Path] = {}
    log_dir = artifact_dir / "pod-logs" / pod_name
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get pod JSON to find container names
    pod_result = kubectl_json(kubeconfig, f"pod/{pod_name}", namespace)
    if not pod_result.success or not pod_result.data:
        error(f"Failed to get pod {pod_name}: {pod_result.stderr}")
        return artifacts
    
    container_statuses = pod_result.data.get("status", {}).get("containerStatuses", [])
    container_names = [cs.get("name", "") for cs in container_statuses if cs.get("name")]
    
    # If no container statuses, try to get container spec
    if not container_names:
        containers = pod_result.data.get("spec", {}).get("containers", [])
        container_names = [c.get("name", "") for c in containers if c.get("name")]
    
    for container_name in container_names:
        # Current logs
        logs_result = kubectl_logs(kubeconfig, pod_name, namespace, container_name)
        if logs_result.success:
            log_path = log_dir / f"{container_name}-current.log"
            log_path.write_text(logs_result.stdout)
            artifacts[f"{container_name}-current"] = log_path
        
        # Previous logs
        if include_previous:
            prev_result = kubectl_logs(kubeconfig, pod_name, namespace, container_name, previous=True)
            if prev_result.success and prev_result.stdout:
                prev_path = log_dir / f"{container_name}-previous.log"
                prev_path.write_text(prev_result.stdout)
                artifacts[f"{container_name}-previous"] = prev_path
    
    return artifacts


def collect_events_sorted(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
) -> Path:
    """Collect events sorted by last timestamp."""
    events_dir = artifact_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    
    # Get events sorted by lastTimestamp
    result = kubectl_events(kubeconfig, namespace, sort_by=".lastTimestamp")
    
    if result.success:
        events_path = write_text_artifact(events_dir, "sorted-events.txt", result.stdout)
        log(f"Collected {len(result.stdout.splitlines())} events to {events_path}")
        return events_path
    
    error(f"Failed to collect events: {result.stderr}")
    return events_dir / "events-error.txt"


def collect_configmap(
    kubeconfig: str,
    namespace: str,
    configmap_name: str,
    artifact_dir: Path,
) -> dict[str, Any] | None:
    """Collect a ConfigMap for artifact inspection.
    
    Returns:
        ConfigMap data dict or None if not found
    """
    result = kubectl_json(kubeconfig, f"configmap/{configmap_name}", namespace)
    if result.success and result.data:
        cm_path = write_json_artifact(artifact_dir, f"configmap-{configmap_name}.json", result.data)
        log(f"Collected ConfigMap {configmap_name} to {cm_path}")
        return result.data
    
    log(f"ConfigMap {configmap_name} not found or error")
    return None


# =============================================================================
# Re-exports
# =============================================================================

__all__ = [
    "wait_for_deployments_ready",
    "check_deployment_ready",
    "get_deployment_status",
    "collect_namespace_snapshot",
    "collect_pod_logs",
    "collect_events_sorted",
    "collect_configmap",
]

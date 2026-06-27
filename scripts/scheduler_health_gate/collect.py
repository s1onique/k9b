"""Collection module for scheduler health gate.

This module handles all kubectl interactions and Kubernetes data collection.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .contracts import SCHEDULER_DEPLOYMENT_NAME, SCHEDULER_POD_SELECTOR

# =============================================================================
# kubectl helpers
# =============================================================================


def run_kubectl(
    kubeconfig: str,
    namespace: str,
    args: list[str],
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run kubectl command and return (returncode, stdout, stderr)."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "kubectl command timed out"
    except Exception as e:
        return 1, "", str(e)


# =============================================================================
# Deployment collection
# =============================================================================


def get_scheduler_deployment_status(
    kubeconfig: str,
    namespace: str,
) -> dict[str, Any]:
    """Get scheduler deployment status."""
    rc, stdout, _ = run_kubectl(
        kubeconfig, namespace,
        ["get", "deployment", SCHEDULER_DEPLOYMENT_NAME, "-o", "json"]
    )
    
    if rc != 0:
        return {
            "found": False,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "error": "deployment not found",
        }
    
    try:
        data = json.loads(stdout)
        status = data.get("status", {})
        spec_replicas = data.get("spec", {}).get("replicas", 0)
        
        # Get conditions for availability
        conditions = status.get("conditions", [])
        available_condition = None
        for cond in conditions:
            if cond.get("type") == "Available":
                available_condition = cond
                break
        
        return {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "replicas": spec_replicas,
            "ready_replicas": status.get("readyReplicas", 0),
            "available_replicas": status.get("availableReplicas", 0),
            "updated_replicas": status.get("updatedReplicas", 0),
            "available_condition": available_condition,
        }
    except (json.JSONDecodeError, KeyError) as e:
        return {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "error": f"failed to parse deployment status: {e}",
        }


def get_scheduler_pod_selector(
    kubeconfig: str,
    namespace: str,
    deployment_name: str,
) -> str:
    """Derive pod selector from Deployment.spec.selector.
    
    Uses the canonical relationship between Deployment and Pods per Kubernetes model.
    Falls back to hard-coded selector if derivation fails.
    """
    rc, stdout, _ = run_kubectl(
        kubeconfig, namespace,
        ["get", "deployment", deployment_name, "-o", "json"]
    )
    
    if rc != 0:
        return SCHEDULER_POD_SELECTOR
    
    try:
        data = json.loads(stdout)
        selector = data.get("spec", {}).get("selector", {})
        labels = selector.get("matchLabels", {})
        
        if labels:
            selector_parts = [f"{k}={v}" for k, v in sorted(labels.items())]
            return ",".join(selector_parts)
        
        return SCHEDULER_POD_SELECTOR
    except (json.JSONDecodeError, KeyError):
        return SCHEDULER_POD_SELECTOR


# =============================================================================
# Pod collection
# =============================================================================


def get_scheduler_pods(
    kubeconfig: str,
    namespace: str,
    selector: str,
) -> dict[str, Any]:
    """Get scheduler pods with full status.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        selector: Pod selector (derived from Deployment.spec.selector)
    """
    rc, stdout, _ = run_kubectl(
        kubeconfig, namespace,
        ["get", "pods", "-l", selector, "-o", "json"]
    )
    
    if rc != 0:
        return {"items": [], "error": "failed to get scheduler pods"}
    
    try:
        return dict[str, Any](json.loads(stdout))
    except json.JSONDecodeError:
        return {"items": [], "error": "failed to parse pods JSON"}


def collect_scheduler_logs(
    kubeconfig: str,
    namespace: str,
    selector: str,
    tail_lines: int = 100,
) -> dict[str, str]:
    """Collect scheduler logs from all pods.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        selector: Pod selector (derived from Deployment.spec.selector)
        tail_lines: Number of log lines to retrieve
    """
    logs: dict[str, str] = {}
    
    pods_data = get_scheduler_pods(kubeconfig, namespace, selector)
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "unknown")
        
        rc, stdout, _ = run_kubectl(
            kubeconfig, namespace,
            ["logs", f"pod/{pod_name}", "--tail", str(tail_lines)]
        )
        logs[pod_name] = stdout if rc == 0 else f"<logs unavailable: exit code {rc}>"
        
        # Also get previous log if available
        rc_prev, stdout_prev, _ = run_kubectl(
            kubeconfig, namespace,
            ["logs", f"pod/{pod_name}", "--previous", "--tail", str(tail_lines)]
        )
        if rc_prev == 0 and stdout_prev:
            logs[f"{pod_name}.previous"] = stdout_prev
    
    return logs


# =============================================================================
# Events collection
# =============================================================================


def get_namespace_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get recent namespace events related to scheduler."""
    rc, stdout, _ = run_kubectl(
        kubeconfig, namespace,
        ["get", "events", "--sort-by=.lastTimestamp", "-o", "json"]
    )
    
    if rc != 0:
        return []
    
    try:
        data = json.loads(stdout)
        events = data.get("items", [])
        
        # Filter to scheduler-related events
        scheduler_events = [
            e for e in events
            if "scheduler" in e.get("involvedObject", {}).get("name", "").lower()
            or "scheduler" in e.get("reason", "").lower()
        ]
        
        # Return last N events
        return scheduler_events[-limit:]
    except json.JSONDecodeError:
        return []

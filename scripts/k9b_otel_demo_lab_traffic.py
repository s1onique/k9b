#!/usr/bin/env python3
"""Traffic generation for OTel Demo Lab.

In scaffold mode, records traffic plan without generating real traffic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import kubectl_json, log, write_json_artifact
from .k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE


def record_traffic_plan(
    kubeconfig: str,
    artifact_dir: Path,
    duration_seconds: int = 30,
) -> dict[str, Any]:
    """Record traffic generation plan (scaffold mode).
    
    In scaffold mode, this function only records the traffic generation plan
    to artifacts; it does not actually generate real traffic.
    
    Args:
        kubeconfig: Path to kubeconfig
        artifact_dir: Directory to write artifacts
        duration_seconds: Intended traffic generation duration
        
    Returns:
        Traffic plan recording result
    """
    log(f"Recording scaffold traffic plan for {duration_seconds} seconds...")
    
    traffic_dir = artifact_dir / "phase2-injected"
    traffic_dir.mkdir(parents=True, exist_ok=True)
    
    # Find frontend service
    frontend_svc = None
    svc_result = kubectl_json(kubeconfig, "services", OTEL_DEMO_NAMESPACE)
    if svc_result.success and svc_result.data:
        for svc in svc_result.data.get("items", []):
            svc_name = svc.get("metadata", {}).get("name", "")
            if "frontend" in svc_name.lower():
                frontend_svc = svc_name
                break
    
    if not frontend_svc:
        log("Warning: Could not find frontend service for traffic generation")
        return {"error": "frontend service not found"}
    
    # Get frontend pod IP
    frontend_pod_ip = None
    pods_result = kubectl_json(kubeconfig, "pods", OTEL_DEMO_NAMESPACE)
    if pods_result.success and pods_result.data:
        for pod in pods_result.data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "frontend" in pod_name.lower():
                pod_ip = pod.get("status", {}).get("podIP")
                if pod_ip:
                    frontend_pod_ip = pod_ip
                    break
    
    result = {
        "frontend_service": frontend_svc,
        "frontend_pod_ip": frontend_pod_ip,
        "duration_seconds": duration_seconds,
        "started_at": __import__("time").time(),
    }
    
    # Write traffic command info
    traffic_cmd = {
        "command": "generate traffic to frontend",
        "service": frontend_svc,
        "pod_ip": frontend_pod_ip,
        "duration": duration_seconds,
        "note": "Traffic should be generated via curl or load generator",
    }
    write_json_artifact(traffic_dir, "traffic-generator.json", traffic_cmd)
    
    result["note"] = "Scaffold mode - plan recorded only, no actual traffic generated"
    log(f"Traffic plan recorded: {result}")
    return result


def generate_traffic(
    kubeconfig: str,
    artifact_dir: Path,
    duration_seconds: int = 30,
) -> dict[str, Any]:
    """Generate traffic against the frontend to trigger the incident.
    
    .. deprecated::
        Use :func:`record_traffic_plan` instead. This function now delegates
        to record_traffic_plan since scaffold mode only records plans.
    """
    return record_traffic_plan(kubeconfig, artifact_dir, duration_seconds)

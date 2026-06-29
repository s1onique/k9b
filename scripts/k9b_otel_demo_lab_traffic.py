#!/usr/bin/env python3
"""Traffic generation for OTel Demo Lab.

In scaffold mode, records traffic plan without generating real traffic.
In live mode, generates real HTTP traffic via a temporary curl pod.
"""

from __future__ import annotations

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import kubectl_json, log, write_json_artifact
from .k9b_otel_demo_lab_constants import (
    FAILURE_TRAFFIC_TARGET_SERVICE_MISSING,
    OTEL_DEMO_NAMESPACE,
)
from .k9b_otel_frontend_smoke import resolve_service_http_url


def record_traffic_plan(
    kubeconfig: str,
    artifact_dir: Path,
    duration_seconds: int = 30,
) -> dict[str, Any]:
    """Record traffic generation plan (scaffold mode only).
    
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
        return {"mode": "scaffold", "error": "frontend service not found"}
    
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
        "mode": "scaffold",
        "frontend_service": frontend_svc,
        "frontend_pod_ip": frontend_pod_ip,
        "duration_seconds": duration_seconds,
        "started_at": time.time(),
    }
    
    # Write traffic command info
    traffic_cmd = {
        "mode": "scaffold",
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


def _build_frontend_proxy_fqdn(service_name: str, namespace: str) -> str:
    """Build the FQDN for a service in a Kubernetes namespace.
    
    The FQDN format is: service-name.namespace.svc.cluster.local
    
    This ensures the traffic pod (which may run in a different namespace)
    can reach the frontend-proxy service.
    """
    return f"{service_name}.{namespace}.svc.cluster.local"


def _find_frontend_proxy_service(kubeconfig: str, namespace: str) -> str | None:
    """Find the frontend-proxy service name."""
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    if svc_result.success and svc_result.data:
        for svc in svc_result.data.get("items", []):
            svc_name: str = svc.get("metadata", {}).get("name", "") or ""
            if svc_name == "frontend-proxy":
                return svc_name
    return None


def _find_frontend_service(kubeconfig: str, namespace: str) -> str | None:
    """Find the frontend service name."""
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    if svc_result.success and svc_result.data:
        for svc in svc_result.data.get("items", []):
            svc_name: str = svc.get("metadata", {}).get("name", "") or ""
            if svc_name == "frontend":
                return svc_name
    return None


def generate_live_traffic(
    kubeconfig: str,
    artifact_dir: Path,
    namespace: str,
    duration_seconds: int = 600,
    interval_seconds: int = 30,
) -> dict[str, Any]:
    """Generate real HTTP traffic to the frontend (live mode only).
    
    Creates a temporary curl pod that hits the frontend-proxy service repeatedly.
    
    Args:
        kubeconfig: Path to kubeconfig
        artifact_dir: Directory to write artifacts
        namespace: OTel Demo namespace
        duration_seconds: How long to generate traffic
        interval_seconds: Interval between requests
        
    Returns:
        Traffic result with success/failure counts and errors
    """
    traffic_dir = artifact_dir / "phase2-injected"
    traffic_dir.mkdir(parents=True, exist_ok=True)
    
    log(f"Starting live traffic generation for {duration_seconds}s...")
    
    # Resolve frontend-proxy URL from Service (includes port)
    # This ensures the URL includes the correct port (e.g., :8080)
    target_url, target_port, resolve_error = resolve_service_http_url(
        kubeconfig, namespace, "frontend-proxy"
    )
    if resolve_error or not target_url:
        log(f"Warning: Could not resolve frontend-proxy: {resolve_error}")
        result = {
            "mode": "live",
            "error": f"frontend-proxy service resolution failed: {resolve_error}",
            "failure_class": FAILURE_TRAFFIC_TARGET_SERVICE_MISSING,
            "success_count": 0,
            "failure_count": 0,
            "actual_attempts": 0,
            "estimated_attempts": duration_seconds // interval_seconds,
            "summary_found": False,
        }
        write_json_artifact(traffic_dir, "traffic-live.json", result)
        return result
    
    # Use resolved URL (includes correct port from Service)
    target_service = "frontend-proxy"
    target_fqdn = _build_frontend_proxy_fqdn(target_service, namespace)
    
    log(f"Target service: {target_service}")
    log(f"Target FQDN: {target_fqdn}")
    log(f"Target URL: {target_url}")
    log(f"Traffic pod will run in namespace: {namespace}")
    
    # Create traffic pod manifest
    traffic_pod_name = f"k9b-traffic-generator-{int(time.time())}"
    pod_manifest = f"""apiVersion: v1
kind: Pod
metadata:
  name: {traffic_pod_name}
  namespace: {namespace}
  labels:
    app: k9b-traffic-generator
    created-by: k9b-otel-demo-lab
spec:
  restartPolicy: Never
  containers:
  - name: curl
    image: curlimages/curl:latest
    command: ["/bin/sh", "-c"]
    args:
      - |
        end=$(( $(date +%s) + {duration_seconds} ))
        success=0
        fail=0
        while [ $(date +%s) -lt $end ]; do
          if curl -s -o /dev/null -w "%{{http_code}}" {target_url} | grep -qE "^[23]"; then
            success=$((success + 1))
          else
            fail=$((fail + 1))
          fi
          sleep {interval_seconds}
        done
        echo "TRAFFIC_SUMMARY: success=$success fail=$fail"
"""
    
    # Apply traffic pod
    log(f"Creating traffic pod: {traffic_pod_name}")
    apply_result = kubectl_apply(kubeconfig, pod_manifest, namespace)
    
    if not apply_result.success:
        log(f"Failed to create traffic pod: {apply_result.stderr}")
        result = {
            "mode": "live",
            "error": apply_result.stderr,
            "success_count": 0,
            "failure_count": 0,
            "actual_attempts": 0,
            "estimated_attempts": duration_seconds // interval_seconds,
            "summary_found": False,
        }
        write_json_artifact(traffic_dir, "traffic-live.json", result)
        return result
    
    # Poll for Succeeded phase (pod has finished)
    max_wait = duration_seconds + 60
    elapsed = 0
    pod_phase = "Unknown"
    while elapsed < max_wait:
        phase_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "pod", traffic_pod_name,
             "-n", namespace, "-o", "jsonpath={.status.phase}"],
            capture_output=True, text=True
        )
        if phase_result.returncode == 0:
            pod_phase = phase_result.stdout.strip()
            if pod_phase == "Succeeded":
                log(f"Traffic pod completed with phase: {pod_phase}")
                break
            elif pod_phase == "Failed":
                log(f"Traffic pod failed with phase: {pod_phase}")
                break
        time.sleep(5)
        elapsed += 5
    
    log(f"Traffic pod final phase: {pod_phase} after {elapsed}s")
    
    # Get pod logs
    logs_result = kubectl_logs(kubeconfig, traffic_pod_name, namespace)
    pod_logs = logs_result.stdout if logs_result.success else logs_result.stderr
    
    # Parse results from logs
    success_count = 0
    failure_count = 0
    summary_found = False
    summary_line = ""
    for line in pod_logs.split("\n"):
        if "TRAFFIC_SUMMARY:" in line:
            summary_line = line
            summary_found = True
            parts = line.split("success=")
            if len(parts) > 1:
                success_fail = parts[1].split()[0]
                success_count = int(success_fail)
                fail_parts = parts[1].split("fail=")
                if len(fail_parts) > 1:
                    failure_count = int(fail_parts[1])
    
    # Calculate actual attempts (only if we found summary)
    actual_attempts = success_count + failure_count if summary_found else 0
    estimated_attempts = duration_seconds // interval_seconds
    
    # Delete traffic pod
    log(f"Deleting traffic pod: {traffic_pod_name}")
    subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "delete", "pod", traffic_pod_name,
         "-n", namespace, "--wait=true"],
        capture_output=True
    )
    
    result = {
        "mode": "live",
        "traffic_pod_name": traffic_pod_name,
        "target_service": target_service,
        "target_fqdn": target_fqdn,
        "target_url": target_url,
        "namespace": namespace,
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "success_count": success_count,
        "failure_count": failure_count,
        "actual_attempts": actual_attempts,
        "estimated_attempts": estimated_attempts,
        "summary_found": summary_found,
        "pod_phase": pod_phase,
        "pod_logs": pod_logs[-2000:],  # Last 2000 chars
        "summary": summary_line,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    
    # Write traffic artifact
    write_json_artifact(traffic_dir, "traffic-live.json", result)
    
    log(f"Live traffic complete: {success_count} success, {failure_count} failures, actual={actual_attempts}, estimated={estimated_attempts}")
    return result


def kubectl_apply(kubeconfig: str, manifest: str, namespace: str) -> Any:
    """Apply a manifest using kubectl."""
    from .k9b_lab_common_helpers import KubectlResult
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"]
    result = subprocess.run(cmd, input=manifest, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def kubectl_logs(kubeconfig: str, pod: str, namespace: str) -> Any:
    """Get pod logs."""
    from .k9b_lab_common_helpers import KubectlResult
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "logs", pod, "-n", namespace]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)

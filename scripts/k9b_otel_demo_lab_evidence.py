#!/usr/bin/env python3
"""Evidence collection for OTel Demo Lab injection."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import kubectl_describe, kubectl_json, log, write_json_artifact, write_text_artifact
from .k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE

# Sanitizer: redacts sensitive values from K8s artifacts
try:
    from .lab_common.artifact_sanitizer import sanitize_artifact
except ImportError:
    def sanitize_artifact(data: Any, max_depth: int = 20) -> Any:
        return data


def collect_injection_evidence(
    kubeconfig: str,
    artifact_dir: Path,
    live_mode: bool = False,
) -> dict[str, Path]:
    """Collect evidence after incident injection.
    
    Args:
        kubeconfig: Path to kubeconfig
        artifact_dir: Directory to write artifacts
        live_mode: If True, collect extended evidence for live mode verification
        
    Collects:
    - Current pods state
    - Events
    - Recommendation service logs
    - Feature flag configuration
    - In live mode: extended Kubernetes evidence, deployments, services, endpoints
    """
    log(f"Collecting injection evidence... (live_mode={live_mode})")
    
    injection_dir = artifact_dir / "phase2-injected"
    injection_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts: dict[str, Path] = {}
    
    # Collect all pods
    pods_result = kubectl_json(kubeconfig, "pods", OTEL_DEMO_NAMESPACE)
    if pods_result.success and pods_result.data:
        # Sanitize pods to redact sensitive values (passwords, tokens, kubeconfig refs)
        sanitized_pods = sanitize_artifact(pods_result.data)
        pods_path = write_json_artifact(injection_dir, "pods.json", sanitized_pods)
        artifacts["pods"] = pods_path
        
        # Collect recommendation service specific info
        for pod in pods_result.data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "recommendation" in pod_name.lower():
                # Get pod describe
                desc_result = kubectl_describe(kubeconfig, "pod", pod_name, OTEL_DEMO_NAMESPACE)
                if desc_result.success:
                    desc_path = write_text_artifact(injection_dir, f"pod-describe-{pod_name}.txt", desc_result.stdout)
                    artifacts[f"pod-describe-{pod_name}"] = desc_path
                
                # Get logs for each container (current)
                for cs in pod.get("status", {}).get("containerStatuses", []):
                    container_name = cs.get("name", "")
                    if not container_name:
                        continue
                    
                    log_result = subprocess.run(
                        ["kubectl", "--kubeconfig", kubeconfig, "logs", pod_name,
                         "-c", container_name, "-n", OTEL_DEMO_NAMESPACE],
                        capture_output=True, text=True
                    )
                    if log_result.returncode == 0:
                        log_path = injection_dir / f"recommendation-logs-{container_name}.txt"
                        log_path.write_text(log_result.stdout)
                        artifacts[f"recommendation-log-{container_name}"] = log_path
                    
                    # Get previous logs if restart count > 0
                    restart_count = cs.get("restartCount", 0)
                    if restart_count > 0:
                        prev_log_result = subprocess.run(
                            ["kubectl", "--kubeconfig", kubeconfig, "logs", pod_name,
                             "-c", container_name, "-n", OTEL_DEMO_NAMESPACE, "--previous"],
                            capture_output=True, text=True
                        )
                        if prev_log_result.returncode == 0:
                            prev_log_path = injection_dir / f"recommendation-logs-{container_name}-previous.txt"
                            prev_log_path.write_text(prev_log_result.stdout)
                            artifacts[f"recommendation-log-{container_name}-previous"] = prev_log_path
    else:
        write_text_artifact(injection_dir, "pods-error.txt", pods_result.stderr)
        artifacts["pods_error"] = injection_dir / "pods-error.txt"
    
    # Collect events
    events_result = kubectl_json(kubeconfig, "events", OTEL_DEMO_NAMESPACE)
    if events_result.success and events_result.data:
        events_path = write_json_artifact(injection_dir, "events.json", events_result.data)
        artifacts["events"] = events_path
    
    # Collect ConfigMaps (for flag state)
    cm_result = kubectl_json(kubeconfig, "configmaps", OTEL_DEMO_NAMESPACE)
    if cm_result.success and cm_result.data:
        flag_cms = {
            cm.get("metadata", {}).get("name", ""): cm
            for cm in cm_result.data.get("items", [])
            if "flag" in cm.get("metadata", {}).get("name", "").lower()
        }
        if flag_cms:
            cms_path = write_json_artifact(injection_dir, "feature-flag-configmaps.json", {"configmaps": flag_cms})
            artifacts["feature_flag_configmaps"] = cms_path
    
    # Live mode: collect extended evidence
    if live_mode:
        log("Collecting extended live mode evidence...")
        
        # Deployments
        deploy_result = kubectl_json(kubeconfig, "deployments", OTEL_DEMO_NAMESPACE)
        if deploy_result.success and deploy_result.data:
            # Sanitize deployments to redact sensitive values (passwords, tokens, kubeconfig refs)
            sanitized_deployments = sanitize_artifact(deploy_result.data)
            deploy_path = write_json_artifact(injection_dir, "deployments.json", sanitized_deployments)
            artifacts["deployments"] = deploy_path
        
        # Services
        svc_result = kubectl_json(kubeconfig, "services", OTEL_DEMO_NAMESPACE)
        if svc_result.success and svc_result.data:
            svc_path = write_json_artifact(injection_dir, "services.json", svc_result.data)
            artifacts["services"] = svc_path
        
        # Endpoints
        ep_result = kubectl_json(kubeconfig, "endpoints", OTEL_DEMO_NAMESPACE)
        if ep_result.success and ep_result.data:
            ep_path = write_json_artifact(injection_dir, "endpoints.json", ep_result.data)
            artifacts["endpoints"] = ep_path
        
        # Flagd logs if available
        flagd_pods = kubectl_json(kubeconfig, "pods", OTEL_DEMO_NAMESPACE)
        if flagd_pods.success and flagd_pods.data:
            for pod in flagd_pods.data.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "")
                if "flagd" in pod_name.lower():
                    flagd_log_result = subprocess.run(
                        ["kubectl", "--kubeconfig", kubeconfig, "logs", pod_name,
                         "-n", OTEL_DEMO_NAMESPACE],
                        capture_output=True, text=True
                    )
                    if flagd_log_result.returncode == 0:
                        flagd_log_path = injection_dir / "flagd-logs.txt"
                        flagd_log_path.write_text(flagd_log_result.stdout)
                        artifacts["flagd_logs"] = flagd_log_path
                    break
        
        # Create marker file for live observation
        live_marker = injection_dir / ".live-mode"
        live_marker.write_text("live observation artifacts collected")
        artifacts["live_mode_marker"] = live_marker
    
    log(f"Collected {len(artifacts)} injection evidence artifacts")
    return artifacts

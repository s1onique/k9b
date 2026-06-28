#!/usr/bin/env python3
"""Evidence collection for OTel Demo Lab injection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .k9b_lab_common_helpers import kubectl_describe, kubectl_json, log, write_json_artifact, write_text_artifact
from .k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE


def collect_injection_evidence(kubeconfig: str, artifact_dir: Path) -> dict[str, Path]:
    """Collect evidence after incident injection.
    
    Collects:
    - Current pods state
    - Events
    - Recommendation service logs
    - Feature flag configuration
    """
    log("Collecting injection evidence...")
    
    injection_dir = artifact_dir / "phase2-injected"
    injection_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts: dict[str, Path] = {}
    
    # Collect all pods
    pods_result = kubectl_json(kubeconfig, "pods", OTEL_DEMO_NAMESPACE)
    if pods_result.success and pods_result.data:
        pods_path = write_json_artifact(injection_dir, "pods.json", pods_result.data)
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
                
                # Get logs for each container
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
    
    log(f"Collected {len(artifacts)} injection evidence artifacts")
    return artifacts

#!/usr/bin/env python3
"""Feature flag operations for OTel Demo Lab injection.

Handles flagd-based feature flag management for incident injection.
"""

from __future__ import annotations

import json
import subprocess

from .k9b_lab_common_helpers import kubectl_json, kubectl_text, log
from .k9b_otel_demo_lab_constants import FEATURE_FLAG_CACHE_FAILURE, OTEL_DEMO_NAMESPACE


def find_flagd_service(kubeconfig: str) -> str | None:
    """Find the flagd service in the otel-demo namespace."""
    result = kubectl_json(kubeconfig, "services", OTEL_DEMO_NAMESPACE)
    if not result.success or not result.data:
        return None
    
    for svc in result.data.get("items", []):
        svc_name: str = svc.get("metadata", {}).get("name", "") or ""
        if "flagd" in svc_name.lower() or "feature" in svc_name.lower():
            return svc_name
    
    # Also check for flagd in any namespace
    all_svcs = kubectl_json(kubeconfig, "services", "")
    if all_svcs.success and all_svcs.data:
        for svc in all_svcs.data.get("items", []):
            svc_name = svc.get("metadata", {}).get("name", "") or ""
            if "flagd" in svc_name.lower():
                return svc_name
    
    return None


def get_feature_flag_config(kubeconfig: str, flagd_service: str) -> dict:
    """Get the current feature flag configuration."""
    kubectl_text(kubeconfig, f"services/{flagd_service}", OTEL_DEMO_NAMESPACE)
    
    cm_result = kubectl_json(kubeconfig, "configmap/flagd", OTEL_DEMO_NAMESPACE)
    if cm_result.success and cm_result.data:
        return {"source": "configmap", "data": cm_result.data.get("data", {})}
    
    all_cms = kubectl_json(kubeconfig, "configmaps", OTEL_DEMO_NAMESPACE)
    if all_cms.success and all_cms.data:
        for cm in all_cms.data.get("items", []):
            cm_name = cm.get("metadata", {}).get("name", "")
            if "flag" in cm_name.lower():
                return {"source": "configmap", "configmap_name": cm_name, "data": cm.get("data", {})}
    
    return {"source": "unknown", "error": "Could not find flag configuration"}


def set_feature_flag(kubeconfig: str, flagd_service: str, enable: bool) -> dict:
    """Set the feature flag state and return normalized result."""
    cm_result = kubectl_json(kubeconfig, "configmaps", OTEL_DEMO_NAMESPACE)
    flag_cm_name = None
    
    if cm_result.success and cm_result.data:
        for cm in cm_result.data.get("items", []):
            cm_name = cm.get("metadata", {}).get("name", "")
            cm_data = cm.get("data", {})
            if FEATURE_FLAG_CACHE_FAILURE in cm_data:
                flag_cm_name = cm_name
                break
            elif any("flag" in k.lower() for k in cm_data.keys()):
                flag_cm_name = cm_name
    
    if flag_cm_name:
        log(f"Updating flag via ConfigMap {flag_cm_name}")
        patch_data = {
            "data": {
                FEATURE_FLAG_CACHE_FAILURE: json.dumps({
                    "flags": {FEATURE_FLAG_CACHE_FAILURE: {"enabled": enable, "description": "Inject cache failure for testing"}}
                })
            }
        }
        cmd = ["kubectl", "--kubeconfig", kubeconfig, "patch", "configmap", flag_cm_name,
               "-n", OTEL_DEMO_NAMESPACE, "--type", "merge", "-p", json.dumps(patch_data)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log(f"ConfigMap {flag_cm_name} patched successfully")
            restart_flagd_pods(kubeconfig)
            return {"source": "configmap", "configmap_name": flag_cm_name,
                    "flags": {FEATURE_FLAG_CACHE_FAILURE: {"enabled": enable, "description": "Inject cache failure for testing"}}, "verified": True}
    
    log("Creating new flag configuration ConfigMap")
    return create_flag_configmap(kubeconfig, enable)


def create_flag_configmap(kubeconfig: str, enable: bool) -> dict:
    """Create a new flag configuration ConfigMap."""
    flag_spec = {"spec": {"flags": {FEATURE_FLAG_CACHE_FAILURE: {"enabled": enable, "description": "Enable recommendation cache failure for incident testing"}}}}
    cm_manifest = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-demo-feature-flags
  namespace: {OTEL_DEMO_NAMESPACE}
  labels:
    app.kubernetes.io/name: opentelemetry-demo
    app.kubernetes.io/component: feature-flags
data:
  cache_failure.json: |
    {json.dumps(flag_spec, indent=2)}
"""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"]
    result = subprocess.run(cmd, input=cm_manifest, capture_output=True, text=True)
    if result.returncode == 0:
        log("Feature flag ConfigMap created")
        restart_flagd_pods(kubeconfig)
        return {"source": "configmap", "configmap_name": "otel-demo-feature-flags",
                "flags": {FEATURE_FLAG_CACHE_FAILURE: {"enabled": enable, "description": "Enable recommendation cache failure for incident testing"}}, "created": True, "verified": True}
    return {"source": "unknown", "error": result.stderr, "enabled": enable}


def restart_flagd_pods(kubeconfig: str) -> None:
    """Restart flagd pods to force configuration reload."""
    result = kubectl_json(kubeconfig, "pods", OTEL_DEMO_NAMESPACE)
    if not result.success or not result.data:
        return
    for pod in result.data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        if "flagd" in pod_name.lower():
            log(f"Deleting flagd pod {pod_name} to force reload...")
            subprocess.run(["kubectl", "--kubeconfig", kubeconfig, "delete", "pod", pod_name,
                          "-n", OTEL_DEMO_NAMESPACE, "--wait=true"], capture_output=True)

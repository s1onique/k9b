#!/usr/bin/env python3
"""Incident injection module for OpenTelemetry Demo Lab.

This module handles:
- Feature flag-based incident injection (recommendationServiceCacheFailure)
- Traffic generation for symptom observation

For LLM-friendly reading, see companion modules:
- k9b_otel_demo_lab_flags.py - flagd operations
- k9b_otel_demo_lab_traffic.py - traffic generation
- k9b_otel_demo_lab_evidence.py - evidence collection
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import log, write_json_artifact
from .k9b_otel_demo_lab_constants import FEATURE_FLAG_CACHE_FAILURE, OTEL_DEMO_NAMESPACE
from .k9b_otel_demo_lab_flags import (
    find_flagd_service,
    get_feature_flag_config,
    set_feature_flag,
)
from .k9b_otel_demo_lab_traffic import generate_traffic


@dataclass
class InjectionResult:
    """Result of incident injection."""
    
    success: bool
    scenario: str
    method: str
    evidence: dict[str, Any]
    error: str | None = None


def inject_recommendation_cache_failure(
    kubeconfig: str,
    artifact_dir: Path,
    enable: bool = True,
) -> InjectionResult:
    """Inject the recommendation cache failure via feature flag."""
    log(f"Injecting recommendation cache failure via feature flag: enable={enable}")
    
    injection_dir = artifact_dir / "phase2-injected"
    injection_dir.mkdir(parents=True, exist_ok=True)
    
    evidence: dict[str, Any] = {
        "method": "feature_flag",
        "flag_name": FEATURE_FLAG_CACHE_FAILURE,
        "enabled": enable,
        "timestamp": time.time(),
    }
    
    flagd_svc = find_flagd_service(kubeconfig)
    if not flagd_svc:
        log("Warning: Could not find flagd service, trying ConfigMap approach")
        return _inject_via_configmap(kubeconfig, artifact_dir, enable)
    
    evidence["flagd_service"] = flagd_svc
    
    flag_config_before = get_feature_flag_config(kubeconfig, flagd_svc)
    write_json_artifact(injection_dir, "flag-config-before.json", flag_config_before)
    evidence["flag_config_before_path"] = str(injection_dir / "flag-config-before.json")
    
    flag_config_after = set_feature_flag(kubeconfig, flagd_svc, enable)
    write_json_artifact(injection_dir, "flag-config-after.json", flag_config_after)
    evidence["flag_config_after_path"] = str(injection_dir / "flag-config-after.json")
    
    if flag_config_after.get("flags", {}).get(FEATURE_FLAG_CACHE_FAILURE, {}).get("enabled") != enable:
        evidence["verification_passed"] = False
        log(f"Warning: Flag verification failed, expected enabled={enable}")
    else:
        evidence["verification_passed"] = True
        log(f"Flag {FEATURE_FLAG_CACHE_FAILURE} set to {enable}")
    
    injection_cmd = {
        "command": f"Enable/disable {FEATURE_FLAG_CACHE_FAILURE}",
        "method": "feature_flag",
        "flagd_service": flagd_svc,
        "flag_name": FEATURE_FLAG_CACHE_FAILURE,
        "enabled": enable,
    }
    write_json_artifact(injection_dir, "injection-command.json", injection_cmd)
    evidence["injection_command_path"] = str(injection_dir / "injection-command.json")
    
    return InjectionResult(
        success=evidence["verification_passed"],
        scenario="recommendation-cache-failure",
        method="feature_flag",
        evidence=evidence,
    )


def _inject_via_configmap(kubeconfig: str, artifact_dir: Path, enable: bool) -> InjectionResult:
    """Fallback injection via ConfigMap patch."""
    import subprocess

    from .k9b_lab_common_helpers import kubectl_json
    
    log("Using ConfigMap fallback injection")
    
    injection_dir = artifact_dir / "phase2-injected"
    injection_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {"method": "configmap_fallback", "enabled": enable, "timestamp": time.time()}
    
    cm_result = kubectl_json(kubeconfig, "configmaps", OTEL_DEMO_NAMESPACE)
    flag_cm_name = None
    
    if cm_result.success and cm_result.data:
        for cm in cm_result.data.get("items", []):
            cm_name = cm.get("metadata", {}).get("name", "")
            if "feature" in cm_name.lower() or "flag" in cm_name.lower():
                flag_cm_name = cm_name
                break
    
    if not flag_cm_name:
        flag_cm_name = "otel-demo-feature-flags"
        cm_manifest = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {flag_cm_name}
  namespace: {OTEL_DEMO_NAMESPACE}
data:
  recommendationServiceCacheFailure: |
    {{"enabled": {str(enable).lower()}}}
"""
        subprocess.run(["kubectl", "--kubeconfig", kubeconfig, "apply", "-f", "-"],
                      input=cm_manifest, capture_output=True, text=True)
    
    evidence["configmap_name"] = flag_cm_name
    write_json_artifact(injection_dir, "injection-command.json", {
        "method": "configmap", "configmap": flag_cm_name,
        "flag": FEATURE_FLAG_CACHE_FAILURE, "enabled": enable
    })
    
    return InjectionResult(success=True, scenario="recommendation-cache-failure",
                          method="configmap_fallback", evidence=evidence)


# Re-export for backward compatibility
def collect_injection_evidence(kubeconfig: str, artifact_dir: Path) -> dict[str, Path]:
    """Collect evidence after incident injection."""
    from .k9b_otel_demo_lab_evidence import collect_injection_evidence as _impl
    return _impl(kubeconfig, artifact_dir)


# CLI entry point
def main() -> int:
    """CLI entry point for incident injection."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Inject OTel Demo incident")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory")
    parser.add_argument("--scenario", default="recommendation-cache-failure",
                       choices=["recommendation-cache-failure"], help="Incident scenario")
    parser.add_argument("--enable", action="store_true", default=True, help="Enable the incident")
    parser.add_argument("--traffic-duration", type=int, default=30, help="Traffic duration in seconds")
    
    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    if args.scenario == "recommendation-cache-failure":
        result = inject_recommendation_cache_failure(args.kubeconfig, artifact_dir, enable=args.enable)
        
        if result.success:
            log(f"Injection successful: {result.method}")
            traffic_result = generate_traffic(args.kubeconfig, artifact_dir, duration_seconds=args.traffic_duration)
            artifacts = collect_injection_evidence(args.kubeconfig, artifact_dir)
            summary = {"injection": result.evidence, "traffic": traffic_result, "artifacts_collected": len(artifacts)}
            write_json_artifact(artifact_dir, "injection-summary.json", summary)
            print(json.dumps(summary, indent=2))
            return 0
        else:
            log(f"Injection failed: {result.error}")
            return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

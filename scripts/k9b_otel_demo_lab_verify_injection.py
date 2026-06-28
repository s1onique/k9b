#!/usr/bin/env python3
"""Injection verification for OTel Demo Lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import read_json
from .k9b_otel_demo_lab_constants import PHASE_INJECTED


def verify_injection(artifact_dir: Path) -> dict[str, Any]:
    """Verify incident injection evidence."""
    injection_dir = artifact_dir / PHASE_INJECTED
    
    if not injection_dir.exists():
        return {"passed": False, "error": f"Injection directory not found: {injection_dir}"}
    
    evidence_files = ["injection-command.json", "pods.json", "events.json"]
    missing = [f for f in evidence_files if not (injection_dir / f).exists()]
    
    if missing:
        return {"passed": False, "error": f"Missing injection evidence: {missing}"}
    
    injection_cmd = read_json(injection_dir / "injection-command.json")
    if not injection_cmd:
        return {"passed": False, "error": "Injection command not recorded"}
    
    pods_data = read_json(injection_dir / "pods.json")
    recommendationservice_evidence = False
    
    for pod in pods_data.get("items", []):
        pod_name = pod.get("metadata", {}).get("name", "")
        if "recommendation" in pod_name.lower():
            recommendationservice_evidence = True
            break
    
    flag_config_exists = (injection_dir / "flag-config-before.json").exists() and \
                         (injection_dir / "flag-config-after.json").exists()
    
    return {"passed": True, "injection_command": injection_cmd,
            "recommendationservice_evidence": recommendationservice_evidence,
            "feature_flag_config_evidence": flag_config_exists}

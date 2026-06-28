#!/usr/bin/env python3
"""Baseline verification for OTel Demo Lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import read_json
from .k9b_otel_demo_lab_constants import PHASE_OTEL_BASELINE, REQUIRED_DEPLOYMENTS


def verify_baseline(artifact_dir: Path) -> dict[str, Any]:
    """Verify baseline readiness artifacts."""
    baseline_dir = artifact_dir / PHASE_OTEL_BASELINE
    
    if not baseline_dir.exists():
        return {"passed": False, "error": f"Baseline directory not found: {baseline_dir}"}
    
    required_files = ["deployments.json", "services.json", "pods.json", "readiness-result.json"]
    missing_files = [f for f in required_files if not (baseline_dir / f).exists()]
    
    if missing_files:
        return {"passed": False, "error": f"Missing baseline files: {missing_files}"}
    
    deployments_data = read_json(baseline_dir / "deployments.json")
    readiness_result = read_json(baseline_dir / "readiness-result.json")
    
    missing_deployments = []
    not_ready_deployments = []
    
    for dep in REQUIRED_DEPLOYMENTS:
        found = False
        for item in deployments_data.get("items", []):
            if item.get("metadata", {}).get("name", "") == dep:
                found = True
                status = item.get("status", {})
                ready = status.get("readyReplicas", 0)
                desired = status.get("replicas", 1)
                if ready < desired:
                    not_ready_deployments.append(f"{dep}({ready}/{desired})")
                break
        if not found:
            missing_deployments.append(dep)
    
    if missing_deployments or not_ready_deployments:
        return {"passed": False, "error": "Baseline not ready",
                "missing_deployments": missing_deployments,
                "not_ready_deployments": not_ready_deployments,
                "readiness_result": readiness_result}
    
    return {"passed": True, "deployments_checked": len(REQUIRED_DEPLOYMENTS), "readiness_result": readiness_result}

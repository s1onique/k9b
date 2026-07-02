#!/usr/bin/env python3
"""Result helpers for k9b OTel demo lab orchestrator.

This module contains helper functions for:
- Converting phase results to dict
- Building K8s-native verdict dicts
- Finalizing and serializing lab results
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import log, write_json_artifact
from .k9b_otel_demo_lab_contract import LabPhaseResult, LabResult


def _phase_to_dict(phase: LabPhaseResult) -> dict[str, Any]:
    """Convert phase result to dict."""
    data: dict[str, Any] = {
        "phase": phase.phase,
        "success": phase.success,
        "message": phase.message,
        "artifacts": phase.artifacts,
        "duration_seconds": phase.duration_seconds,
    }
    # Include verdict fields for K8s-native phases
    if phase.p3c_verdict is not None:
        data["p3c_verdict"] = phase.p3c_verdict
    if phase.p4c_verdict is not None:
        data["p4c_verdict"] = phase.p4c_verdict
    return data


def _build_k8s_native_verdict(
    p3c_success: bool,
    p3c_phase: LabPhaseResult | None,
    p4c_success: bool | None,
    p4c_phase: LabPhaseResult | None,
    final_success: bool,
    reason: str,
) -> dict[str, Any]:
    """Build K8s-native verdict dict for lab-result.json.

    This function is used in both success and failure paths to ensure
    the verdict is always populated with phase distinction.
    """
    verdict: dict[str, Any] = {
        "final": {
            "success": final_success,
            "reason": reason,
        },
    }

    # P3c verdict
    p3c_data: dict[str, Any] = {
        "success": p3c_success,
        "phase": "incident_discovery",
    }
    if p3c_phase is not None:
        p3c_data["incident_id"] = p3c_phase.artifacts.get("incident_id")
        p3c_data["candidate_class"] = p3c_phase.artifacts.get("candidate_class")
        p3c_data["root_cause_final"] = False  # P3c is symptom-level only
    verdict["p3c"] = p3c_data

    # P4c verdict - use normalized p4c_outcome if available
    p4c_data: dict[str, Any] = {
        "phase": "root_cause_validation",
    }
    if p4c_phase is not None:
        # Use the normalized p4c_outcome from the phase artifacts
        p4c_outcome = p4c_phase.artifacts.get("p4c_outcome")
        if p4c_outcome:
            # Use the single authoritative source for P4c success/failure
            p4c_data["success"] = p4c_outcome.get("success", p4c_success)
            p4c_data["mode"] = p4c_outcome.get("mode")
            p4c_data["pass_count"] = p4c_outcome.get("pass_count")
            p4c_data["pass_run_ids"] = p4c_outcome.get("pass_run_ids", [])
            p4c_data["review_artifact_paths"] = p4c_outcome.get("review_artifact_paths", [])
            p4c_data["failure_reasons"] = p4c_outcome.get("failure_reasons", [])
            # Use failure_reasons from normalized outcome
            if p4c_outcome.get("failure_reasons"):
                p4c_data["failure_reason"] = "; ".join(p4c_outcome["failure_reasons"])
            elif not p4c_outcome.get("success"):
                p4c_data["failure_reason"] = p4c_phase.artifacts.get("failure_reason")
        else:
            # Fallback to legacy behavior
            if p4c_success is not None:
                p4c_data["success"] = p4c_success
            p4c_data["failure_reason"] = p4c_phase.artifacts.get("failure_reason")
    verdict["p4c"] = p4c_data

    return verdict


def _finish_result(
    result: LabResult,
    artifact_dir: Path,
    start_time: float,
) -> LabResult:
    """Finalize and save the lab result."""
    result.finished_at = datetime.now(UTC).isoformat()
    elapsed = time.time() - start_time
    result.elapsed_seconds = elapsed

    # Write result to artifact dir
    result_path = write_json_artifact(artifact_dir, "lab-result.json", _result_to_dict(result))
    log(f"Lab result saved to {result_path}")

    return result


def _result_to_dict(result: LabResult) -> dict[str, Any]:
    """Convert LabResult to dict for JSON serialization."""
    data: dict[str, Any] = {
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "elapsed_seconds": result.elapsed_seconds,
        "success": result.success,
        "failure_reason": result.failure_reason,
        "verification_passed": result.verification_passed,
        "verification_details": result.verification_details,
        "provider_smoke_passed": result.provider_smoke_passed,
        "config": result.config,
        "phases": result.phases,
    }
    # Include K8s-native verdict if present (for unschedulable-shipping scenario)
    if result.k8s_native_verdict is not None:
        data["k8s_native_verdict"] = result.k8s_native_verdict
    return data

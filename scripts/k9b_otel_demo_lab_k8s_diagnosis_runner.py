#!/usr/bin/env python3
"""Diagnosis loop runner for K8s multi-pass diagnosis phase.

This module is a thin compatibility façade that re-exports the public API
from the extracted runner modules.

Architecture:
- P4c uses backend-targeted automatic diagnosis-loop one-pass via
  POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
- This bypasses the scheduler-global periodic loop which may not
  process the specific incident
- State is validated via GET /api/incidents/{incident_id}

For the actual implementation, see:
- k9b_otel_demo_lab_k8s_diagnosis_runner_config: config/env helpers
- k9b_otel_demo_lab_k8s_diagnosis_runner_phases: phase sequencing
- k9b_otel_demo_lab_k8s_diagnosis_runner_execution: execution logic
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_REAL,
    DIAGNOSIS_SOURCE_SIMULATED,
    FAILURE_REASON_LOOP_ENV_RBAC_DENIED,
    FAILURE_REASON_LOOP_ENV_READ_FAILED,
    MIN_REQUIRED_PASSES,
    SIMULATION_ENV_VAR,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_config import (
    DEFAULT_K9B_NAMESPACE,
    _LOOP_CHECK_REASON_TO_FAILURE,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
    extract_root_cause_from_review,
    run_backend_targeted_diagnosis,
    simulate_diagnosis_loop,
)
from scripts.k9b_lab_common_helpers import log


def run_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int = DEFAULT_MAX_PASSES,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
    allow_simulation: bool = False,
    kubeconfig: str | None = None,
    namespace: str = "k9b",
) -> dict[str, Any]:
    """Run the automatic diagnosis loop for an incident.

    This function triggers the k9b automatic diagnosis loop and collects
    multi-pass diagnostic information. By default, it FAILS CLOSED if
    the real loop is unavailable. Simulation is only allowed when
    explicitly enabled via allow_simulation=True.

    Architecture note:
        P4c uses backend-targeted one-pass diagnosis via the API endpoint
        POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass.
        This bypasses the scheduler-global periodic loop which may not process
        the specific incident. Do NOT use /diagnosis-loop/one-pass for OTel P4c;
        it is not the automatic collector path.

    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow
        max_checks_per_pass: Maximum checks per pass
        allow_simulation: If True, allow simulation fallback for testing.
                          NEVER set this in production/live-lab.
        kubeconfig: Optional path to kubeconfig for kubectl exec
        namespace: Namespace where k9b backend runs (default: "k9b")

    Returns:
        Dict with diagnosis loop results. On failure, includes
        `diagnosis_source`, `failure_reason`, `simulation_used`.
    """
    import os

    result: dict[str, Any] = {
        "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
        "simulation_used": False,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": False,
        "diagnosis_loop_module": None,
        "status": "unknown",
        "incident_id": incident_id,
        "pass_count": 0,
        "pass_run_ids": [],
        "requested_checks": [],
        "executed_checks": [],
        "root_cause_summary": "",
        "artifact_path": None,
        "review_packet_path": None,
        "failure_reason": None,
        # Backend-targeted diagnosis metadata
        "backend_targeted_invocation": False,
        "targeted_invocation_result": None,
        "targeted_poll_result": None,
        "backend_incident_detail": None,
    }

    # Check for simulation env var (test-only override)
    simulation_env = os.environ.get(SIMULATION_ENV_VAR, "").lower()
    if simulation_env == "true":
        log(f"  NOTE: {SIMULATION_ENV_VAR}=true (TEST MODE ONLY)")
        allow_simulation = True

    # If no kubeconfig, fail immediately
    if not kubeconfig:
        log("  ERROR: kubeconfig is required for backend-targeted diagnosis")
        result["failure_reason"] = "kubeconfig_required"
        result["status"] = "kubeconfig_missing"
        if allow_simulation:
            log("  NOTE: allow_simulation=True - using simulation (TEST ONLY)")
            return simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result

    # Use backend-targeted diagnosis
    k9b_namespace = namespace or DEFAULT_K9B_NAMESPACE
    return run_backend_targeted_diagnosis(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        kubeconfig=kubeconfig,
        namespace=k9b_namespace,
        result=result,
        allow_simulation=allow_simulation,
        max_passes=max_passes,
    )


# Re-export internal functions for backwards compatibility with tests
_run_backend_targeted_diagnosis = run_backend_targeted_diagnosis
_simulate_diagnosis_loop = simulate_diagnosis_loop
_extract_root_cause_from_review = extract_root_cause_from_review

__all__ = [
    "run_diagnosis_loop",
    "run_backend_targeted_diagnosis",
    "simulate_diagnosis_loop",
    "extract_root_cause_from_review",
]

#!/usr/bin/env python3
"""Diagnosis loop runner for K8s multi-pass diagnosis phase.

This module contains the execution logic for running the automatic
diagnosis loop and simulation fallback. It handles external seam
invocation with proper error handling.

Architecture:
- P4c uses backend-targeted automatic diagnosis-loop one-pass via
  POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
- This endpoint wraps collect_automatic_diagnosis_evidence() and uses
  the REAL automatic diagnosis loop collector
- This bypasses the scheduler-global periodic loop which may not
  process the specific incident
- State is validated via GET /api/incidents/{incident_id}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import log
from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers import (
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    fetch_backend_incident_detail,
    invoke_targeted_automatic_diagnosis_loop,
    poll_backend_diagnosis_state,
)
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

# Mapping from loop check reason codes to failure reason constants
_LOOP_CHECK_REASON_TO_FAILURE: dict[str, str] = {
    "automatic_loop_env_rbac_denied": FAILURE_REASON_LOOP_ENV_RBAC_DENIED,
    "automatic_loop_env_read_failed": FAILURE_REASON_LOOP_ENV_READ_FAILED,
}

# Default k9b namespace
DEFAULT_K9B_NAMESPACE = "k9b"


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
            return _simulate_diagnosis_loop(
                incident_id,
                external_analysis_dir,
                max_passes,
            )
        return result

    # Use backend-targeted diagnosis
    k9b_namespace = namespace or DEFAULT_K9B_NAMESPACE
    return _run_backend_targeted_diagnosis(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        kubeconfig=kubeconfig,
        namespace=k9b_namespace,
        result=result,
        allow_simulation=allow_simulation,
        max_passes=max_passes,
    )


def _run_backend_targeted_diagnosis(
    incident_id: str,
    external_analysis_dir: Path,
    kubeconfig: str,
    namespace: str,
    result: dict[str, Any],
    allow_simulation: bool,
    max_passes: int = DEFAULT_MAX_PASSES,
) -> dict[str, Any]:
    """Run backend-targeted diagnosis for the incident.

    This function:
    1. Confirms the incident exists in backend
    2. Loops targeted one-pass endpoint until pass_count >= MIN_REQUIRED_PASSES
    3. Polls for diagnosis completion after each pass
    4. Validates persisted state

    Architecture:
        The /automatic-diagnosis-loop/one-pass endpoint runs a single pass.
        To meet the MIN_REQUIRED_PASSES requirement (typically 2), we loop
        the endpoint until we have sufficient passes accumulated.

    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Directory for diagnosis artifacts
        kubeconfig: Path to kubeconfig
        namespace: Namespace where k9b backend runs
        result: Result dict to populate
        allow_simulation: If True, allow simulation fallback

    Returns:
        Result dict with diagnosis loop results
    """
    log(f"  Using backend-targeted diagnosis for incident {incident_id}")

    # Step 1: Confirm incident exists in backend
    log("  Step 1: Confirming incident exists in backend...")
    incident_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )

    if incident_detail is None:
        log("  ERROR: Could not fetch incident detail from backend")
        result["failure_reason"] = "backend_incident_fetch_failed"
        result["status"] = "fetch_failed"
        result["backend_incident_detail"] = None
        return result

    result["backend_incident_detail"] = incident_detail.to_compact_log()
    log(f"  Backend incident: {incident_detail.to_compact_log()}")

    # Initialize pass tracking
    total_pass_count = 0
    all_pass_run_ids: list[str] = []

    # Step 2: Loop targeted one-pass endpoint until pass_count >= MIN_REQUIRED_PASSES
    log(f"  Step 2: Looping targeted diagnosis until pass_count >= {MIN_REQUIRED_PASSES}...")

    for pass_attempt in range(1, max_passes + 1):
        current_pass_in_label = f"pass {pass_attempt}/{max_passes}"
        log(f"    [{current_pass_in_label}] Invoking targeted diagnosis-loop one-pass...")

        invocation_result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
        )

        if pass_attempt == 1:
            result["backend_targeted_invocation"] = True
            result["targeted_invocation_result"] = invocation_result.to_dict()

        if not invocation_result.success:
            log(f"    [{current_pass_in_label}] ERROR: Targeted invocation failed: {invocation_result.error_class}")
            log(f"    [{current_pass_in_label}] Detail: {invocation_result.error_detail}")

            # Fail with specific error class on first invocation
            if pass_attempt == 1:
                result["failure_reason"] = invocation_result.error_class
                result["status"] = "invocation_failed"
                result["real_loop_invoked"] = False
                return result
            else:
                # Log failure but continue with accumulated passes
                log(f"    [{current_pass_in_label}] WARNING: Pass invocation failed, using accumulated passes")
                break

        log(f"    [{current_pass_in_label}] Invocation succeeded (HTTP {invocation_result.http_status})")
        result["real_loop_invoked"] = True
        result["provider_invocation_attempted"] = True

        # Step 3: Poll for diagnosis completion
        log(f"    [{current_pass_in_label}] Polling backend for diagnosis completion...")

        def poll_log(message: str) -> None:
            log(f"      {message}")

        poll_result = poll_backend_diagnosis_state(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
            max_attempts=12,
            poll_interval_seconds=5.0,
            log_callback=poll_log,
        )

        if pass_attempt == 1:
            result["targeted_poll_result"] = poll_result.to_dict()

        if not poll_result.success:
            log(f"    [{current_pass_in_label}] ERROR: Diagnosis did not complete: {poll_result.failure_reason}")
            log(f"    [{current_pass_in_label}] Final status: {poll_result.final_status}")
            log(f"    [{current_pass_in_label}] Loop summary: {poll_result.loop_summary_status}")
            log(f"    [{current_pass_in_label}] Review available: {poll_result.review_available}")

            if pass_attempt == 1:
                result["failure_reason"] = poll_result.failure_reason
                result["status"] = "poll_timeout"
                return result
            else:
                log(f"    [{current_pass_in_label}] WARNING: Poll failed, using accumulated passes")
                break

        log(f"    [{current_pass_in_label}] Diagnosis completed: loop_summary.status={poll_result.loop_summary_status}")

        # Step 4: Fetch current incident detail and extract pass information
        current_detail = fetch_backend_incident_detail(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
        )

        if current_detail:
            result["backend_incident_detail"] = current_detail.to_compact_log()
            result["status"] = current_detail.status

            # Extract pass information from the response
            loop_summary = current_detail.raw.get("automatic_diagnosis_loop_summary", {}) or {}
            if "pass_run_ids" in loop_summary:
                current_pass_run_ids = loop_summary["pass_run_ids"] or []
                # Track new passes (those not already in our list)
                new_pass_run_ids = [rid for rid in current_pass_run_ids if rid not in all_pass_run_ids]
                all_pass_run_ids.extend(new_pass_run_ids)
                total_pass_count = len(all_pass_run_ids)
            elif "pass_count" in loop_summary:
                total_pass_count = loop_summary["pass_count"] or 0

            # Check for review packet
            result["review_packet_found"] = current_detail.review_available

            # Try to extract root cause summary from loop summary
            if "root_cause_summary" in loop_summary:
                result["root_cause_summary"] = loop_summary["root_cause_summary"]

        log(f"    [{current_pass_in_label}] Total passes so far: {total_pass_count}/{MIN_REQUIRED_PASSES}")

        # Check if we have enough passes
        if total_pass_count >= MIN_REQUIRED_PASSES:
            log(f"    [{current_pass_in_label}] SUCCESS: Required passes met ({total_pass_count} >= {MIN_REQUIRED_PASSES})")
            break
        elif pass_attempt < max_passes:
            log(f"    [{current_pass_in_label}] Need more passes, continuing loop...")
        else:
            log(f"    [{current_pass_in_label}] Reached max_passes limit ({max_passes})")

    # Step 5: Final validation
    log("  Step 5: Validating pass artifacts...")
    result["pass_count"] = total_pass_count
    result["pass_run_ids"] = all_pass_run_ids

    if result["pass_count"] < MIN_REQUIRED_PASSES:
        result["failure_reason"] = FAILURE_TARGETED_INSUFFICIENT_PASSES
        result["real_pass_artifacts_found"] = False
        log(f"  ERROR: Insufficient passes: {result['pass_count']} < {MIN_REQUIRED_PASSES}")
        return result

    result["real_pass_artifacts_found"] = result["pass_count"] >= MIN_REQUIRED_PASSES
    result["pass_artifact_paths"] = [str(external_analysis_dir / "diagnosis-loop-passes" / f"{rid}.json")
                                    for rid in result["pass_run_ids"]]
    result["artifact_path"] = str(external_analysis_dir / "diagnosis-loop-passes")

    log(f"  Backend-targeted diagnosis completed: {result['pass_count']} passes")
    return result


def _simulate_diagnosis_loop(
    incident_id: str,
    external_analysis_dir: Path,
    max_passes: int,
) -> dict[str, Any]:
    """Simulate multi-pass diagnosis loop for lab verification.

    This function provides a simulated diagnosis loop that:
    1. Runs exactly 2 passes (meeting minimum requirement)
    2. Provides realistic root-cause summary
    3. Includes read-only check evidence

    IMPORTANT: This function is for TESTING ONLY. It returns
    simulation metadata so the verifier can reject it.

    Args:
        incident_id: The incident ID being diagnosed
        external_analysis_dir: Directory for diagnosis artifacts
        max_passes: Maximum passes to allow

    Returns:
        Simulated diagnosis result with simulation metadata
    """
    log("  Running simulated diagnosis loop (2 passes) - TEST ONLY")

    # Simulate pass 1: Initial diagnosis with partial evidence
    pass1_run_id = f"sim-{incident_id[:8]}-pass1"
    pass1_time = datetime.now(UTC).isoformat()

    # Simulate pass 2: Follow-up with full evidence
    pass2_run_id = f"sim-{incident_id[:8]}-pass2"
    pass2_time = datetime.now(UTC).isoformat()

    # Create simulated loop pass artifacts
    loop_passes_dir = external_analysis_dir / "diagnosis-loop-passes"
    loop_passes_dir.mkdir(parents=True, exist_ok=True)

    pass1_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass1_run_id,
        "timestamp": pass1_time,
        "pass_number": 1,
        "decision": "run_allowed_read_only_checks",
        "checks_requested": 3,
        "checks_run": 3,
        "read_only": True,
    }

    pass2_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "run_id": pass2_run_id,
        "timestamp": pass2_time,
        "pass_number": 2,
        "decision": "stop_root_cause_found",
        "checks_requested": 2,
        "checks_run": 2,
        "read_only": True,
    }

    # Write pass artifacts
    (loop_passes_dir / f"{pass1_run_id}.json").write_text(json.dumps(pass1_artifact, indent=2))
    (loop_passes_dir / f"{pass2_run_id}.json").write_text(json.dumps(pass2_artifact, indent=2))

    # Simulated root-cause summary matching the expected root cause
    root_cause_summary = (
        f"Root cause identified: The {SHIPPING_DEPLOYMENT} Deployment "
        f"has an impossible nodeSelector requiring label "
        f"'{K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}'. "
        f"No node in the cluster has this label, causing the shipping-* Pod "
        f"to remain in Pending state with status 'unschedulable'. "
        f"The nodeSelector prevents scheduling because there is no matching node."
    )

    # Create simulated review packet
    review_dir = external_analysis_dir / "diagnosis-review"
    review_dir.mkdir(parents=True, exist_ok=True)

    review_artifact = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "collector_run_id": f"sim-collector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(UTC).isoformat(),
        "root_cause_summary": root_cause_summary,
        "diagnosis_conclusion": {
            "component": SHIPPING_DEPLOYMENT,
            "issue": "unschedulable_pod",
            "root_cause": f"impossible nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}",
            "evidence": [
                "PendingPod for shipping-* with reason Unschedulable",
                "FailedScheduling event indicating no matching node",
                f"nodeSelector: {K8S_INJECTION_NODE_SELECTOR_KEY}: {K8S_INJECTION_NODE_SELECTOR_VALUE}",
                "No nodes with required label exist in cluster",
            ],
        },
        "read_only": True,
        "allowed_actions": [],
    }

    review_filename = f"review-{incident_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    (review_dir / review_filename).write_text(json.dumps(review_artifact, indent=2))

    # Return result with simulation metadata for verifier to detect
    return {
        # Simulation metadata - used by verifier to reject
        "diagnosis_source": DIAGNOSIS_SOURCE_SIMULATED,
        "simulation_used": True,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": True,
        "diagnosis_loop_module": None,
        "failure_reason": None,
        # Diagnosis results
        "status": "completed",
        "incident_id": incident_id,
        "pass_count": 2,
        "pass_run_ids": [pass1_run_id, pass2_run_id],
        "requested_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "executed_checks": [
            "kubectl_get_deployment_shipping",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ],
        "root_cause_summary": root_cause_summary,
        "artifact_path": str(loop_passes_dir),
        "review_packet_path": str(review_dir / review_filename),
    }


def _extract_root_cause_from_review(review_data: dict[str, Any]) -> str:
    """Extract root cause summary from diagnosis review packet.

    Args:
        review_data: Review packet data

    Returns:
        Root cause summary string
    """
    # Try various paths where root cause might be stored
    if "root_cause_summary" in review_data:
        return str(review_data["root_cause_summary"])

    if "diagnosis_conclusion" in review_data:
        conclusion = review_data["diagnosis_conclusion"]
        if isinstance(conclusion, dict):
            return str(conclusion.get("summary", str(conclusion)))

    if "summary" in review_data:
        return str(review_data["summary"])

    return str(review_data)

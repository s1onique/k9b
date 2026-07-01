"""Runner phases for K8s multi-pass diagnosis phase.

This module defines the phase sequencing for the diagnosis loop runner.

Architecture:
- P4c uses backend-targeted automatic diagnosis-loop one-pass via
  POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import log
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers import (
    FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
    BackendIncidentDetail,
    fetch_backend_incident_detail,
    fetch_backend_incident_detail_result,
    invoke_targeted_automatic_diagnosis_loop,
    poll_backend_diagnosis_state,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    MIN_REQUIRED_PASSES,
)


def phase1_confirm_incident(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    result: dict[str, Any],
) -> BackendIncidentDetail | None:
    """Phase 1: Confirm incident exists in backend.

    This phase fetches the incident detail using the precise diagnostic
    result object that classifies failures into transport, HTTP, JSON,
    or contract errors.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where k9b backend runs
        incident_id: The incident ID to confirm
        result: Result dict to populate with structured diagnostics

    Returns:
        BackendIncidentDetail or None if fetch fails.
    """
    log("  Step 1: Confirming incident exists in backend...")

    fetch_result = fetch_backend_incident_detail_result(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )

    # Store structured fetch result for artifact/debugging
    result["backend_incident_fetch_result"] = fetch_result.to_dict()

    if not fetch_result.success:
        # Log precise error classification
        log(f"  ERROR: {fetch_result.error_class}")
        log(f"    Detail: {fetch_result.error_detail}")
        log(f"    HTTP status: {fetch_result.http_status}, curl_rc: {fetch_result.curl_rc}")
        if fetch_result.body_prefix:
            log(f"    Body prefix: {fetch_result.body_prefix[:100]}")

        # Use precise error class if available, fallback to generic
        result["failure_reason"] = fetch_result.error_class or FAILURE_BACKEND_INCIDENT_FETCH_FAILED
        result["status"] = "fetch_failed"
        result["backend_incident_detail"] = None
        return None

    # Success - store incident detail
    incident_detail = fetch_result.incident
    if incident_detail:
        result["backend_incident_detail"] = incident_detail.to_compact_log()
        log(f"  Backend incident: {incident_detail.to_compact_log()}")
    else:
        result["backend_incident_detail"] = None
        log("  WARNING: Fetch succeeded but returned no incident detail")

    return incident_detail


def phase2_invoke_and_poll_pass(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    pass_attempt: int,
    max_passes: int,
    result: dict[str, Any],
) -> tuple[bool, int, list[str]]:
    """Phase 2: Invoke one-pass diagnosis and poll for completion.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where k9b backend runs
        incident_id: The incident ID to diagnose
        pass_attempt: Current pass attempt number (1-indexed)
        max_passes: Maximum passes to allow
        result: Result dict to populate

    Returns:
        Tuple of (success, total_pass_count, all_pass_run_ids).
    """
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
        return False, 0, []

    # Check for budget exhaustion BEFORE polling - fail fast
    # The invocation returned HTTP 200 but the incident is not eligible (budget exhausted)
    if invocation_result.is_runtime_state():
        log(f"    [{current_pass_in_label}] ERROR: Loop not eligible: {invocation_result.error_detail}")
        log(f"    [{current_pass_in_label}] Budget exhausted - cannot run diagnosis")
        
        # Print structured budget diagnostics if available
        budget_summary = invocation_result.budget_summary()
        if budget_summary and budget_summary != "no budget diagnostics":
            log(f"    [{current_pass_in_label}] Budget diagnostics:")
            for bd in invocation_result.budget_diagnostics:
                status = "EXHAUSTED" if bd.get("exhausted") else "OK"
                log(
                    f"    [{current_pass_in_label}]   {bd.get('name', 'unknown')}: {status} "
                    f"used={bd.get('used', 0)} limit={bd.get('limit', 0)} "
                    f"remaining={bd.get('remaining', 0)} "
                    f"source={bd.get('source', 'unknown')} "
                    f"resettable={bd.get('resettable', True)}"
                )
        
        result["real_loop_invoked"] = False
        # Preserve actionable detail: "budget_exhausted" not just "not_eligible"
        if invocation_result.error_detail:
            result["failure_reason"] = f"{invocation_result.error_class}: {invocation_result.error_detail}"
        else:
            result["failure_reason"] = invocation_result.error_class
        return False, 0, []

    log(f"    [{current_pass_in_label}] Invocation succeeded (HTTP {invocation_result.http_status})")
    result["real_loop_invoked"] = True
    result["provider_invocation_attempted"] = True

    # Poll for diagnosis completion
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
        return False, 0, []

    # Check if loop actually ran a pass or if it was skipped/not_run
    # even though the invocation returned HTTP 200
    if poll_result.loop_summary_status == "not_run" or poll_result.loop_summary_status is None:
        log(f"    [{current_pass_in_label}] ERROR: Loop never started (loop_summary.status=not_run)")
        log(f"    [{current_pass_in_label}] Invocation returned HTTP 200 but no pass was recorded")
        result["real_loop_invoked"] = False
        result["failure_reason"] = poll_result.failure_reason
        return False, 0, []

    log(f"    [{current_pass_in_label}] Diagnosis completed: loop_summary.status={poll_result.loop_summary_status}")

    # Fetch current incident detail and extract pass information
    current_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )

    total_pass_count = 0
    all_pass_run_ids: list[str] = []

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
    return True, total_pass_count, all_pass_run_ids


def phase3_validate_artifacts(
    total_pass_count: int,
    all_pass_run_ids: list[str],
    external_analysis_dir: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Phase 3: Validate pass artifacts.

    Args:
        total_pass_count: Number of passes accumulated
        all_pass_run_ids: List of pass run IDs
        external_analysis_dir: Directory for diagnosis artifacts
        result: Result dict to populate

    Returns:
        Updated result dict.
    """
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

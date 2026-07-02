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
    count_observable_targeted_diagnosis_passes,
    extract_pass_run_ids,
    is_read_only_terminal_decision,
    is_terminal_no_checks_decision,
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
) -> tuple[bool, int, list[str], bool]:
    """Phase 2: Invoke one-pass diagnosis and poll for completion.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where k9b backend runs
        incident_id: The incident ID to diagnose
        pass_attempt: Current pass attempt number (1-indexed)
        max_passes: Maximum passes to allow
        result: Result dict to populate

    Returns:
        Tuple of (success, total_pass_count, all_pass_run_ids, post_attempted).
        The post_attempted flag indicates whether the POST was actually made,
        regardless of whether it succeeded or failed.
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
        return False, 0, [], True  # POST was attempted even though it failed

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
        return False, 0, [], True  # POST was attempted but loop was not eligible

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
        return False, 0, [], True  # POST succeeded, polling failed

    # Check if loop actually ran a pass or if it was skipped/not_run
    # even though the invocation returned HTTP 200
    if poll_result.loop_summary_status == "not_run" or poll_result.loop_summary_status is None:
        log(f"    [{current_pass_in_label}] ERROR: Loop never started (loop_summary.status=not_run)")
        log(f"    [{current_pass_in_label}] Invocation returned HTTP 200 but no pass was recorded")
        result["real_loop_invoked"] = False
        result["failure_reason"] = poll_result.failure_reason
        return False, 0, [], True  # POST succeeded, but loop didn't run

    log(f"    [{current_pass_in_label}] Diagnosis completed: loop_summary.status={poll_result.loop_summary_status}")

    # Fetch current incident detail and extract pass information
    current_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )

    total_pass_count = 0
    all_pass_run_ids: list[str] = []
    terminal_decision_reached = False

    if current_detail:
        result["backend_incident_detail"] = current_detail.to_compact_log()
        result["status"] = current_detail.status

        # Use the new helper to count observable passes
        # This handles the split-brain state where automatic_diagnosis_review is available
        # but loop_summary may be null or missing pass info
        total_pass_count = count_observable_targeted_diagnosis_passes(current_detail.raw)
        
        # Extract pass run IDs from loop_summary if available
        # Support both field naming conventions
        loop_summary = current_detail.raw.get("automatic_diagnosis_loop_summary", {}) or {}
        current_pass_run_ids = extract_pass_run_ids(loop_summary)
        # Also check legacy loop_summary field if present
        if not current_pass_run_ids and "loop_summary" in current_detail.raw:
            legacy_summary = current_detail.raw.get("loop_summary", {}) or {}
            current_pass_run_ids = extract_pass_run_ids(legacy_summary)
        # Track new passes (those not already in our list)
        new_pass_run_ids = [rid for rid in current_pass_run_ids if rid not in all_pass_run_ids]
        all_pass_run_ids.extend(new_pass_run_ids)
        
        # Check for review packet
        result["review_packet_found"] = current_detail.review_available

        # Try to extract root cause summary from loop summary
        if "root_cause_summary" in loop_summary:
            result["root_cause_summary"] = loop_summary["root_cause_summary"]

        # Check for terminal no-checks decision
        if is_terminal_no_checks_decision(current_detail.raw):
            terminal_decision_reached = True
            review = current_detail.raw.get("automatic_diagnosis_review", {})
            artifact_name = review.get("artifact_name", "unknown")
            log(f"    [{current_pass_in_label}] Diagnosis review artifact available: {review.get('artifact_type', 'unknown')}")
            log(f"    [{current_pass_in_label}] Terminal diagnosis decision: stop_no_checks_proposed")
            log(f"    [{current_pass_in_label}] Observable passes so far: {total_pass_count}")
            log(f"    [{current_pass_in_label}] Review artifact: {artifact_name}")
            
            # Check if read-only constraints are satisfied
            if is_read_only_terminal_decision(current_detail.raw):
                log(f"    [{current_pass_in_label}] Read-only constraints satisfied: review_required_before_any_action=True, no_remediation_attempted=True")
                result["terminal_no_checks_accepted"] = True
                result["terminal_decision_reached"] = True
            else:
                log(f"    [{current_pass_in_label}] WARNING: Read-only constraints not fully satisfied")

    result["terminal_decision_reached"] = terminal_decision_reached
    log(f"    [{current_pass_in_label}] Total passes so far: {total_pass_count}/{MIN_REQUIRED_PASSES}")
    return True, total_pass_count, all_pass_run_ids, True  # POST succeeded, loop completed


def phase3_validate_artifacts(
    total_pass_count: int,
    all_pass_run_ids: list[str],
    external_analysis_dir: Path,
    result: dict[str, Any],
    terminal_no_checks: bool = False,
) -> dict[str, Any]:
    """Phase 3: Validate pass artifacts.

    LAB-STRICT: This phase no longer treats terminal single-pass as success.
    The compute_p4c_outcome() function (called in phase.py) determines the
    final outcome with lab-strict semantics.

    Args:
        total_pass_count: Number of passes accumulated
        all_pass_run_ids: List of pass run IDs
        external_analysis_dir: Directory for diagnosis artifacts
        result: Result dict to populate
        terminal_no_checks: Whether a terminal no-checks decision was reached

    Returns:
        Updated result dict with pass metadata for compute_p4c_outcome().
    """
    log("  Step 5: Validating pass artifacts...")
    result["pass_count"] = total_pass_count
    result["pass_run_ids"] = all_pass_run_ids
    result["real_pass_artifacts_found"] = total_pass_count >= MIN_REQUIRED_PASSES or terminal_no_checks

    # Log terminal no-checks status (but do NOT treat as success here)
    # The compute_p4c_outcome() function determines final outcome
    # For premature terminal no-checks, ensure failure_reason is set for downstream logging
    if terminal_no_checks:
        if total_pass_count < MIN_REQUIRED_PASSES:
            log(f"  Terminal no-checks decision before required pass count: {total_pass_count} < {MIN_REQUIRED_PASSES}")
            log("  P4c diagnosis did not satisfy lab objective: premature terminal no-checks")
            log("  This will be evaluated by compute_p4c_outcome() with lab-strict semantics")
            # Explicitly mark this as premature for compute_p4c_outcome()
            result["premature_terminal_no_checks"] = True
            # Set failure_reason so legacy callers can see the issue
            result["failure_reason"] = f"premature_terminal_no_checks: {total_pass_count} < {MIN_REQUIRED_PASSES}"
        else:
            log(f"  Backend-targeted diagnosis completed: terminal no-checks ({total_pass_count} observable passes)")
            log("  Final outcome determined by compute_p4c_outcome()")
    elif total_pass_count < MIN_REQUIRED_PASSES:
        result["failure_reason"] = FAILURE_TARGETED_INSUFFICIENT_PASSES
        result["real_pass_artifacts_found"] = False
        log(f"  ERROR: Insufficient passes: {result['pass_count']} < {MIN_REQUIRED_PASSES}")
        return result
    else:
        log(f"  Backend-targeted diagnosis completed: {result['pass_count']} passes")

    # Always populate pass_artifact_paths when we have pass IDs
    if all_pass_run_ids:
        result["pass_artifact_paths"] = [
            str(external_analysis_dir / "diagnosis-loop-passes" / f"{rid}.json")
            for rid in all_pass_run_ids
        ]
        result["artifact_path"] = str(external_analysis_dir / "diagnosis-loop-passes")

    return result

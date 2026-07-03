"""Runner execution for K8s multi-pass diagnosis phase.

This module provides the main execution logic for running the automatic
diagnosis loop and simulation fallback.

Architecture:
- P4c uses backend-targeted automatic diagnosis-loop one-pass via
  POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import log
from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
    BudgetResetResult,
    get_budget_status_in_backend,
    reset_diagnosis_loop_budget_in_backend,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DEFAULT_MAX_PASSES,
    DIAGNOSIS_SOURCE_SIMULATED,
    MIN_REQUIRED_PASSES,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_config import (
    get_shipping_root_cause_summary,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
    phase1_confirm_incident,
    phase2_invoke_and_poll_pass,
    phase3_validate_artifacts,
)


def run_backend_targeted_diagnosis(
    incident_id: str,
    external_analysis_dir: Path,
    kubeconfig: str,
    namespace: str,
    result: dict[str, Any],
    allow_simulation: bool,
    max_passes: int = DEFAULT_MAX_PASSES,
    require_complete_root_cause_before_stop: bool = False,
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
        max_passes: Maximum passes to allow
        require_complete_root_cause_before_stop: If True (P4c lab-strict mode),
            stop_no_checks_proposed requires complete scheduling root cause evidence.

    Returns:
        Result dict with diagnosis loop results
    """
    log(f"  Using backend-targeted diagnosis for incident {incident_id}")

    # Step 1: Confirm incident exists in backend
    incident_detail = phase1_confirm_incident(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        result=result,
    )

    if incident_detail is None:
        return result

    # Initialize pass tracking
    total_pass_count = 0
    all_pass_run_ids: list[str] = []
    all_review_artifact_paths: list[str] = []

    # Step 2: Reset budget state for deterministic P4c isolation
    # CRITICAL: Must reset budget in the BACKEND's artifact root (runs/health/external-analysis/)
    # NOT in the lab's lab-artifacts/ directory. The backend's eligibility check looks at
    # its own artifact root, not the lab output directory.
    log(f"  Step 2: Checking and resetting budget state for incident {incident_id}...")
    
    # Get budget status from backend container
    budget_before = get_budget_status_in_backend(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )
    log(f"    Budget before reset: {budget_before.get('review_packet_count', 0)} review packets (in backend container)")

    # Reset budget in backend container
    reset_result: BudgetResetResult = reset_diagnosis_loop_budget_in_backend(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )
    log(f"    Reset {reset_result.reset_file_count} budget files (context: {reset_result.execution_context})")

    # Verify budget was reset
    budget_after = get_budget_status_in_backend(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
    )
    log(f"    Budget after reset: {budget_after.get('review_packet_count', 0)} review packets")

    # Step 2b: Fail-fast if reset failed
    # Enforce the invariant: after reset, total_auto_artifact_count == 0
    # This prevents confusing downstream budget_exhausted errors
    if reset_result.error is not None:
        result["failure_reason"] = f"budget_reset_backend_error:{reset_result.error}"
        result["status"] = "budget_reset_failed"
        result["real_loop_invoked"] = False
        return result

    if budget_after.get("error"):
        result["failure_reason"] = f"budget_status_backend_error:{budget_after['error']}"
        result["status"] = "budget_status_failed"
        result["real_loop_invoked"] = False
        return result

    remaining = int(budget_after.get("total_auto_artifact_count", 0))
    if remaining > 0:
        result["failure_reason"] = f"budget_reset_failed_artifacts_remain:{remaining}"
        result["status"] = "budget_reset_incomplete"
        result["real_loop_invoked"] = False
        return result

    # Step 3: Loop targeted one-pass endpoint until pass_count >= MIN_REQUIRED_PASSES
    # OR a terminal no-checks decision is reached (valid single-pass success)
    log(f"  Step 3: Looping targeted diagnosis until pass_count >= {MIN_REQUIRED_PASSES}...")

    terminal_no_checks_reached = False
    invocation_count = 0

    for pass_attempt in range(1, max_passes + 1):
        success, pass_count, pass_run_ids, post_attempted, review_artifact_path = phase2_invoke_and_poll_pass(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
            pass_attempt=pass_attempt,
            max_passes=max_passes,
            result=result,
            # P4c lab-strict mode: require complete root cause before accepting stop_no_checks_proposed
            require_complete_root_cause_before_stop=require_complete_root_cause_before_stop,
        )
        # Track actual POST attempts, not just phase invocations
        if post_attempted:
            invocation_count += 1

        if not success:
            if pass_attempt == 1:
                result["failure_reason"] = result.get("targeted_invocation_result", {}).get("error_class")
                result["status"] = "invocation_failed"
                result["real_loop_invoked"] = False
                return result
            else:
                # Log failure but continue with accumulated passes
                log(f"    [pass {pass_attempt}/{max_passes}] WARNING: Pass invocation failed, using accumulated passes")
                break

        # Merge pass run IDs - accumulate from all invocations FIRST.
        # This must happen before max() so len(all_pass_run_ids) reflects post-merge state.
        for rid in pass_run_ids:
            if rid not in all_pass_run_ids:
                all_pass_run_ids.append(rid)

        # EVIDENCE PRESERVATION: Accumulate review artifact paths from all passes.
        # This is the fallback observable pass evidence when pass_run_ids are not available.
        # The backend may not return stable pass_run_ids across multiple targeted-diagnosis calls,
        # but review artifacts are observable and persisted during each pass.
        if review_artifact_path and review_artifact_path not in all_review_artifact_paths:
            all_review_artifact_paths.append(review_artifact_path)

        # Update pass tracking - ACCUMULATE from all invocations.
        # The backend's current state may only show recent passes (split-brain state),
        # so we track the maximum observed across all invocations.
        # HARDENING: Also consider len(all_pass_run_ids) after merging current IDs
        # to be resilient when backend loop_summary is latest-only.
        total_pass_count = max(total_pass_count, pass_count, len(all_pass_run_ids))

        # Check for terminal no-checks decision AFTER pass count check
        # LAB-STRICT: Terminal no-checks alone is not sufficient - we must have
        # accumulated min_required_passes observable passes before accepting it.
        # Only break early if both conditions are met:
        # 1. Terminal no-checks decision was reached
        # 2. We have accumulated at least MIN_REQUIRED_PASSES
        if result.get("terminal_no_checks_accepted") and total_pass_count >= MIN_REQUIRED_PASSES:
            terminal_no_checks_reached = True
            log(f"    [pass {pass_attempt}/{max_passes}] Terminal no-checks decision with {total_pass_count} passes: stopping loop")
            break

        # Standard pass count check
        if total_pass_count >= MIN_REQUIRED_PASSES:
            log(f"    [pass {pass_attempt}/{max_passes}] SUCCESS: Required passes met ({total_pass_count} >= {MIN_REQUIRED_PASSES})")
            break
        elif pass_attempt < max_passes:
            log(f"    [pass {pass_attempt}/{max_passes}] Need more passes, continuing loop...")
        else:
            log(f"    [pass {pass_attempt}/{max_passes}] Reached max_passes limit ({max_passes})")

    # Store invocation metadata for failure diagnostics
    result["targeted_invocation_count"] = invocation_count
    result["targeted_invocation_attempted"] = invocation_count > 0

    # Step 4: Final validation
    # Pass terminal_no_checks flag to validation
    # Also detect premature terminal no-checks (terminal accepted but insufficient passes)
    # This needs to be explicitly flagged since terminal_no_checks_reached only tracks
    # the post-loop state where both conditions were met
    premature_terminal = (
        result.get("terminal_no_checks_accepted", False)
        and total_pass_count < MIN_REQUIRED_PASSES
    )
    if premature_terminal:
        result["premature_terminal_no_checks"] = True

    result = phase3_validate_artifacts(
        total_pass_count=total_pass_count,
        all_pass_run_ids=all_pass_run_ids,
        external_analysis_dir=external_analysis_dir,
        result=result,
        terminal_no_checks=terminal_no_checks_reached or premature_terminal,
        all_review_artifact_paths=all_review_artifact_paths,
    )

    return result


def simulate_diagnosis_loop(
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
    root_cause_summary = get_shipping_root_cause_summary()

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
            "component": "shipping",
            "issue": "unschedulable_pod",
            "root_cause": "impossible nodeSelector: k8s.injection/node-label=injected-value",
            "evidence": [
                "PendingPod for shipping-* with reason Unschedulable",
                "FailedScheduling event indicating no matching node",
                "nodeSelector: k8s.injection/node-label: injected-value",
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


def extract_root_cause_from_review(review_data: dict[str, Any]) -> str:
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

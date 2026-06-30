"""Runtime envelope that wraps orchestrator with DiagnosisLoopPolicy enforcement.

This module provides the outer controller layer that:
- Owns the DiagnosisLoopPolicy hard budget limits
- Gates checks BEFORE execution (mutating, sensitive, duplicates)
- Emits pass artifacts with exact PASS_ARTIFACT_FIELDS
- Maps loop decisions to typed LoopStopReason

Design constraints:
- Splits planning from execution: plan first, gate, then execute
- Does NOT replace NextCheckPolicy (planner semantic layer)
- Emits artifacts matching PASS_ARTIFACT_FIELDS
- Deterministic with injected timestamps
- Explicit OTel span boundaries
- Pre-execution enforcement: rejected checks are NEVER executed
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)

from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_otel import (
    emit_check_gate_span,
    emit_loop_span,
    emit_pass_span,
)
from .incident_diagnosis_loop_runtime_utils import (
    compute_case_file_hash,
    is_safe_run_id,
)
from .incident_read_only_check_runner import (
    ReadOnlyCheckHandler,
    run_read_only_checks,
)
from .runtime_artifacts import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    build_policy_enforced_pass_artifact,
    write_runtime_pass_artifact,
)
from .runtime_budgets import enforce_budgets
from .runtime_gating import GateSummary, gate_checks
from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass

__all__ = [
    "run_policy_enforced_loop_pass",
    "run_policy_enforced_loop",
    "gate_checks",
    "build_policy_enforced_pass_artifact",
    "LoopRuntimeState",
    "GateSummary",
    "RUNTIME_SCHEMA_VERSION",
    "P4C_DIAGNOSIS_SUBDIR",
    "P4C_LOOP_PASSES_SUBDIR",
]


# =============================================================================
# Public API: Single Pass
# =============================================================================


def run_policy_enforced_loop_pass(
    *,
    incident_id: str,
    external_analysis_dir: Path,
    case_file: Mapping[str, object],
    diagnosis_report: Mapping[str, object],
    run_id: str,
    policy: DiagnosisLoopPolicy | None = None,
    prior_loop_state: Mapping[str, object] | None = None,
    runtime_state: LoopRuntimeState | None = None,
    now: datetime | None = None,
    fake_handlers: Mapping[str, ReadOnlyCheckHandler] | None = None,
) -> dict[str, object]:
    """Run one diagnosis loop pass with PRE-EXECUTION policy enforcement.

    This is the main entry point for the policy-enforced runtime:
    1. Validate run_id for safety
    2. Use DiagnosisLoopPolicy (or default)
    3. Check budget limits BEFORE any execution
    4. Gate checks against policy BEFORE execution
    5. Execute ONLY accepted checks
    6. Emit pass artifact with PASS_ARTIFACT_FIELDS
    7. Return augmented result

    CRITICAL: Rejected checks are NEVER executed.
    
    Execution order is STRUCTURALLY enforced:
    1. Plan (via plan_one_read_only_diagnosis_loop_pass - NO execution)
    2. Enforce budgets
    3. Gate proposed checks
    4. Execute ONLY accepted checks (via run_read_only_checks)
    5. Build pass artifact
    6. Write P4c artifact
    """
    from .incident_diagnosis_loop_orchestrator import (
        plan_one_read_only_diagnosis_loop_pass,
    )

    # Validate run_id
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve policy
    resolved_policy = policy if policy is not None else DiagnosisLoopPolicy.live_lab_default()
    resolved_now = now if now is not None else datetime.now(UTC)

    # Resolve or create runtime state
    if runtime_state is not None:
        current_state = runtime_state
    else:
        loop_run_id = f"{run_id}-{resolved_now.strftime('%Y%m%d%H%M%S')}"
        current_state = LoopRuntimeState(
            loop_run_id=loop_run_id,
            incident_id=incident_id,
            started_at=resolved_now.isoformat(),
        )

    # Emit loop start span (only on first pass)
    if current_state.pass_index == 1:
        emit_loop_span(current_state.loop_run_id, incident_id, resolved_policy, "started")

    # Check budgets BEFORE any planning
    elapsed_seconds = (resolved_now - datetime.fromisoformat(current_state.started_at)).total_seconds()
    elapsed_seconds = max(0, elapsed_seconds)
    
    budget_exceeded, budget_stop_reason = enforce_budgets(
        resolved_policy, current_state, elapsed_seconds
    )

    # STEP 1: Plan WITHOUT executing checks (planner-only seam)
    # This returns loop_update with proposed_next_checks but NO runner_result
    planner_result = plan_one_read_only_diagnosis_loop_pass(
        incident_id=incident_id,
        case_file=case_file,
        diagnosis_report=diagnosis_report,
        run_id=run_id,
        prior_loop_state=prior_loop_state,
        now=resolved_now,
    )

    # Extract loop update for gating decisions
    loop_update = planner_result.get("loop_update", {})
    decision = str(planner_result.get("decision", ""))

    # Get proposed checks from loop update
    proposed_checks = loop_update.get("proposed_next_checks", [])
    if not isinstance(proposed_checks, list):
        proposed_checks = []

    # STEP 2: Gate checks BEFORE execution using persistent seen_fingerprints
    seen_fingerprints = set(current_state.seen_check_fingerprints)
    gate_summary, accepted_fingerprints = gate_checks(proposed_checks, resolved_policy, seen_fingerprints)

    # STEP 3: Enforce max_checks_per_pass after gating
    if gate_summary.accepted > resolved_policy.max_checks_per_pass:
        # Reject overflow - only execute up to the cap
        # Slice accepted_checks to only the first max_checks_per_pass
        gate_summary.accepted_checks = gate_summary.accepted_checks[:resolved_policy.max_checks_per_pass]
        gate_summary.accepted_fingerprints = gate_summary.accepted_fingerprints[:resolved_policy.max_checks_per_pass]
        gate_summary.accepted = len(gate_summary.accepted_checks)

    # If budget is exceeded, DO NOT execute checks
    if budget_exceeded:
        decision = LoopDecision.STOP_BUDGET_EXHAUSTED.value

    # Extract root cause info from loop update
    root_cause_summary = ""
    root_cause = loop_update.get("root_cause_candidate", {})
    if isinstance(root_cause, dict):
        root_cause_summary = str(root_cause.get("summary", ""))
    confidence = "unknown"
    if isinstance(root_cause, dict):
        confidence = str(root_cause.get("confidence", "unknown"))

    # STEP 4: Execute ONLY accepted checks (AFTER gating)
    runner_result: dict[str, Any] | None = None
    if gate_summary.accepted > 0 and not budget_exceeded and decision == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
        # Execute only the accepted checks - rejected checks never reach here
        runner_result = run_read_only_checks(
            incident_id=incident_id,
            run_id=run_id,
            accepted_checks=gate_summary.accepted_checks,
            now=resolved_now,
            fake_handlers=fake_handlers,
        )

    # STEP 5: Build the pass artifact with ONLY accepted fingerprints for this pass
    pass_artifact = build_policy_enforced_pass_artifact(
        loop_run_id=current_state.loop_run_id,
        incident_id=incident_id,
        pass_index=current_state.pass_index,
        case_file=case_file,
        policy=resolved_policy,
        gate_summary=gate_summary,
        accepted_fingerprints=accepted_fingerprints,
        runtime_state=current_state,
        decision=decision,
        root_cause_summary=root_cause_summary,
        confidence=confidence,
        runner_result=runner_result,
        now=resolved_now,
        budget_exceeded=budget_exceeded,
        budget_stop_reason=budget_stop_reason,
    )

    # Validate pass artifact schema
    from k8s_diag_agent.collect.incident_diagnosis_loop_policy import validate_pass_artifact_schema
    is_valid, missing = validate_pass_artifact_schema(pass_artifact)
    if not is_valid:
        pass_artifact["_schema_error"] = f"Missing required fields: {missing}"

    # Emit pass span
    stop_reason = pass_artifact.get("stop_reason")
    emit_pass_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        decision=decision,
        stop_reason=stop_reason,
        checks_accepted=gate_summary.accepted,
        checks_rejected=gate_summary.rejected_mutating + gate_summary.rejected_sensitive + gate_summary.rejected_duplicate,
    )

    # Emit check gate spans for each gated check (BEFORE execution)
    for check in gate_summary.accepted_checks:
        emit_check_gate_span(current_state.loop_run_id, current_state.pass_index, str(check.get("check_id", "")), True, None)

    for check in gate_summary.rejected_checks:
        emit_check_gate_span(current_state.loop_run_id, current_state.pass_index, str(check.get("check_id", "")), False, check.get("rejection_reason"))

    # Write pass artifact to P4c path
    p4c_artifact_path = write_runtime_pass_artifact(
        external_analysis_dir=external_analysis_dir,
        loop_run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        artifact=pass_artifact,
    )

    # Emit loop complete span (only on final pass)
    emit_loop_span(current_state.loop_run_id, incident_id, resolved_policy, "completed")

    # Build augmented result
    case_file_hash = compute_case_file_hash(case_file)
    result = dict(planner_result)
    result["policy_enforced"] = True
    result["policy"] = resolved_policy.to_dict()
    result["gate_summary"] = {
        "proposed": gate_summary.proposed,
        "accepted": gate_summary.accepted,
        "rejected_mutating": gate_summary.rejected_mutating,
        "rejected_sensitive": gate_summary.rejected_sensitive,
        "rejected_duplicate": gate_summary.rejected_duplicate,
        "rejected_checks": [c.get("rejection_reason", "unknown") for c in gate_summary.rejected_checks],
    }
    result["pass_artifact"] = pass_artifact
    result["p4c_artifact_path"] = str(p4c_artifact_path) if p4c_artifact_path else None
    result["case_file_hash"] = case_file_hash
    result["budget_exceeded"] = budget_exceeded
    result["budget_stop_reason"] = budget_stop_reason.value if budget_stop_reason else None

    return result


# =============================================================================
# Public API: Multi-Pass Loop
# =============================================================================


def run_policy_enforced_loop(
    *,
    incident_id: str,
    external_analysis_dir: Path,
    case_file: Mapping[str, object],
    diagnosis_report: Mapping[str, object],
    run_id: str,
    policy: DiagnosisLoopPolicy | None = None,
    now: datetime | None = None,
    fake_handlers: Mapping[str, ReadOnlyCheckHandler] | None = None,
) -> dict[str, object]:
    """Run the complete policy-enforced diagnosis loop.
    
    This function manages multi-pass execution with:
    - Persistent LoopRuntimeState across passes
    - Pre-execution policy gating
    - Budget enforcement before each pass
    - Proper P4c artifact path writing
    
    Returns:
        Dict with loop results and all pass artifacts
    """
    # Validate run_id
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve policy
    resolved_policy = policy if policy is not None else DiagnosisLoopPolicy.live_lab_default()
    resolved_now = now if now is not None else datetime.now(UTC)

    # Create initial runtime state
    loop_run_id = f"{run_id}-{resolved_now.strftime('%Y%m%d%H%M%S')}"
    runtime_state = LoopRuntimeState(
        loop_run_id=loop_run_id,
        incident_id=incident_id,
        started_at=resolved_now.isoformat(),
    )

    # Emit loop start span
    emit_loop_span(loop_run_id, incident_id, resolved_policy, "started")

    # Track results across passes
    pass_results: list[dict[str, object]] = []
    all_pass_artifacts: list[dict[str, Any]] = []
    
    # Track persistent state
    seen_fingerprints = set(runtime_state.seen_check_fingerprints)
    total_checks_executed = runtime_state.total_checks_executed
    total_mutating_executed = runtime_state.total_mutating_executed
    total_sensitive_executed = runtime_state.total_sensitive_executed

    # Run passes until stop condition
    should_continue = True
    
    while should_continue:
        # Check budgets before next pass
        elapsed_seconds = (resolved_now - datetime.fromisoformat(runtime_state.started_at)).total_seconds()
        elapsed_seconds = max(0, elapsed_seconds)
        
        budget_exceeded, budget_stop_reason = enforce_budgets(
            resolved_policy, runtime_state, elapsed_seconds
        )
        
        if budget_exceeded:
            # Create stop artifact with ALL PASS_ARTIFACT_FIELDS
            stop_artifact = {
                # PASS_ARTIFACT_FIELDS
                "loop_run_id": loop_run_id,
                "incident_id": incident_id,
                "pass_index": runtime_state.pass_index,
                "case_file_hash": "",  # No case file on budget stop
                "proposed_checks": [],
                "accepted_checks": [],
                "rejected_checks": [],
                "check_fingerprints": [],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "",
                "confidence": "unknown",
                "should_continue": False,
                "stop_reason": budget_stop_reason.value if budget_stop_reason else LoopStopReason.MAX_CHECKS_REACHED.value,
                # Additional fields
                "decision": LoopDecision.STOP_BUDGET_EXHAUSTED.value,
                "budget_exceeded": True,
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "generated_at": resolved_now.isoformat(),
            }
            pass_results.append({
                "stop_reason": budget_stop_reason.value if budget_stop_reason else LoopStopReason.MAX_CHECKS_REACHED.value,
                "budget_exceeded": True,
            })
            all_pass_artifacts.append(stop_artifact)
            break

        # Run single pass
        pass_result = run_policy_enforced_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            policy=resolved_policy,
            runtime_state=runtime_state,
            now=resolved_now,
            fake_handlers=fake_handlers,
        )
        
        pass_results.append(pass_result)
        
        # Extract pass artifact with explicit type handling
        pass_artifact = {}
        raw_artifact = pass_result.get("pass_artifact")
        if isinstance(raw_artifact, dict):
            pass_artifact = raw_artifact
        all_pass_artifacts.append(pass_artifact)
        
        # Update persistent state
        gate_summary = pass_result.get("gate_summary", {})
        accepted_count = gate_summary.get("accepted", 0)
        total_checks_executed += accepted_count
        
        # Update runtime state for next iteration
        runtime_state = runtime_state.with_updates(
            pass_index=runtime_state.pass_index + 1,
            seen_check_fingerprints=frozenset(seen_fingerprints),
            total_checks_executed=total_checks_executed,
            total_mutating_executed=total_mutating_executed,
            total_sensitive_executed=total_sensitive_executed,
        )
        
        # Check if loop should continue
        should_continue = pass_artifact.get("should_continue", False)

    # Emit loop complete span
    emit_loop_span(loop_run_id, incident_id, resolved_policy, "completed")

    # Build final result
    final_result = {
        "loop_run_id": loop_run_id,
        "incident_id": incident_id,
        "total_passes": len(pass_results),
        "total_checks_executed": total_checks_executed,
        "pass_results": pass_results,
        "pass_artifacts": all_pass_artifacts,
        "final_stop_reason": pass_results[-1].get("stop_reason") if pass_results else None,
        "policy": resolved_policy.to_dict(),
    }

    return final_result

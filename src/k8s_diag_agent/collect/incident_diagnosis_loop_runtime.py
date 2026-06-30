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

from .incident_diagnosis_loop_otel import (
    emit_artifact_written_event,
    emit_budget_exceeded_event,
    emit_check_gate_span,
    emit_check_rejected_event,
    emit_checks_executed_event,
    emit_loop_span,
    emit_pass_span,
    emit_stop_event,
    record_exception,
    set_span_error,
    set_span_ok,
    start_artifact_span,
    start_budget_span,
    start_execute_span,
    start_gate_span,
    start_loop_span,
    start_pass_span,
    start_plan_span,
    SpanContext,
)

# Re-export contract types for stable public API
from .incident_diagnosis_loop_runtime_contract import (
    PASS_ARTIFACT_FIELDS,
)
from .incident_diagnosis_loop_runtime_helpers import (
    _build_budget_exceeded_result,
    build_budget_exceeded_stop_artifact,
    build_loop_stop_artifact,
)
from .incident_diagnosis_loop_runtime_rendering import (
    render_gate_summary,
    render_loop_summary,
    render_runtime_summary,
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
    # Core runtime functions
    "run_policy_enforced_loop_pass",
    "run_policy_enforced_loop",
    # Gating
    "gate_checks",
    "GateSummary",
    # Artifact building
    "build_policy_enforced_pass_artifact",
    # State
    "LoopRuntimeState",
    "RUNTIME_SCHEMA_VERSION",
    # Constants
    "P4C_DIAGNOSIS_SUBDIR",
    "P4C_LOOP_PASSES_SUBDIR",
    # Contract types
    "DiagnosisLoopPolicy",
    "LoopStopReason",
    "PASS_ARTIFACT_FIELDS",
    # Rendering helpers
    "render_runtime_summary",
    "render_loop_summary",
    "render_gate_summary",
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

    # Start pass span for OTel instrumentation
    pass_span_ctx: SpanContext | None = None
    pass_span: Any = None
    
    # Check budgets BEFORE any planning
    elapsed_seconds = (resolved_now - datetime.fromisoformat(current_state.started_at)).total_seconds()
    elapsed_seconds = max(0, elapsed_seconds)
    
    # Start budget span
    budget_span_ctx = start_budget_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        budget_exceeded=False,  # Will be updated
        stop_reason=None,
    )
    
    budget_exceeded, budget_stop_reason = enforce_budgets(
        resolved_policy, current_state, elapsed_seconds
    )
    
    # Update budget span with actual result
    if budget_exceeded:
        emit_budget_exceeded_event(budget_span_ctx.span, budget_stop_reason.value if budget_stop_reason else "unknown")
        emit_loop_span(current_state.loop_run_id, incident_id, resolved_policy, "completed")

    # If budget is already exceeded, do NOT plan - use helper to build stop artifact
    if budget_exceeded:
        pass_artifact = build_budget_exceeded_stop_artifact(
            loop_run_id=current_state.loop_run_id,
            incident_id=incident_id,
            pass_index=current_state.pass_index,
            case_file=case_file,
            policy=resolved_policy,
            budget_stop_reason=budget_stop_reason,
            now=resolved_now,
            fake_handlers=fake_handlers,
        )
        
        # Write pass artifact to P4c path
        p4c_artifact_path = write_runtime_pass_artifact(
            external_analysis_dir=external_analysis_dir,
            loop_run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
            artifact=pass_artifact,
        )
        
        # Instrument artifact span
        artifact_span_ctx = start_artifact_span(
            run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
            artifact_path=str(p4c_artifact_path) if p4c_artifact_path else None,
            schema_valid=False,  # Budget exceeded artifact may be incomplete
            missing_fields=0,
            new_evidence_count=0,
        )
        emit_artifact_written_event(artifact_span_ctx.span, str(p4c_artifact_path) if p4c_artifact_path else "", False)
        
        # Emit stop event on budget span
        emit_stop_event(budget_span_ctx.span, budget_stop_reason.value if budget_stop_reason else "unknown")
        set_span_ok(budget_span_ctx.span)
        
        # Build result using helper
        return _build_budget_exceeded_result(
            pass_artifact=pass_artifact,
            resolved_policy=resolved_policy,
            budget_stop_reason=budget_stop_reason,
            case_file=case_file,
        )

    # STEP 1: Plan WITHOUT executing checks (planner-only seam)
    # This returns loop_update with proposed_next_checks but NO runner_result
    plan_span_ctx = start_plan_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
    )
    
    try:
        planner_result = plan_one_read_only_diagnosis_loop_pass(
            incident_id=incident_id,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            prior_loop_state=prior_loop_state,
            now=resolved_now,
        )
        set_span_ok(plan_span_ctx.span)
    except Exception as exc:
        record_exception(plan_span_ctx.span, exc)
        set_span_error(plan_span_ctx.span)
        raise

    # Extract loop update for gating decisions
    loop_update = planner_result.get("loop_update", {})
    decision = str(planner_result.get("decision", ""))

    # Get proposed checks from loop update
    proposed_checks = loop_update.get("proposed_next_checks", [])
    if not isinstance(proposed_checks, list):
        proposed_checks = []

    # STEP 2: Gate checks BEFORE execution using persistent seen_fingerprints
    seen_fingerprints = set(current_state.seen_check_fingerprints)
    
    # Start gate span (will update counts after gating)
    gate_span_ctx = start_gate_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        proposed=len(proposed_checks),
        accepted=0,
        rejected_mutating=0,
        rejected_sensitive=0,
        rejected_duplicate=0,
        rejected_budget=0,
    )
    
    gate_summary, accepted_fingerprints = gate_checks(proposed_checks, resolved_policy, seen_fingerprints)

    # STEP 3: Enforce max_checks_per_pass after gating - explicitly reject overflow
    rejected_budget_count = 0
    if gate_summary.accepted > resolved_policy.max_checks_per_pass:
        # Reject overflow - only execute up to the cap
        overflow_checks = gate_summary.accepted_checks[resolved_policy.max_checks_per_pass:]
        overflow_fingerprints = gate_summary.accepted_fingerprints[resolved_policy.max_checks_per_pass:]
        rejected_budget_count = len(overflow_checks)
        
        # Add overflow to rejected checks with explicit reason
        for check, fp in zip(overflow_checks, overflow_fingerprints):
            check_dict = dict(check)
            check_dict["rejection_reason"] = "max_checks_per_pass_exceeded"
            check_dict["rejected_fingerprint"] = fp
            gate_summary.rejected_checks.append(check_dict)
            gate_summary.rejected_fingerprints.append(fp)
        
        # Update accepted to only the first max_checks_per_pass
        gate_summary.accepted_checks = gate_summary.accepted_checks[:resolved_policy.max_checks_per_pass]
        gate_summary.accepted_fingerprints = gate_summary.accepted_fingerprints[:resolved_policy.max_checks_per_pass]
        gate_summary.accepted = len(gate_summary.accepted_checks)
    
    # Emit rejection events for each rejected check
    for check in gate_summary.rejected_checks:
        rejection_reason = check.get("rejection_reason", "unknown")
        emit_check_rejected_event(
            gate_span_ctx.span,
            check_id=str(check.get("check_id", "")),
            rejection_reason=rejection_reason,
            is_unsafe=(rejection_reason == "mutating_check_rejected"),
            is_sensitive=(rejection_reason == "sensitive_read_denied"),
        )
    
    # Use gate_summary.accepted_fingerprints for the artifact (it's the authoritative list after truncation)
    artifact_accepted_fingerprints = list(gate_summary.accepted_fingerprints)
    
    # Update seen_fingerprints to include new accepted fingerprints for all_seen_fingerprints
    updated_seen_fingerprints = seen_fingerprints | set(artifact_accepted_fingerprints)
    
    # Create updated runtime state for artifact
    updated_runtime_state = current_state.with_updates(
        seen_check_fingerprints=frozenset(updated_seen_fingerprints),
    )

    # Extract root cause info from loop update
    root_cause_summary = ""
    root_cause = loop_update.get("root_cause_candidate", {})
    if isinstance(root_cause, dict):
        root_cause_summary = str(root_cause.get("summary", ""))
    confidence = "unknown"
    if isinstance(root_cause, dict):
        confidence = str(root_cause.get("confidence", "unknown"))

    # STEP 4: Execute ONLY accepted checks (AFTER gating)
    # Execute if gate accepted any checks AND budget not exceeded
    # Note: Planner decision is informational; gate acceptance overrides planner's stop decision
    runner_result: dict[str, Any] | None = None
    if gate_summary.accepted > 0 and not budget_exceeded:
        # Start execute span
        execute_span_ctx = start_execute_span(
            run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
            checks_count=gate_summary.accepted,
            runner_kind="read_only",
        )
        
        # Execute only the accepted checks - rejected checks never reach here
        try:
            runner_result = run_read_only_checks(
                incident_id=incident_id,
                run_id=run_id,
                accepted_checks=gate_summary.accepted_checks,
                now=resolved_now,
                fake_handlers=fake_handlers,
            )
            emit_checks_executed_event(execute_span_ctx.span, gate_summary.accepted)
            set_span_ok(execute_span_ctx.span)
        except Exception as exc:
            record_exception(execute_span_ctx.span, exc)
            set_span_error(execute_span_ctx.span)
            raise

    # STEP 5: Build the pass artifact with ONLY accepted fingerprints for this pass
    pass_artifact = build_policy_enforced_pass_artifact(
        loop_run_id=current_state.loop_run_id,
        incident_id=incident_id,
        pass_index=current_state.pass_index,
        case_file=case_file,
        policy=resolved_policy,
        gate_summary=gate_summary,
        accepted_fingerprints=artifact_accepted_fingerprints,
        runtime_state=updated_runtime_state,
        decision=decision,
        root_cause_summary=root_cause_summary,
        confidence=confidence,
        runner_result=runner_result,
        now=resolved_now,
        budget_exceeded=budget_exceeded,
        budget_stop_reason=budget_stop_reason,
        fake_handlers=fake_handlers,
    )

    # Validate pass artifact schema
    from k8s_diag_agent.collect.incident_diagnosis_loop_policy import validate_pass_artifact_schema
    is_valid, missing = validate_pass_artifact_schema(pass_artifact)
    if not is_valid:
        pass_artifact["_schema_error"] = f"Missing required fields: {missing}"

    # Write pass artifact to P4c path
    p4c_artifact_path = write_runtime_pass_artifact(
        external_analysis_dir=external_analysis_dir,
        loop_run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        artifact=pass_artifact,
    )

    # Instrument artifact span
    artifact_span_ctx = start_artifact_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        artifact_path=str(p4c_artifact_path) if p4c_artifact_path else None,
        schema_valid=is_valid,
        missing_fields=len(missing),
        new_evidence_count=len(pass_artifact.get("new_evidence_hashes", [])),
    )
    emit_artifact_written_event(artifact_span_ctx.span, str(p4c_artifact_path) if p4c_artifact_path else "", is_valid)
    set_span_ok(artifact_span_ctx.span)

    # Emit pass span with summary
    stop_reason = pass_artifact.get("stop_reason")
    emit_pass_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        decision=decision,
        stop_reason=stop_reason,
        checks_accepted=gate_summary.accepted,
        checks_rejected=gate_summary.rejected_mutating + gate_summary.rejected_sensitive + gate_summary.rejected_duplicate + rejected_budget_count,
    )

    # Emit loop complete span (only on final pass)
    emit_loop_span(current_state.loop_run_id, incident_id, resolved_policy, "completed")

    # Emit stop event
    emit_stop_event(artifact_span_ctx.span, stop_reason if stop_reason else "unknown")
    set_span_ok(budget_span_ctx.span)

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
            # Use helper to build stop artifact
            stop_artifact = build_loop_stop_artifact(
                loop_run_id=loop_run_id,
                incident_id=incident_id,
                pass_index=runtime_state.pass_index,
                case_file=case_file,
                budget_stop_reason=budget_stop_reason,
                now=resolved_now,
            )
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

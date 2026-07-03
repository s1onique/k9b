"""Single-pass runtime execution with policy enforcement.

This module provides run_policy_enforced_loop_pass() which executes one diagnosis
loop pass with PRE-EXECUTION policy enforcement.

Design constraints:
- Splits planning from execution: plan first, gate, then execute
- Does NOT replace NextCheckPolicy (planner semantic layer)
- Emits artifacts matching PASS_ARTIFACT_FIELDS
- Deterministic with injected timestamps
- Explicit OTel span boundaries using `with` blocks
- Pre-execution enforcement: rejected checks are NEVER executed
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    validate_pass_artifact_schema,
)

from .incident_diagnosis_loop_otel import (
    emit_artifact_written_event,
    emit_budget_exceeded_event,
    emit_check_rejected_event,
    emit_checks_executed_event,
    emit_loop_span,
    emit_pass_span,
    emit_stop_event,
    start_artifact_span,
    start_budget_span,
    start_execute_span,
    start_gate_span,
    start_plan_span,
)
from .incident_diagnosis_loop_runtime_helpers import (
    _build_budget_exceeded_result,
    build_budget_exceeded_stop_artifact,
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
    build_policy_enforced_pass_artifact,
    write_runtime_pass_artifact,
)
from .runtime_budgets import enforce_budgets
from .runtime_gating import gate_checks
from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass

__all__ = [
    "run_policy_enforced_loop_pass",
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
    require_complete_root_cause_before_stop: bool = False,
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

    # Calculate elapsed time for budget check
    elapsed_seconds = (resolved_now - datetime.fromisoformat(current_state.started_at)).total_seconds()
    elapsed_seconds = max(0, elapsed_seconds)

    # Start budget span with `with` block for proper lifecycle
    with start_budget_span(
        run_id=current_state.loop_run_id,
        pass_index=current_state.pass_index,
        budget_exceeded=False,  # Will be updated
        stop_reason=None,
    ) as budget_span_ctx:
        budget_exceeded, budget_stop_reason = enforce_budgets(
            resolved_policy, current_state, elapsed_seconds
        )
        
        # Handle budget exceeded path
        if budget_exceeded:
            emit_budget_exceeded_event(
                budget_span_ctx,
                budget_stop_reason.value if budget_stop_reason else "unknown"
            )
            emit_loop_span(current_state.loop_run_id, incident_id, resolved_policy, "completed")

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
            
            p4c_artifact_path = write_runtime_pass_artifact(
                external_analysis_dir=external_analysis_dir,
                loop_run_id=current_state.loop_run_id,
                pass_index=current_state.pass_index,
                artifact=pass_artifact,
            )
            
            # Instrument artifact span with `with` block
            with start_artifact_span(
                run_id=current_state.loop_run_id,
                pass_index=current_state.pass_index,
                artifact_path=str(p4c_artifact_path) if p4c_artifact_path else None,
                schema_valid=False,  # Budget exceeded artifact may be incomplete
                missing_fields=0,
                new_evidence_count=0,
            ) as artifact_span_ctx:
                emit_artifact_written_event(
                    artifact_span_ctx,
                    str(p4c_artifact_path) if p4c_artifact_path else "",
                    False
                )
                emit_stop_event(
                    artifact_span_ctx,
                    budget_stop_reason.value if budget_stop_reason else "unknown"
                )
            
            emit_stop_event(
                budget_span_ctx,
                budget_stop_reason.value if budget_stop_reason else "unknown"
            )
            budget_span_ctx.set_ok()
            
            return _build_budget_exceeded_result(
                pass_artifact=pass_artifact,
                resolved_policy=resolved_policy,
                budget_stop_reason=budget_stop_reason,
                case_file=case_file,
            )

        # Budget not exceeded - proceed with planning
        
        # STEP 1: Plan WITHOUT executing checks (planner-only seam)
        # Start plan span with `with` block
        with start_plan_span(
            run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
        ) as plan_span_ctx:
            try:
                planner_result = plan_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                    prior_loop_state=prior_loop_state,
                    now=resolved_now,
                    require_complete_root_cause_before_stop=require_complete_root_cause_before_stop,
                )
                plan_span_ctx.set_ok()
            except Exception as exc:
                # record_exception() already calls set_error() internally
                plan_span_ctx.record_exception(exc)
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
        
        # Start gate span with `with` block
        with start_gate_span(
            run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
            proposed=len(proposed_checks),
            accepted=0,
            rejected_mutating=0,
            rejected_sensitive=0,
            rejected_duplicate=0,
            rejected_budget=0,
        ) as gate_span_ctx:
            gate_summary, accepted_fingerprints = gate_checks(
                proposed_checks, resolved_policy, seen_fingerprints
            )

            # STEP 3: Enforce max_checks_per_pass after gating
            rejected_budget_count = 0
            if gate_summary.accepted > resolved_policy.max_checks_per_pass:
                overflow_checks = gate_summary.accepted_checks[resolved_policy.max_checks_per_pass:]
                overflow_fingerprints = gate_summary.accepted_fingerprints[resolved_policy.max_checks_per_pass:]
                rejected_budget_count = len(overflow_checks)
                
                for check, fp in zip(overflow_checks, overflow_fingerprints):
                    check_dict = dict(check)
                    check_dict["rejection_reason"] = "max_checks_per_pass_exceeded"
                    check_dict["rejected_fingerprint"] = fp
                    gate_summary.rejected_checks.append(check_dict)
                    gate_summary.rejected_fingerprints.append(fp)
                
                gate_summary.accepted_checks = gate_summary.accepted_checks[:resolved_policy.max_checks_per_pass]
                gate_summary.accepted_fingerprints = gate_summary.accepted_fingerprints[:resolved_policy.max_checks_per_pass]
                gate_summary.accepted = len(gate_summary.accepted_checks)
            
            # Emit rejection events for each rejected check
            for check in gate_summary.rejected_checks:
                rejection_reason = check.get("rejection_reason", "unknown")
                emit_check_rejected_event(
                    gate_span_ctx,
                    check_id=str(check.get("check_id", "")),
                    rejection_reason=rejection_reason,
                    is_unsafe=(rejection_reason == "mutating_check_rejected"),
                    is_sensitive=(rejection_reason == "sensitive_read_denied"),
                )
        
        # Use gate_summary.accepted_fingerprints for the artifact
        artifact_accepted_fingerprints = list(gate_summary.accepted_fingerprints)
        
        # Update seen_fingerprints
        updated_seen_fingerprints = seen_fingerprints | set(artifact_accepted_fingerprints)
        
        # Create updated runtime state for artifact
        updated_runtime_state = current_state.with_updates(
            seen_check_fingerprints=frozenset(updated_seen_fingerprints),
        )

        # Extract root cause info
        root_cause_summary = ""
        root_cause = loop_update.get("root_cause_candidate", {})
        if isinstance(root_cause, dict):
            root_cause_summary = str(root_cause.get("summary", ""))
        confidence = "unknown"
        if isinstance(root_cause, dict):
            confidence = str(root_cause.get("confidence", "unknown"))

        # STEP 4: Execute ONLY accepted checks (AFTER gating)
        runner_result: dict[str, Any] | None = None
        if gate_summary.accepted > 0 and not budget_exceeded:
            # Start execute span with `with` block
            with start_execute_span(
                run_id=current_state.loop_run_id,
                pass_index=current_state.pass_index,
                checks_count=gate_summary.accepted,
                runner_kind="read_only",
            ) as execute_span_ctx:
                try:
                    runner_result = run_read_only_checks(
                        incident_id=incident_id,
                        run_id=run_id,
                        accepted_checks=gate_summary.accepted_checks,
                        now=resolved_now,
                        fake_handlers=fake_handlers,
                    )
                    emit_checks_executed_event(execute_span_ctx, gate_summary.accepted)
                    execute_span_ctx.set_ok()
                except Exception as exc:
                    # record_exception() already calls set_error() internally
                    execute_span_ctx.record_exception(exc)
                    raise

        # STEP 5: Build the pass artifact
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

        # Instrument artifact span with `with` block
        with start_artifact_span(
            run_id=current_state.loop_run_id,
            pass_index=current_state.pass_index,
            artifact_path=str(p4c_artifact_path) if p4c_artifact_path else None,
            schema_valid=is_valid,
            missing_fields=len(missing),
            new_evidence_count=len(pass_artifact.get("new_evidence_hashes", [])),
        ) as artifact_span_ctx:
            emit_artifact_written_event(
                artifact_span_ctx,
                str(p4c_artifact_path) if p4c_artifact_path else "",
                is_valid
            )
            stop_reason = pass_artifact.get("stop_reason")
            emit_stop_event(artifact_span_ctx, stop_reason if stop_reason else "unknown")
            artifact_span_ctx.set_ok()

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

        # Set budget span to OK
        budget_span_ctx.set_ok()

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

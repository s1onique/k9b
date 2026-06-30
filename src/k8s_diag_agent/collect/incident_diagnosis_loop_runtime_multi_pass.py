"""Multi-pass runtime loop execution with policy enforcement.

This module provides run_policy_enforced_loop() which executes the complete
policy-enforced diagnosis loop across multiple passes.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_read_only_check_runner import ReadOnlyCheckHandler

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)

from .incident_diagnosis_loop_otel import emit_loop_span
from .incident_diagnosis_loop_runtime_helpers import build_loop_stop_artifact
from .incident_diagnosis_loop_runtime_single_pass import run_policy_enforced_loop_pass
from .runtime_budgets import enforce_budgets
from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass

__all__ = [
    "run_policy_enforced_loop",
]


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
    from .incident_diagnosis_loop_runtime_utils import is_safe_run_id

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
        
        # CRITICAL: Merge accepted fingerprints from this pass into seen_fingerprints
        # for duplicate detection in subsequent passes
        accepted_fingerprints = pass_artifact.get("all_seen_fingerprints", [])
        if accepted_fingerprints:
            seen_fingerprints = seen_fingerprints | set(accepted_fingerprints)
        
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

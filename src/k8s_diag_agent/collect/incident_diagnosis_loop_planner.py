"""Main loop planning function for incident diagnosis.

This module contains the main entry point for diagnosis loop planning.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .incident_diagnosis_loop_models import (
    DEFAULT_MAX_PASSES,
    LoopDecision,
    LoopState,
    StopReason,
)
from .incident_diagnosis_loop_proposals import extract_next_check_proposals
from .incident_diagnosis_loop_state import (
    add_pass_to_state,
    create_initial_loop_state,
    increment_pass,
    record_planned_checks,
    stop_loop,
)
from .incident_diagnosis_loop_stops import (
    build_root_cause_candidate,
    check_budget_exhausted,
    check_low_confidence_no_progress,
    check_no_safe_checks,
    check_root_cause_found,
    check_safety_blocked,
    check_stop_no_checks_proposed_acceptable,
)
from .incident_next_check_policy import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_TOTAL_CHECKS,
    DISALLOWED_ACTIONS,
    NextCheckPolicy,
)


def _build_loop_update(
    loop_state: LoopState,
    decision: LoopDecision,
    stop_reason: StopReason | None,
    accepted_checks: list[dict[str, Any]],
    rejected_checks: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
) -> dict[str, object]:
    """Build the loop update result dict."""
    from .incident_diagnosis_loop_models import LOOP_SCHEMA_VERSION

    # Safety metadata
    safety_metadata = {
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        "no_execution": True,
        "no_kubernetes_client": True,
        "no_llm_execution": True,
        "checks_validated_by_policy": True,
    }

    # Rejection reasons summary
    rejection_reasons: list[str] = []
    for r in rejected_checks:
        if r.get("rejection_reason"):
            rejection_reasons.append(f"{r['check_id']}: {r['rejection_reason']}")

    return {
        "schema_version": LOOP_SCHEMA_VERSION,
        "incident_id": loop_state.incident_id,
        "loop_state": loop_state.to_dict(),
        "decision": decision.value,
        "stop_reason": stop_reason.value if stop_reason else None,
        "accepted_checks": accepted_checks,
        "rejected_checks": rejected_checks,
        "proposed_next_checks": proposals,  # All proposals for runtime gating
        "rejection_summary": rejection_reasons,
        "passes_completed": len(loop_state.passes),
        "current_pass": loop_state.pass_budget["current_pass"],
        "total_checks_planned": loop_state.total_checks_planned,
        "safety_metadata": safety_metadata,
        "note": "This result does not execute checks. Future ACT will wire execution.",
    }


def plan_next_diagnosis_pass(
    *,
    incident_id: str,
    case_file: Mapping[str, object],
    diagnosis_report: Mapping[str, object],
    prior_loop_state: Mapping[str, object] | None = None,
    now: datetime | None = None,
    max_passes: int = DEFAULT_MAX_PASSES,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
    max_total_checks: int = DEFAULT_MAX_TOTAL_CHECKS,
    require_complete_root_cause_before_stop: bool = False,
) -> dict[str, object]:
    """Plan the next diagnosis pass or make a stop decision.

    This is the main entry point for the diagnosis loop. It:
    1. Builds or updates loop state
    2. Extracts next-check proposals from diagnosis
    3. Validates proposals against policy
    4. Checks stop conditions
    5. Returns loop state update with decision

    Args:
        incident_id: The incident to diagnose
        case_file: Case-file packet from build_incident_case_file()
        diagnosis_report: Diagnosis report from build_incident_diagnosis()
        prior_loop_state: Prior loop state if continuing (from prior call)
        now: Optional datetime for deterministic timestamps
        max_passes: Maximum diagnosis passes (default 3)
        max_checks_per_pass: Maximum checks per pass (default 5)
        max_total_checks: Maximum total checks (default 15)
        require_complete_root_cause_before_stop: If True (P4c lab-strict mode),
            stop_no_checks_proposed requires complete scheduling root cause.
            If False (default), no proposals = stop immediately.

    Returns:
        Loop-state update dict with:
        {
            "schema_version": "1.0",
            "incident_id": "...",
            "loop_state": {...},  # Full loop state
            "decision": "...",  # LoopDecision value
            "stop_reason": "...",  # StopReason if stopped
            "accepted_checks": [...],  # Validated read-only checks
            "rejected_checks": [...],  # Rejected with reasons
            "safety_metadata": {...}
        }

    Safety guarantees:
    - read_only: True
    - allowed_actions: []
    - disallowed_actions includes all mutation/remediation verbs
    - No execution occurs
    - No Kubernetes client is called
    - No LLM text is converted to executable commands
    """
    from .incident_diagnosis_loop_models import DiagnosisPass

    timestamp = now if now is not None else datetime.now(UTC)

    # Build or restore loop state
    if prior_loop_state is not None:
        loop_state = LoopState.from_dict(dict(prior_loop_state))
    else:
        loop_state = create_initial_loop_state(
            incident_id=incident_id,
            now=timestamp,
            max_passes=max_passes,
            max_checks_per_pass=max_checks_per_pass,
            max_total_checks=max_total_checks,
        )

    # Extract case file summary for this pass
    incident = case_file.get("incident", {})
    case_file_summary = {
        "incident_id": str(incident.get("incident_id", incident_id)),
        "namespace": str(incident.get("namespace", "")),
        "object_kind": str(incident.get("object_kind", "")),
        "object_name": str(incident.get("object_name", "")),
        "severity": str(incident.get("severity", "")),
    }

    # Extract diagnosis from report
    diagnosis_data = diagnosis_report.get("diagnosis", {})
    if not isinstance(diagnosis_data, dict):
        diagnosis_data = {}

    # Build root-cause candidate from diagnosis
    root_cause_candidate = build_root_cause_candidate(diagnosis_report)

    # Extract next-check proposals
    proposals = extract_next_check_proposals(
        diagnosis_report,
        max_proposals=max_checks_per_pass * 2,  # Extract more than max to test bounds
    )

    # Determine current pass index
    current_pass_index = loop_state.pass_budget["current_pass"]
    prior_pass_count = len(loop_state.passes)

    # Use restored state budget if resuming, else parameter
    state_max_total_checks = int(loop_state.pass_budget.get("max_total_checks", max_total_checks))

    # Check total checks budget BEFORE policy validation
    remaining_total_budget = state_max_total_checks - loop_state.total_checks_planned
    if remaining_total_budget <= 0:
        # Total budget exhausted
        new_state = stop_loop(loop_state, StopReason.BUDGET_EXHAUSTED, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision={},
            stop_reason=StopReason.BUDGET_EXHAUSTED.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_BUDGET_EXHAUSTED,
            stop_reason=StopReason.BUDGET_EXHAUSTED,
            accepted_checks=[],
            rejected_checks=[],
            proposals=proposals,
        )

    # Compute effective per-pass limit considering total budget
    effective_max_checks_this_pass = min(max_checks_per_pass, remaining_total_budget)

    # Validate proposals against policy
    policy = NextCheckPolicy(max_checks_per_pass=effective_max_checks_this_pass)
    accepted_checks, validation_results = policy.validate(proposals)

    # Build policy decision for this pass
    policy_decision = {
        "proposals_received": len(proposals),
        "checks_accepted": len(accepted_checks),
        "checks_rejected": len([r for r in validation_results if not r.accepted]),
        "max_checks_per_pass": max_checks_per_pass,
        "validation_results": [r.to_dict() for r in validation_results],
    }

    # Check stop conditions in priority order
    # 1. Safety blocked
    if check_safety_blocked(proposals, validation_results):
        new_state = stop_loop(loop_state, StopReason.SAFETY_BLOCKED, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=StopReason.SAFETY_BLOCKED.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_SAFETY_BLOCKED,
            stop_reason=StopReason.SAFETY_BLOCKED,
            accepted_checks=[],
            rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
            proposals=proposals,
        )

    # 2. Root cause found
    if check_root_cause_found(root_cause_candidate):
        new_state = stop_loop(loop_state, StopReason.ROOT_CAUSE_FOUND, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=StopReason.ROOT_CAUSE_FOUND.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_ROOT_CAUSE_FOUND,
            stop_reason=StopReason.ROOT_CAUSE_FOUND,
            accepted_checks=accepted_checks,
            rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
            proposals=proposals,
        )

    # 3. Budget exhausted (pass budget)
    if check_budget_exhausted(loop_state):
        new_state = stop_loop(loop_state, StopReason.BUDGET_EXHAUSTED, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=StopReason.BUDGET_EXHAUSTED.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_BUDGET_EXHAUSTED,
            stop_reason=StopReason.BUDGET_EXHAUSTED,
            accepted_checks=accepted_checks,
            rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
            proposals=proposals,
        )

    # 4. No checks proposed - mode-gated stop decision
    #
    # Unit/product default (require_complete_root_cause_before_stop=False):
    #   - no proposals => stop_no_checks_proposed
    #
    # P4c lab-strict mode (require_complete_root_cause_before_stop=True):
    #   - no proposals + complete scheduling root cause => stop_no_checks_proposed
    #   - no proposals + incomplete scheduling root cause => continue loop
    if len(proposals) == 0:
        if require_complete_root_cause_before_stop:
            # P4c lab-strict mode: check if root cause is complete
            root_cause_summary = ""
            if diagnosis_data:
                likely_causes = diagnosis_data.get("likely_causes", [])
                if likely_causes:
                    root_cause_summary = "; ".join(str(c) for c in likely_causes[:3])

            if check_stop_no_checks_proposed_acceptable(
                proposals,
                root_cause_candidate,
                root_cause_summary,
                diagnosis_data=diagnosis_data,
                require_operator_action=True,
            ):
                # Complete root cause - accept stop
                new_state = stop_loop(loop_state, StopReason.NO_CHECKS_PROPOSED, now=timestamp)
                pass_result = DiagnosisPass(
                    pass_index=current_pass_index,
                    case_file_summary=case_file_summary,
                    diagnosis=diagnosis_data,
                    root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
                    proposed_next_checks=(),
                    policy_decision=policy_decision,
                    stop_reason=StopReason.NO_CHECKS_PROPOSED.value,
                )
                new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

                return _build_loop_update(
                    loop_state=new_state,
                    decision=LoopDecision.STOP_NO_CHECKS_PROPOSED,
                    stop_reason=StopReason.NO_CHECKS_PROPOSED,
                    accepted_checks=[],
                    rejected_checks=[],
                    proposals=[],
                )
            # Incomplete root cause - fall through to continue loop
        else:
            # Default mode: no proposals = stop immediately
            new_state = stop_loop(loop_state, StopReason.NO_CHECKS_PROPOSED, now=timestamp)
            pass_result = DiagnosisPass(
                pass_index=current_pass_index,
                case_file_summary=case_file_summary,
                diagnosis=diagnosis_data,
                root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
                proposed_next_checks=(),
                policy_decision=policy_decision,
                stop_reason=StopReason.NO_CHECKS_PROPOSED.value,
            )
            new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

            return _build_loop_update(
                loop_state=new_state,
                decision=LoopDecision.STOP_NO_CHECKS_PROPOSED,
                stop_reason=StopReason.NO_CHECKS_PROPOSED,
                accepted_checks=[],
                rejected_checks=[],
                proposals=[],
            )

    # 5. No safe checks (all rejected)
    if check_no_safe_checks(proposals, validation_results):
        new_state = stop_loop(loop_state, StopReason.NO_SAFE_CHECKS, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=StopReason.NO_SAFE_CHECKS.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_NO_SAFE_CHECKS,
            stop_reason=StopReason.NO_SAFE_CHECKS,
            accepted_checks=[],
            rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
            proposals=proposals,
        )

    # 6. Low confidence no progress
    if check_low_confidence_no_progress(root_cause_candidate, prior_pass_count):
        new_state = stop_loop(loop_state, StopReason.LOW_CONFIDENCE_NO_PROGRESS, now=timestamp)
        pass_result = DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=StopReason.LOW_CONFIDENCE_NO_PROGRESS.value,
        )
        new_state = add_pass_to_state(new_state, pass_result, now=timestamp)

        return _build_loop_update(
            loop_state=new_state,
            decision=LoopDecision.STOP_LOW_CONFIDENCE_NO_PROGRESS,
            stop_reason=StopReason.LOW_CONFIDENCE_NO_PROGRESS,
            accepted_checks=accepted_checks,
            rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
            proposals=proposals,
        )

    # Continue: run accepted checks
    new_state = add_pass_to_state(
        loop_state,
        DiagnosisPass(
            pass_index=current_pass_index,
            case_file_summary=case_file_summary,
            diagnosis=diagnosis_data,
            root_cause_candidate=root_cause_candidate.to_dict() if root_cause_candidate else None,
            proposed_next_checks=tuple(proposals),
            policy_decision=policy_decision,
            stop_reason=None,
        ),
        now=timestamp,
    )

    # Record planned checks in state
    new_state = record_planned_checks(new_state, len(accepted_checks), now=timestamp)

    # Increment pass for next iteration
    new_state = increment_pass(new_state, timestamp)

    return _build_loop_update(
        loop_state=new_state,
        decision=LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS,
        stop_reason=None,
        accepted_checks=accepted_checks,
        rejected_checks=[r.to_dict() for r in validation_results if not r.accepted],
        proposals=proposals,
    )


__all__ = [
    "plan_next_diagnosis_pass",
]

"""Runtime helpers for budget-exceeded and stop artifact creation.

This module provides helper functions for handling budget exhaustion scenarios
and building stop artifacts.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_models import LoopDecision
from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
    validate_pass_artifact_schema,
)

from .runtime_artifacts import (
    RUNTIME_SCHEMA_VERSION,
    build_policy_enforced_pass_artifact,
)
from .runtime_gating import GateSummary
from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass


def build_budget_exceeded_stop_artifact(
    *,
    loop_run_id: str,
    incident_id: str,
    pass_index: int,
    case_file: Mapping[str, object],
    policy: DiagnosisLoopPolicy,
    budget_stop_reason: LoopStopReason | None,
    now: datetime,
    fake_handlers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal pass artifact for budget exhaustion scenario.

    Args:
        loop_run_id: Unique identifier for this loop run
        incident_id: The incident being diagnosed
        pass_index: Current pass index
        case_file: The case file mapping
        policy: The policy being enforced
        budget_stop_reason: Reason for budget exhaustion
        now: Current timestamp
        fake_handlers: Optional fake handlers for testing

    Returns:
        A stop artifact dict with PASS_ARTIFACT_FIELDS
    """
    decision = LoopDecision.STOP_BUDGET_EXHAUSTED.value

    # Build minimal gate summary for budget stop
    gate_summary = GateSummary(
        proposed=0,
        accepted=0,
        rejected_mutating=0,
        rejected_sensitive=0,
        rejected_duplicate=0,
        accepted_checks=[],
        rejected_checks=[],
        accepted_fingerprints=[],
        rejected_fingerprints=[],
    )

    # Build pass artifact with empty results
    pass_artifact = build_policy_enforced_pass_artifact(
        loop_run_id=loop_run_id,
        incident_id=incident_id,
        pass_index=pass_index,
        case_file=case_file,
        policy=policy,
        gate_summary=gate_summary,
        accepted_fingerprints=[],
        runtime_state=LoopRuntimeState(
            loop_run_id=loop_run_id,
            incident_id=incident_id,
            pass_index=pass_index,
            started_at=now.isoformat(),
        ),
        decision=decision,
        root_cause_summary="",
        confidence="unknown",
        runner_result=None,
        now=now,
        budget_exceeded=True,
        budget_stop_reason=budget_stop_reason,
        fake_handlers=fake_handlers,
    )

    # Validate pass artifact schema
    is_valid, missing = validate_pass_artifact_schema(pass_artifact)
    if not is_valid:
        pass_artifact["_schema_error"] = f"Missing required fields: {missing}"

    return pass_artifact


def _build_budget_exceeded_result(
    *,
    pass_artifact: dict[str, Any],
    resolved_policy: DiagnosisLoopPolicy,
    budget_stop_reason: LoopStopReason | None,
    case_file: Mapping[str, object],
) -> dict[str, object]:
    """Build the result dict for budget exceeded scenario.

    Args:
        pass_artifact: The built stop artifact
        resolved_policy: The policy that was enforced
        budget_stop_reason: Reason for budget exhaustion
        case_file: The case file mapping

    Returns:
        Result dict for the pass
    """
    from .incident_diagnosis_loop_runtime_utils import compute_case_file_hash

    case_file_hash = compute_case_file_hash(case_file)
    return {
        "policy_enforced": True,
        "policy": resolved_policy.to_dict(),
        "gate_summary": {
            "proposed": 0,
            "accepted": 0,
            "rejected_mutating": 0,
            "rejected_sensitive": 0,
            "rejected_duplicate": 0,
            "rejected_checks": [],
        },
        "pass_artifact": pass_artifact,
        "p4c_artifact_path": None,
        "case_file_hash": case_file_hash,
        "budget_exceeded": True,
        "budget_stop_reason": budget_stop_reason.value if budget_stop_reason else None,
        "decision": LoopDecision.STOP_BUDGET_EXHAUSTED.value,
        "planner_called": False,
    }


def build_loop_stop_artifact(
    *,
    loop_run_id: str,
    incident_id: str,
    pass_index: int,
    case_file: Mapping[str, object],
    budget_stop_reason: LoopStopReason | None,
    now: datetime,
) -> dict[str, Any]:
    """Build a stop artifact for loop budget exhaustion.

    This creates the minimal artifact required when the loop stops
    due to budget limits being reached.

    Args:
        loop_run_id: Unique identifier for this loop run
        incident_id: The incident being diagnosed
        pass_index: Current pass index
        case_file: The case file mapping
        budget_stop_reason: Reason for budget exhaustion
        now: Current timestamp

    Returns:
        A stop artifact dict with PASS_ARTIFACT_FIELDS
    """
    from .incident_diagnosis_loop_runtime_utils import compute_case_file_hash

    case_file_hash = compute_case_file_hash(case_file)

    stop_artifact = {
        # PASS_ARTIFACT_FIELDS
        "loop_run_id": loop_run_id,
        "incident_id": incident_id,
        "pass_index": pass_index,
        "case_file_hash": case_file_hash,
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
        "generated_at": now.isoformat(),
    }

    return stop_artifact


__all__ = [
    "build_budget_exceeded_stop_artifact",
    "build_loop_stop_artifact",
]

"""Deterministic one-pass read-only diagnosis loop orchestrator.

This module provides a deterministic one-pass orchestrator that performs exactly
one safe read-only diagnosis loop pass:

    input case_file + diagnosis_report + prior_loop_state
      -> plan next diagnosis pass
      -> if decision is run_allowed_read_only_checks:
           run fake read-only checks
           persist bounded read-only check result artifact
           rebuild case file with that artifact linked
      -> return a bounded JSON-serializable orchestration result

Design constraints:
- Pure functions only
- No store mutation (except what build_incident_case_file() already reads)
- No LLM calls
- No Kubernetes calls
- No subprocess/shell/kubectl
- No execution, promotion, or remediation
- Deterministic ordering with bounded counts
- Explicit safety metadata

Safety constraints:
- Does not import kubernetes
- Does not import subprocess
- Does not contain kubectl execution behavior
- Does not contain apply/delete/patch/scale/restart/rollout actions
- Preserves read_only: True
- Preserves allowed_actions: []
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .incident_case_file import build_incident_case_file
from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_pass_artifacts import (
    write_diagnosis_loop_pass_artifact,
)
from .incident_diagnosis_loop_planner import plan_next_diagnosis_pass
from .incident_read_only_check_artifacts import (
    is_safe_run_id,
    write_read_only_check_result_artifact,
)
from .incident_read_only_check_runner import run_checks_from_loop_decision

if TYPE_CHECKING:
    from .incident_read_only_check_runner import ReadOnlyCheckHandler

__all__ = [
    "run_one_read_only_diagnosis_loop_pass",
    "plan_one_read_only_diagnosis_loop_pass",
    "ORCHESTRATOR_SCHEMA_VERSION",
]


# =============================================================================
# Constants
# =============================================================================

# Schema version for orchestrator output
ORCHESTRATOR_SCHEMA_VERSION = "1.0"


# =============================================================================
# Safety Validation
# =============================================================================


def _validate_run_id(run_id: str) -> None:
    """Validate run_id for safety.

    Args:
        run_id: The run_id to validate

    Raises:
        ValueError: If run_id is unsafe
    """
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")


# =============================================================================
# Stop Decision Detection
# =============================================================================


def _is_stop_decision(decision: str) -> bool:
    """Check if a loop decision is a stop decision.

    Args:
        decision: The decision string to check

    Returns:
        True if the decision is a stop decision
    """
    stop_decisions = {
        LoopDecision.STOP_ROOT_CAUSE_FOUND.value,
        LoopDecision.STOP_NO_SAFE_CHECKS.value,
        LoopDecision.STOP_BUDGET_EXHAUSTED.value,
        LoopDecision.STOP_LOW_CONFIDENCE_NO_PROGRESS.value,
        LoopDecision.STOP_SAFETY_BLOCKED.value,
        LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
    }
    return decision in stop_decisions


# =============================================================================
# Public API
# =============================================================================


def run_one_read_only_diagnosis_loop_pass(
    *,
    incident_id: str,
    external_analysis_dir: Path,
    case_file: Mapping[str, object],
    diagnosis_report: Mapping[str, object],
    run_id: str,
    prior_loop_state: Mapping[str, object] | None = None,
    now: datetime | None = None,
    fake_handlers: Mapping[str, ReadOnlyCheckHandler] | None = None,
    require_complete_root_cause_before_stop: bool = False,
) -> dict[str, object]:
    """Run one deterministic read-only diagnosis loop pass.

    This function orchestrates a single pass of the diagnosis loop:

    1. Validate run_id for safety
    2. Plan next diagnosis pass
    3. If decision is run_allowed_read_only_checks:
       a. Run fake read-only checks
       b. Persist bounded check result artifact
       c. Rebuild case file with artifact linked
    4. Return bounded orchestration result

    Args:
        incident_id: The incident ID being diagnosed
        external_analysis_dir: Path to external-analysis directory for artifacts
        case_file: Current case-file packet from build_incident_case_file()
        diagnosis_report: Diagnosis report from build_incident_diagnosis()
        run_id: Unique identifier for this orchestrator run (must be safe)
        prior_loop_state: Prior loop state from previous pass (if continuing)
        now: Optional datetime for deterministic timestamps
        fake_handlers: Optional mapping of check_id -> ReadOnlyCheckHandler
            for test injection
        require_complete_root_cause_before_stop: If True (P4c lab-strict mode),
            stop_no_checks_proposed requires complete scheduling root cause.

    Returns:
        Bounded JSON-serializable orchestration result:

        {
            "schema_version": "1.0",
            "incident_id": "...",
            "run_id": "...",
            "read_only": True,
            "allowed_actions": [],
            "decision": "run_allowed_read_only_checks" | stop_decision,
            "loop_update": {...},  # Full loop update from planner
            "runner_result": {...} | None,  # Runner result if checks ran
            "artifact": {...} | None,  # Artifact metadata if written
            "rebuilt_case_file": {...} | None,  # Rebuilt case file if checks ran
            "case_file_linked_artifact": True | False,
            "safety_metadata": {
                "read_only": True,
                "no_kubernetes_client": True,
                "no_shell": True,
                "no_subprocess": True,
                "no_kubectl": True,
                "no_mutation": True,
                "fake_runner": True,
                "one_pass_only": True,
            },
        }

    Raises:
        ValueError: If run_id is unsafe

    Safety guarantees:
    - Does not import kubernetes
    - Does not import subprocess
    - Does not call kubectl
    - Does not mutate cluster
    - Preserves read_only: True
    - Preserves allowed_actions: []
    """
    # Validate run_id for safety
    _validate_run_id(run_id)

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Step 1: Plan next diagnosis pass
    loop_update = plan_next_diagnosis_pass(
        incident_id=incident_id,
        case_file=dict(case_file),
        diagnosis_report=dict(diagnosis_report),
        prior_loop_state=dict(prior_loop_state) if prior_loop_state is not None else None,
        now=resolved_now,
        require_complete_root_cause_before_stop=require_complete_root_cause_before_stop,
    )

    # Extract decision
    decision = loop_update.get("decision", "")

    # Safety metadata for all paths
    safety_metadata = {
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": [
            "execute",
            "promote",
            "apply",
            "remediate",
            "delete",
            "mutate_cluster",
            "mutate",
            "scale",
            "restart",
            "rollout",
        ],
        "no_kubernetes_client": True,
        "no_shell": True,
        "no_subprocess": True,
        "no_kubectl": True,
        "no_mutation": True,
        "fake_runner": True,
        "one_pass_only": True,
        "checks_validated_by_policy": True,
    }

    # Initialize result fields
    runner_result: dict[str, object] | None = None
    artifact: dict[str, object] | None = None
    rebuilt_case_file: dict[str, object] | None = None
    case_file_linked_artifact = False

    # Step 2: Check decision and execute if allowed
    if decision == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
        # Step 3: Run fake read-only checks
        runner_result = run_checks_from_loop_decision(
            incident_id=incident_id,
            run_id=run_id,
            loop_update=loop_update,
            now=resolved_now,
            fake_handlers=fake_handlers,
        )

        # Step 4: Persist artifact if runner returned results
        checks_run = runner_result.get("checks_run", 0)
        if runner_result and isinstance(checks_run, int) and checks_run > 0:
            try:
                artifact = write_read_only_check_result_artifact(
                    external_analysis_dir=external_analysis_dir,
                    run_id=run_id,
                    incident_id=incident_id,
                    runner_result=runner_result,
                    now=resolved_now,
                )
            except (OSError, ValueError) as e:
                # Artifact write failed - continue without artifact
                artifact = {
                    "error": str(e),
                    "written": False,
                }

        # Step 5: Rebuild case file with explicit run_id for artifact linkage
        # This ensures the artifact written in this pass is included
        rebuilt_case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            now=resolved_now,
            read_only_check_result_run_ids=[run_id],
        )
        check_results = rebuilt_case_file.get("read_only_check_results") if rebuilt_case_file else None
        case_file_linked_artifact = (
            rebuilt_case_file is not None
            and check_results is not None
            and isinstance(check_results, list)
            and len(check_results) > 0
        )

    # Build intermediate result for loop-pass artifact writing
    disallowed = safety_metadata["disallowed_actions"]
    intermediate_result: dict[str, object] = {
        "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
        "incident_id": incident_id,
        "run_id": run_id,
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(disallowed) if isinstance(disallowed, list) else [],
        "decision": decision,
        "loop_update": loop_update,
        "runner_result": runner_result,
        "artifact": artifact,
        "rebuilt_case_file": None,  # Don't include in loop-pass artifact
        "case_file_linked_artifact": case_file_linked_artifact,
        "safety_metadata": safety_metadata,
    }

    # Step 6: Write loop-pass artifact for all valid orchestrator passes
    # This includes both run decisions and stop decisions
    loop_pass_artifact: dict[str, object] | None = None
    try:
        loop_pass_artifact = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=external_analysis_dir,
            run_id=run_id,
            incident_id=incident_id,
            orchestrator_result=intermediate_result,
            now=resolved_now,
        )
    except (OSError, ValueError) as e:
        # Loop-pass artifact write failed - continue without it
        loop_pass_artifact = {
            "error": str(e),
            "written": False,
        }

    # Build final orchestration result
    result: dict[str, object] = {
        "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
        "incident_id": incident_id,
        "run_id": run_id,
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(disallowed) if isinstance(disallowed, list) else [],
        "decision": decision,
        "loop_update": loop_update,
        "runner_result": runner_result,
        "artifact": artifact,
        "rebuilt_case_file": rebuilt_case_file,
        "case_file_linked_artifact": case_file_linked_artifact,
        "loop_pass_artifact": loop_pass_artifact,
        "safety_metadata": safety_metadata,
    }

    return result


def plan_one_read_only_diagnosis_loop_pass(
    *,
    incident_id: str,
    case_file: Mapping[str, object],
    diagnosis_report: Mapping[str, object],
    run_id: str,
    prior_loop_state: Mapping[str, object] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Plan one diagnosis loop pass WITHOUT executing checks.

    This is the PLANNER-ONLY seam for pre-execution policy enforcement.
    It returns the loop_update with proposed_next_checks WITHOUT running
    any check handlers or the fake runner.

    Use this when you need to:
    - Gate checks BEFORE execution
    - Enforce budgets before any execution
    - Ensure rejected checks never reach handlers

    The runtime MUST call this instead of run_one_read_only_diagnosis_loop_pass
    when pre-execution enforcement is required.

    Args:
        incident_id: The incident ID being diagnosed
        case_file: Current case-file packet from build_incident_case_file()
        diagnosis_report: Diagnosis report from build_incident_diagnosis()
        run_id: Unique identifier for this orchestrator run (must be safe)
        prior_loop_state: Prior loop state from previous pass (if continuing)
        now: Optional datetime for deterministic timestamps

    Returns:
        Planner-only result dict:
        {
            "schema_version": "1.0",
            "incident_id": "...",
            "run_id": "...",
            "read_only": True,
            "allowed_actions": [],
            "decision": "run_allowed_read_only_checks" | stop_decision,
            "loop_update": {
                "decision": "...",
                "stop_reason": "...",
                "proposed_next_checks": [...],  # For gating
                "accepted_checks": [...],  # Planner-validated (NOT runtime-gated)
                "rejected_checks": [...],
                "root_cause_candidate": {...},
            },
            # NO runner_result - checks are NOT executed
            # NO artifact - no checks ran
            # NO rebuilt_case_file - no checks ran
            "safety_metadata": {
                "read_only": True,
                "planner_only": True,  # Explicit: no execution
                "no_kubernetes_client": True,
                "no_shell": True,
                "no_subprocess": True,
                "no_kubectl": True,
                "no_mutation": True,
                "no_execution": True,
            },
        }

    Raises:
        ValueError: If run_id is unsafe

    Safety guarantees:
    - Does not import kubernetes
    - Does not import subprocess
    - Does not call kubectl
    - Does not mutate cluster
    - Does NOT execute any check handlers
    - Does NOT produce runner results
    - Preserves read_only: True
    - Preserves allowed_actions: []
    """
    # Validate run_id for safety
    _validate_run_id(run_id)

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Step 1: Plan next diagnosis pass (NO execution)
    loop_update = plan_next_diagnosis_pass(
        incident_id=incident_id,
        case_file=dict(case_file),
        diagnosis_report=dict(diagnosis_report),
        prior_loop_state=dict(prior_loop_state) if prior_loop_state is not None else None,
        now=resolved_now,
    )

    # Extract decision
    decision = loop_update.get("decision", "")

    # Safety metadata - explicitly planner-only
    safety_metadata = {
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": [
            "execute",
            "promote",
            "apply",
            "remediate",
            "delete",
            "mutate_cluster",
            "mutate",
            "scale",
            "restart",
            "rollout",
        ],
        "no_kubernetes_client": True,
        "no_shell": True,
        "no_subprocess": True,
        "no_kubectl": True,
        "no_mutation": True,
        "planner_only": True,  # Explicit: no execution occurred
        "no_execution": True,
        "no_runner_result": True,
    }

    # Build planner-only result (NO execution)
    # Extract disallowed_actions as a properly-typed list using cast
    _disallowed_actions: list[str] = cast(list[str], safety_metadata["disallowed_actions"])
    result: dict[str, object] = {
        "schema_version": ORCHESTRATOR_SCHEMA_VERSION,
        "incident_id": incident_id,
        "run_id": run_id,
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": _disallowed_actions,
        "decision": decision,
        "loop_update": loop_update,
        # NO runner_result - checks are NOT executed
        # NO artifact - no checks ran
        # NO rebuilt_case_file - no checks ran
        # NO loop_pass_artifact - written only after gating + execution
        "safety_metadata": safety_metadata,
    }

    return result

"""Runtime envelope that wraps orchestrator with DiagnosisLoopPolicy enforcement.

This module provides the outer controller layer that:
- Owns the DiagnosisLoopPolicy hard budget limits
- Gates checks before execution (mutating, sensitive, duplicates)
- Emits pass artifacts with exact PASS_ARTIFACT_FIELDS
- Maps loop decisions to typed LoopStopReason

Design constraints:
- Wraps run_one_read_only_diagnosis_loop_pass()
- Does NOT replace NextCheckPolicy (planner semantic layer)
- Emits artifacts matching PASS_ARTIFACT_FIELDS
- Deterministic with injected timestamps
- Explicit OTel span boundaries
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_mutating_check as _is_mutating_check,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_sensitive_read_check as _is_sensitive_read_check,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
    validate_pass_artifact_schema,
)

from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)
from .incident_diagnosis_loop_otel import (
    emit_check_gate_span,
    emit_loop_span,
    emit_pass_span,
)
from .incident_diagnosis_loop_runtime_utils import (
    compute_case_file_hash,
    compute_fingerprint,
    extract_evidence_hashes,
    is_safe_run_id,
)
from .incident_read_only_check_runner import ReadOnlyCheckHandler

if TYPE_CHECKING:
    pass

__all__ = [
    "run_policy_enforced_loop_pass",
    "gate_checks",
    "build_policy_enforced_pass_artifact",
    "GateSummary",
    "RUNTIME_SCHEMA_VERSION",
]

# =============================================================================
# Constants
# =============================================================================

RUNTIME_SCHEMA_VERSION = "1.0"


# =============================================================================
# Check Gating
# =============================================================================


@dataclass
class GateSummary:
    """Summary of gating decisions for a pass."""

    proposed: int
    accepted: int
    rejected_mutating: int
    rejected_sensitive: int
    rejected_duplicate: int
    accepted_checks: list[dict[str, Any]]
    rejected_checks: list[dict[str, Any]]


def gate_checks(
    proposed_checks: Sequence[Mapping[str, object]],
    policy: DiagnosisLoopPolicy,
    seen_fingerprints: set[str],
) -> GateSummary:
    """Gate proposed checks against policy.

    Applies in order:
    1. Mutating check rejection (unless policy allows)
    2. Sensitive read rejection (unless policy allows)
    3. Duplicate fingerprint rejection
    """
    accepted_checks: list[dict[str, Any]] = []
    rejected_checks: list[dict[str, Any]] = []
    rejected_mutating = 0
    rejected_sensitive = 0
    rejected_duplicate = 0

    for check in proposed_checks:
        check_id = str(check.get("check_id", "unknown"))
        check_dict = dict(check)

        # Check 1: Mutating?
        is_mutating = _is_mutating_check(check_id) or _is_mutating_check(json.dumps(check))
        if is_mutating:
            if not policy.allow_mutating_checks:
                rejected_checks.append({**check_dict, "rejection_reason": "mutating_check_rejected", "is_unsafe": True})
                rejected_mutating += 1
                continue

        # Check 2: Sensitive read?
        is_sensitive = _is_sensitive_read_check(check_id) or _is_sensitive_read_check(json.dumps(check))
        if is_sensitive:
            if not policy.allow_sensitive_reads:
                rejected_checks.append({**check_dict, "rejection_reason": "sensitive_read_denied", "is_sensitive": True})
                rejected_sensitive += 1
                continue

        # Check 3: Duplicate fingerprint?
        fingerprint = compute_fingerprint(check)
        if fingerprint in seen_fingerprints:
            rejected_checks.append({**check_dict, "rejection_reason": "duplicate_check_fingerprint", "duplicate_fingerprint": fingerprint})
            rejected_duplicate += 1
            continue

        accepted_checks.append(check_dict)

    return GateSummary(
        proposed=len(proposed_checks),
        accepted=len(accepted_checks),
        rejected_mutating=rejected_mutating,
        rejected_sensitive=rejected_sensitive,
        rejected_duplicate=rejected_duplicate,
        accepted_checks=accepted_checks,
        rejected_checks=rejected_checks,
    )


def map_decision_to_stop_reason(decision: str, loop_update: Any) -> LoopStopReason | None:
    """Map loop decision to typed LoopStopReason."""
    decision_to_reason: dict[str, LoopStopReason] = {
        LoopDecision.STOP_ROOT_CAUSE_FOUND.value: LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
        LoopDecision.STOP_NO_SAFE_CHECKS.value: LoopStopReason.NO_SAFE_CHECKS_PROPOSED,
        LoopDecision.STOP_BUDGET_EXHAUSTED.value: LoopStopReason.MAX_CHECKS_REACHED,
        LoopDecision.STOP_LOW_CONFIDENCE_NO_PROGRESS.value: LoopStopReason.NO_NEW_EVIDENCE,
        LoopDecision.STOP_SAFETY_BLOCKED.value: LoopStopReason.CHECK_RUNNER_FAILED,
        LoopDecision.STOP_NO_CHECKS_PROPOSED.value: LoopStopReason.NO_SAFE_CHECKS_PROPOSED,
    }
    return decision_to_reason.get(decision)


# =============================================================================
# Pass Artifact Construction
# =============================================================================


def build_policy_enforced_pass_artifact(
    *,
    orchestrator_result: Mapping[str, object],
    loop_run_id: str,
    incident_id: str,
    case_file: Mapping[str, object],
    policy: DiagnosisLoopPolicy,
    gate_summary: GateSummary,
    seen_fingerprints: set[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a pass artifact with exact PASS_ARTIFACT_FIELDS."""
    resolved_now = now if now is not None else datetime.now(UTC)

    loop_update = orchestrator_result.get("loop_update", {})
    decision = str(orchestrator_result.get("decision", ""))
    runner_result = orchestrator_result.get("runner_result")

    # Extract root cause summary from loop update
    root_cause_summary = ""
    root_cause = loop_update.get("root_cause_candidate", {})
    if isinstance(root_cause, dict):
        root_cause_summary = str(root_cause.get("summary", ""))

    # Extract confidence
    confidence = "unknown"
    if isinstance(root_cause, dict):
        confidence = str(root_cause.get("confidence", "unknown"))

    # Determine stop reason
    stop_reason: str | None = None
    typed_reason = map_decision_to_stop_reason(decision, loop_update)
    if typed_reason:
        stop_reason = typed_reason.value
    elif decision.startswith("stop_"):
        stop_reason = decision.replace("stop_", "").replace("_", " ")

    # Determine if loop should continue
    should_continue = decision == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value

    # Extract proposed checks from loop update
    proposed_checks = loop_update.get("proposed_next_checks", [])
    if isinstance(proposed_checks, list):
        proposed_check_ids = [str(c.get("check_id", "")) for c in proposed_checks if isinstance(c, dict)]
    else:
        proposed_check_ids = []

    # Build the complete artifact with all PASS_ARTIFACT_FIELDS
    artifact: dict[str, Any] = {
        # PASS_ARTIFACT_FIELDS
        "loop_run_id": loop_run_id,
        "incident_id": incident_id,
        "pass_index": loop_update.get("pass_index", 1),
        "case_file_hash": compute_case_file_hash(case_file),
        "proposed_checks": proposed_check_ids,
        "accepted_checks": [str(c.get("check_id", "")) for c in gate_summary.accepted_checks],
        "rejected_checks": [str(c.get("check_id", "")) for c in gate_summary.rejected_checks],
        "check_fingerprints": list(seen_fingerprints),
        "new_evidence_hashes": extract_evidence_hashes(runner_result),
        "duplicate_check_count": gate_summary.rejected_duplicate,
        "unsafe_check_count": gate_summary.rejected_mutating,
        "root_cause_summary": root_cause_summary,
        "confidence": confidence,
        "should_continue": should_continue,
        "stop_reason": stop_reason,
        # Additional metadata
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "generated_at": resolved_now.isoformat(),
        "policy_version": policy.schema_version,
        "decision": decision,
        "gate_summary": {
            "proposed": gate_summary.proposed,
            "accepted": gate_summary.accepted,
            "rejected_mutating": gate_summary.rejected_mutating,
            "rejected_sensitive": gate_summary.rejected_sensitive,
            "rejected_duplicate": gate_summary.rejected_duplicate,
        },
        # Safety metadata
        "safety_metadata": {
            "read_only": True,
            "policy_enforced": True,
            "allow_mutating_checks": policy.allow_mutating_checks,
            "allow_sensitive_reads": policy.allow_sensitive_reads,
            "no_kubernetes_client": True,
            "no_shell": True,
            "no_subprocess": True,
            "no_kubectl": True,
            "no_mutation": True,
            "fake_runner": True,
        },
    }

    # Validate schema
    is_valid, missing = validate_pass_artifact_schema(artifact)
    if not is_valid:
        artifact["_schema_validation_warning"] = f"Missing fields: {missing}"

    return artifact


# =============================================================================
# Public API
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
    now: datetime | None = None,
    fake_handlers: Mapping[str, ReadOnlyCheckHandler] | None = None,
) -> dict[str, object]:
    """Run one diagnosis loop pass with policy enforcement.

    This is the main entry point for the policy-enforced runtime:
    1. Validate run_id for safety
    2. Use DiagnosisLoopPolicy (or default)
    3. Run orchestrator pass
    4. Gate checks against policy
    5. Emit pass artifact with PASS_ARTIFACT_FIELDS
    6. Return augmented result
    """
    # Validate run_id
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve policy
    resolved_policy = policy if policy is not None else DiagnosisLoopPolicy.live_lab_default()
    resolved_now = now if now is not None else datetime.now(UTC)

    # Emit loop start span
    emit_loop_span(run_id, incident_id, resolved_policy, "started")

    # Build loop_run_id for pass artifact
    loop_run_id = f"{run_id}-{resolved_now.strftime('%Y%m%d%H%M%S')}"

    # Run the orchestrator
    orchestrator_result = run_one_read_only_diagnosis_loop_pass(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        case_file=case_file,
        diagnosis_report=diagnosis_report,
        run_id=run_id,
        prior_loop_state=prior_loop_state,
        now=resolved_now,
        fake_handlers=fake_handlers,
    )

    # Extract loop update for gating decisions
    loop_update = orchestrator_result.get("loop_update", {})
    decision = str(orchestrator_result.get("decision", ""))

    # Get proposed checks from loop update
    proposed_checks = loop_update.get("proposed_next_checks", [])
    if not isinstance(proposed_checks, list):
        proposed_checks = []

    # Gate checks against policy
    seen_fingerprints: set[str] = set()
    gate_summary = gate_checks(proposed_checks, resolved_policy, seen_fingerprints)

    # Build the complete pass artifact with PASS_ARTIFACT_FIELDS
    pass_artifact = build_policy_enforced_pass_artifact(
        orchestrator_result=orchestrator_result,
        loop_run_id=loop_run_id,
        incident_id=incident_id,
        case_file=case_file,
        policy=resolved_policy,
        gate_summary=gate_summary,
        seen_fingerprints=seen_fingerprints,
        now=resolved_now,
    )

    # Validate pass artifact schema
    is_valid, missing = validate_pass_artifact_schema(pass_artifact)
    if not is_valid:
        pass_artifact["_schema_error"] = f"Missing required fields: {missing}"

    # Emit pass span
    stop_reason = pass_artifact.get("stop_reason")
    emit_pass_span(
        run_id=loop_run_id,
        pass_index=pass_artifact.get("pass_index", 1),
        decision=decision,
        stop_reason=stop_reason,
        checks_accepted=gate_summary.accepted,
        checks_rejected=gate_summary.rejected_mutating + gate_summary.rejected_sensitive + gate_summary.rejected_duplicate,
    )

    # Emit check gate spans for each gated check
    for check in gate_summary.accepted_checks:
        emit_check_gate_span(loop_run_id, pass_artifact.get("pass_index", 1), str(check.get("check_id", "")), True, None)

    for check in gate_summary.rejected_checks:
        emit_check_gate_span(loop_run_id, pass_artifact.get("pass_index", 1), str(check.get("check_id", "")), False, check.get("rejection_reason"))

    # Write policy-enforced pass artifact for P4c validation
    policy_artifact_path: Path | None = None
    try:
        policy_artifact_dir = external_analysis_dir / "diagnosis-loop-passes"
        policy_artifact_dir.mkdir(parents=True, exist_ok=True)
        policy_artifact_path = policy_artifact_dir / f"{run_id}-policy-pass.json"
        artifact_json = json.dumps(pass_artifact, default=str, indent=2)
        policy_artifact_path.write_text(artifact_json, encoding="utf-8")
    except (OSError, ValueError):
        pass

    # Emit loop complete span
    emit_loop_span(loop_run_id, incident_id, resolved_policy, "completed")

    # Build augmented result
    case_file_hash = compute_case_file_hash(case_file)
    result = dict(orchestrator_result)
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
    result["policy_pass_artifact_path"] = str(policy_artifact_path) if policy_artifact_path else None
    result["case_file_hash"] = case_file_hash

    return result

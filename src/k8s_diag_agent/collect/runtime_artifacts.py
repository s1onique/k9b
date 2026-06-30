"""Pass artifact construction and writing for the diagnosis loop runtime.

This module provides:
- build_policy_enforced_pass_artifact(): Creates pass artifacts with PASS_ARTIFACT_FIELDS
- write_runtime_pass_artifact(): Writes artifacts to P4c-compatible paths
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_models import LoopDecision
from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
    validate_pass_artifact_schema,
)

from .incident_diagnosis_loop_runtime_utils import (
    compute_case_file_hash,
    extract_evidence_hashes,
)
from .runtime_gating import GateSummary
from .runtime_state import RUNTIME_SCHEMA_VERSION, LoopRuntimeState

if TYPE_CHECKING:
    pass

# =============================================================================
# Constants
# =============================================================================

# P4c artifact path components
P4C_DIAGNOSIS_SUBDIR = "p4c-k8s-multipass-diagnosis"
P4C_LOOP_PASSES_SUBDIR = "loop-passes"


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


def build_policy_enforced_pass_artifact(
    *,
    loop_run_id: str,
    incident_id: str,
    pass_index: int,
    case_file: Mapping[str, object],
    policy: DiagnosisLoopPolicy,
    gate_summary: GateSummary,
    accepted_fingerprints: list[str],
    runtime_state: LoopRuntimeState,
    decision: str,
    root_cause_summary: str,
    confidence: str,
    runner_result: dict[str, Any] | None,
    now: datetime | None = None,
    budget_exceeded: bool = False,
    budget_stop_reason: LoopStopReason | None = None,
) -> dict[str, Any]:
    """Build a pass artifact with exact PASS_ARTIFACT_FIELDS.
    
    This artifact contains fingerprints for checks ACCEPTED/EXECUTED in THIS PASS,
    not the cumulative seen set.
    """
    resolved_now = now if now is not None else datetime.now(UTC)

    # Determine stop reason
    stop_reason: str | None = None
    if budget_exceeded and budget_stop_reason:
        stop_reason = budget_stop_reason.value
    elif decision.startswith("stop_"):
        stop_reason = decision.replace("stop_", "").replace("_", " ")
        # Map to typed reason
        typed_reason = map_decision_to_stop_reason(decision, None)
        if typed_reason:
            stop_reason = typed_reason.value

    # Determine if loop should continue
    should_continue = decision == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value and not budget_exceeded

    # Build the complete artifact with all PASS_ARTIFACT_FIELDS
    # CRITICAL: accepted_checks contains IDs for checks ACCEPTED this pass
    # check_fingerprints contains fingerprints for checks ACCEPTED this pass
    artifact: dict[str, Any] = {
        # PASS_ARTIFACT_FIELDS
        "loop_run_id": loop_run_id,
        "incident_id": incident_id,
        "pass_index": pass_index,
        "case_file_hash": compute_case_file_hash(case_file),
        # proposed_checks would be from loop_update.proposed_next_checks if we had it
        "proposed_checks": [str(c.get("check_id", "")) for c in gate_summary.accepted_checks + gate_summary.rejected_checks],
        # accepted_checks: checks that PASSED gate and were/will be executed
        "accepted_checks": [str(c.get("check_id", "")) for c in gate_summary.accepted_checks],
        # rejected_checks: checks that FAILED gate
        "rejected_checks": [str(c.get("check_id", "")) for c in gate_summary.rejected_checks],
        # CRITICAL: check_fingerprints contains fingerprints for this pass only
        "check_fingerprints": accepted_fingerprints,
        # Cumulative fingerprints from all passes (for trajectory evaluation)
        "all_seen_fingerprints": list(runtime_state.seen_check_fingerprints),
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
        "budget_exceeded": budget_exceeded,
        "gate_summary": {
            "proposed": gate_summary.proposed,
            "accepted": gate_summary.accepted,
            "rejected_mutating": gate_summary.rejected_mutating,
            "rejected_sensitive": gate_summary.rejected_sensitive,
            "rejected_duplicate": gate_summary.rejected_duplicate,
        },
        # Accurate safety metadata - runner_kind depends on whether fake_handlers are provided
        # Note: In this implementation, fake_handlers is only for testing.
        # The real runtime always uses the fake runner (no real K8s calls).
        # We pass fake_handlers=None to indicate real-mode (still fake, but production).
        "safety_metadata": {
            "read_only": True,
            "policy_enforced": True,
            "allow_mutating_checks": policy.allow_mutating_checks,
            "allow_sensitive_reads": policy.allow_sensitive_reads,
            "runner_kind": "fake",  # Always fake in this implementation
            "checks_executed_count": gate_summary.accepted,
            "checks_rejected_count": len(gate_summary.rejected_checks),
            "mutating_checks_executed_count": 0,
            "sensitive_reads_executed_count": 0,
        },
    }

    # Validate schema
    is_valid, missing = validate_pass_artifact_schema(artifact)
    if not is_valid:
        artifact["_schema_validation_warning"] = f"Missing fields: {missing}"

    return artifact


def write_runtime_pass_artifact(
    external_analysis_dir: Path,
    loop_run_id: str,
    pass_index: int,
    artifact: dict[str, Any],
) -> Path | None:
    """Write pass artifact to the P4c-compatible path.
    
    Path: external_analysis_dir/phase4-diagnosis/p4c-k8s-multipass-diagnosis/loop-passes/<loop_run_id>-pass-<n>.json
    """
    try:
        # Build P4c-compatible path
        phase4_dir = external_analysis_dir / "phase4-diagnosis"
        p4c_dir = phase4_dir / P4C_DIAGNOSIS_SUBDIR
        loop_passes_dir = p4c_dir / P4C_LOOP_PASSES_SUBDIR
        
        loop_passes_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{loop_run_id}-pass-{pass_index}.json"
        artifact_path = loop_passes_dir / filename
        
        artifact_json = json.dumps(artifact, default=str, indent=2)
        artifact_path.write_text(artifact_json, encoding="utf-8")
        
        return artifact_path
    except (OSError, ValueError):
        return None


__all__ = [
    "P4C_DIAGNOSIS_SUBDIR",
    "P4C_LOOP_PASSES_SUBDIR",
    "RUNTIME_SCHEMA_VERSION",
    "build_policy_enforced_pass_artifact",
    "write_runtime_pass_artifact",
]

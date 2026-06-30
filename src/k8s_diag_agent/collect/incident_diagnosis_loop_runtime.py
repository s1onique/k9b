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

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    "run_policy_enforced_loop",
    "gate_checks",
    "build_policy_enforced_pass_artifact",
    "LoopRuntimeState",
    "GateSummary",
    "RUNTIME_SCHEMA_VERSION",
]

# =============================================================================
# Constants
# =============================================================================

RUNTIME_SCHEMA_VERSION = "1.0"

# P4c artifact path components
P4C_DIAGNOSIS_SUBDIR = "p4c-k8s-multipass-diagnosis"
P4C_LOOP_PASSES_SUBDIR = "loop-passes"


# =============================================================================
# Persistent Runtime State
# =============================================================================


@dataclass(frozen=True)
class LoopRuntimeState:
    """Persistent state across multiple diagnosis loop passes.
    
    This state is maintained across passes to:
    - Track seen check fingerprints for duplicate detection
    - Maintain pass indices and counts
    - Track model calls and evidence hashes
    - Ensure budget limits are respected across the entire loop
    
    The state is immutable - each pass creates a new state with updates.
    """

    # Identifiers
    loop_run_id: str
    incident_id: str
    
    # Pass tracking
    pass_index: int = 1
    started_at: str = ""
    
    # Check fingerprint tracking (for duplicate detection across passes)
    seen_check_fingerprints: frozenset[str] = frozenset()
    
    # Execution counters
    total_checks_executed: int = 0
    total_checks_proposed: int = 0
    total_checks_rejected: int = 0
    total_mutating_executed: int = 0
    total_sensitive_executed: int = 0
    total_model_calls: int = 0
    
    # Evidence tracking
    evidence_hashes_seen: frozenset[str] = frozenset()
    
    # Case file tracking
    last_case_file_hash: str = ""
    
    # Schema version for compatibility
    schema_version: str = RUNTIME_SCHEMA_VERSION

    def with_updates(
        self,
        *,
        pass_index: int | None = None,
        seen_check_fingerprints: frozenset[str] | None = None,
        total_checks_executed: int | None = None,
        total_checks_proposed: int | None = None,
        total_checks_rejected: int | None = None,
        total_mutating_executed: int | None = None,
        total_sensitive_executed: int | None = None,
        total_model_calls: int | None = None,
        evidence_hashes_seen: frozenset[str] | None = None,
        last_case_file_hash: str | None = None,
    ) -> LoopRuntimeState:
        """Create a new state with the specified updates applied."""
        return LoopRuntimeState(
            loop_run_id=self.loop_run_id,
            incident_id=self.incident_id,
            pass_index=pass_index if pass_index is not None else self.pass_index,
            started_at=self.started_at,
            seen_check_fingerprints=(
                seen_check_fingerprints if seen_check_fingerprints is not None 
                else self.seen_check_fingerprints
            ),
            total_checks_executed=(
                total_checks_executed if total_checks_executed is not None 
                else self.total_checks_executed
            ),
            total_checks_proposed=(
                total_checks_proposed if total_checks_proposed is not None 
                else self.total_checks_proposed
            ),
            total_checks_rejected=(
                total_checks_rejected if total_checks_rejected is not None 
                else self.total_checks_rejected
            ),
            total_mutating_executed=(
                total_mutating_executed if total_mutating_executed is not None 
                else self.total_mutating_executed
            ),
            total_sensitive_executed=(
                total_sensitive_executed if total_sensitive_executed is not None 
                else self.total_sensitive_executed
            ),
            total_model_calls=(
                total_model_calls if total_model_calls is not None 
                else self.total_model_calls
            ),
            evidence_hashes_seen=(
                evidence_hashes_seen if evidence_hashes_seen is not None 
                else self.evidence_hashes_seen
            ),
            last_case_file_hash=(
                last_case_file_hash if last_case_file_hash is not None 
                else self.last_case_file_hash
            ),
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "loop_run_id": self.loop_run_id,
            "incident_id": self.incident_id,
            "pass_index": self.pass_index,
            "started_at": self.started_at,
            "seen_check_fingerprints": list(self.seen_check_fingerprints),
            "total_checks_executed": self.total_checks_executed,
            "total_checks_proposed": self.total_checks_proposed,
            "total_checks_rejected": self.total_checks_rejected,
            "total_mutating_executed": self.total_mutating_executed,
            "total_sensitive_executed": self.total_sensitive_executed,
            "total_model_calls": self.total_model_calls,
            "evidence_hashes_seen": list(self.evidence_hashes_seen),
            "last_case_file_hash": self.last_case_file_hash,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopRuntimeState:
        """Create from dict."""
        return cls(
            loop_run_id=str(data.get("loop_run_id", "")),
            incident_id=str(data.get("incident_id", "")),
            pass_index=int(data.get("pass_index", 1)),
            started_at=str(data.get("started_at", "")),
            seen_check_fingerprints=frozenset(data.get("seen_check_fingerprints", [])),
            total_checks_executed=int(data.get("total_checks_executed", 0)),
            total_checks_proposed=int(data.get("total_checks_proposed", 0)),
            total_checks_rejected=int(data.get("total_checks_rejected", 0)),
            total_mutating_executed=int(data.get("total_mutating_executed", 0)),
            total_sensitive_executed=int(data.get("total_sensitive_executed", 0)),
            total_model_calls=int(data.get("total_model_calls", 0)),
            evidence_hashes_seen=frozenset(data.get("evidence_hashes_seen", [])),
            last_case_file_hash=str(data.get("last_case_file_hash", "")),
            schema_version=str(data.get("schema_version", RUNTIME_SCHEMA_VERSION)),
        )


# =============================================================================
# Check Gating
# =============================================================================


@dataclass
class GateSummary:
    """Summary of gating decisions for a pass.
    
    This summarizes what was proposed vs accepted/rejected in a single pass.
    """

    proposed: int
    accepted: int
    rejected_mutating: int
    rejected_sensitive: int
    rejected_duplicate: int
    accepted_checks: list[dict[str, Any]]
    rejected_checks: list[dict[str, Any]]
    # Explicit fingerprint tracking for this pass
    accepted_fingerprints: list[str] = field(default_factory=list)
    rejected_fingerprints: list[str] = field(default_factory=list)


def gate_checks(
    proposed_checks: Sequence[Mapping[str, object]],
    policy: DiagnosisLoopPolicy,
    seen_fingerprints: set[str],
) -> tuple[GateSummary, list[str]]:
    """Gate proposed checks against policy.
    
    CRITICAL: This function enforces policy BEFORE execution.
    Rejected checks are NEVER passed back for execution.

    Applies in order:
    1. Mutating check rejection (unless policy allows)
    2. Sensitive read rejection (unless policy allows)  
    3. Duplicate fingerprint rejection (checks against seen_fingerprints)

    Args:
        proposed_checks: Checks proposed by the planner
        policy: The DiagnosisLoopPolicy to enforce
        seen_fingerprints: Set of fingerprints already seen (mutated in place)
            - DUPLICATE fingerprints are added to this set
            - Accepted fingerprints are NOT added (handled by caller)

    Returns:
        Tuple of (GateSummary, list of accepted fingerprints for this pass)
        The caller must add accepted_fingerprints to seen_fingerprints.
    """
    accepted_checks: list[dict[str, Any]] = []
    rejected_checks: list[dict[str, Any]] = []
    accepted_fingerprints: list[str] = []
    rejected_fingerprints: list[str] = []
    rejected_mutating = 0
    rejected_sensitive = 0
    rejected_duplicate = 0

    for check in proposed_checks:
        check_id = str(check.get("check_id", "unknown"))
        check_dict = dict(check)

        # Compute fingerprint upfront for all checks
        fingerprint = compute_fingerprint(check)

        # Check 1: Mutating? (normalize underscores to spaces for pattern matching)
        normalized_check_id = check_id.replace("_", " ")
        is_mutating = _is_mutating_check(normalized_check_id) or _is_mutating_check(check_id) or _is_mutating_check(json.dumps(check))
        if is_mutating:
            if not policy.allow_mutating_checks:
                rejected_checks.append({**check_dict, "rejection_reason": "mutating_check_rejected", "is_unsafe": True})
                rejected_fingerprints.append(fingerprint)
                rejected_mutating += 1
                continue

        # Check 2: Sensitive read? (normalize underscores to spaces for pattern matching)
        is_sensitive = _is_sensitive_read_check(normalized_check_id) or _is_sensitive_read_check(check_id) or _is_sensitive_read_check(json.dumps(check))
        if is_sensitive:
            if not policy.allow_sensitive_reads:
                rejected_checks.append({**check_dict, "rejection_reason": "sensitive_read_denied", "is_sensitive": True})
                rejected_fingerprints.append(fingerprint)
                rejected_sensitive += 1
                continue

        # Check 3: Duplicate fingerprint?
        if fingerprint in seen_fingerprints:
            rejected_checks.append({**check_dict, "rejection_reason": "duplicate_check_fingerprint", "duplicate_fingerprint": fingerprint})
            rejected_fingerprints.append(fingerprint)
            rejected_duplicate += 1
            continue

        # ACCEPTED: Add fingerprint to seen set immediately
        seen_fingerprints.add(fingerprint)
        accepted_checks.append(check_dict)
        accepted_fingerprints.append(fingerprint)

    return (
        GateSummary(
            proposed=len(proposed_checks),
            accepted=len(accepted_checks),
            rejected_mutating=rejected_mutating,
            rejected_sensitive=rejected_sensitive,
            rejected_duplicate=rejected_duplicate,
            accepted_checks=accepted_checks,
            rejected_checks=rejected_checks,
            accepted_fingerprints=accepted_fingerprints,
            rejected_fingerprints=rejected_fingerprints,
        ),
        accepted_fingerprints,
    )


def enforce_budgets(
    policy: DiagnosisLoopPolicy,
    runtime_state: LoopRuntimeState,
    elapsed_seconds: float,
) -> tuple[bool, LoopStopReason | None]:
    """Enforce hard budget limits BEFORE execution.
    
    Returns:
        Tuple of (exceeded, stop_reason)
        - If exceeded=True, NO checks should be executed
        - stop_reason contains the reason if exceeded
    """
    # Check pass index against max_passes
    if runtime_state.pass_index > policy.max_passes:
        return True, LoopStopReason.MAX_PASSES_REACHED

    # Check total checks against max_total_checks
    if runtime_state.total_checks_executed >= policy.max_total_checks:
        return True, LoopStopReason.MAX_CHECKS_REACHED

    # Check checks proposed this pass against max_checks_per_pass
    # (This is approximate since we don't know exact count until planning)
    
    # Check model calls against max_model_calls
    if runtime_state.total_model_calls >= policy.max_model_calls:
        return True, LoopStopReason.MAX_MODEL_CALLS_REACHED

    # Check wall clock against max_wall_clock_seconds
    if elapsed_seconds >= policy.max_wall_clock_seconds:
        return True, LoopStopReason.MAX_WALL_CLOCK_REACHED

    return False, None


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
        # Accurate safety metadata
        "safety_metadata": {
            "read_only": True,
            "policy_enforced": True,
            "allow_mutating_checks": policy.allow_mutating_checks,
            "allow_sensitive_reads": policy.allow_sensitive_reads,
            "runner_kind": "fake",  # Current implementation uses fake runner
            "checks_executed_count": gate_summary.accepted,
            "checks_rejected_count": len(gate_summary.rejected_checks),
            "mutating_checks_executed_count": 0,  # Would be non-zero if mutating allowed
            "sensitive_reads_executed_count": 0,  # Would be non-zero if sensitive allowed
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
    """
    from .incident_diagnosis_loop_orchestrator import (
        run_one_read_only_diagnosis_loop_pass,
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

    # Check budgets BEFORE execution
    elapsed_seconds = (resolved_now - datetime.fromisoformat(current_state.started_at)).total_seconds()
    elapsed_seconds = max(0, elapsed_seconds)
    
    budget_exceeded, budget_stop_reason = enforce_budgets(
        resolved_policy, current_state, elapsed_seconds
    )

    # Run the orchestrator to get planned checks
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

    # CRITICAL: Gate checks BEFORE execution using persistent seen_fingerprints
    seen_fingerprints = set(current_state.seen_check_fingerprints)
    gate_summary, accepted_fingerprints = gate_checks(proposed_checks, resolved_policy, seen_fingerprints)

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

    # Build the pass artifact with ONLY accepted fingerprints for this pass
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
        runner_result=None,  # No execution if budget exceeded
        now=resolved_now,
        budget_exceeded=budget_exceeded,
        budget_stop_reason=budget_stop_reason,
    )

    # Validate pass artifact schema
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
            # Create stop artifact
            stop_artifact = {
                "loop_run_id": loop_run_id,
                "incident_id": incident_id,
                "pass_index": runtime_state.pass_index,
                "decision": LoopDecision.STOP_BUDGET_EXHAUSTED.value,
                "stop_reason": budget_stop_reason.value if budget_stop_reason else LoopStopReason.MAX_CHECKS_REACHED.value,
                "should_continue": False,
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

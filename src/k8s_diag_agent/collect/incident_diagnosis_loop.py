"""Bounded multi-pass incident diagnosis loop contract and state machine.

This module provides the bounded diagnosis loop that:
- Maintains loop state across passes
- Tracks pass budget and root-cause candidates
- Validates LLM-reviewed next-check proposals against policy
- Makes explicit loop decisions (run checks, stop)
- Enforces stop conditions
- Preserves read-only safety guarantees

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic state transitions
- Explicit safety metadata

This module does NOT:
- Execute checks
- Instantiate Kubernetes clients
- Call shell/subprocess
- Persist loop state
- Turn LLM text into executable commands
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .incident_next_check_policy import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_TOTAL_CHECKS,
    DISALLOWED_ACTIONS,
    NextCheckPolicy,
)

__all__ = [
    "LoopDecision",
    "StopReason",
    "Confidence",
    "RootCauseCandidate",
    "DiagnosisPass",
    "LoopState",
    "plan_next_diagnosis_pass",
    "LOOP_SCHEMA_VERSION",
]


# =============================================================================
# Constants
# =============================================================================

# Schema version for tracking structure evolution
LOOP_SCHEMA_VERSION = "1.0"

# Default bounds
DEFAULT_MAX_PASSES = 3

# Root-cause credibility thresholds
MIN_HIGH_CONFIDENCE_EVIDENCE = 1
MAX_MISSING_EVIDENCE_FOR_CREDIBLE = 2


# =============================================================================
# Enums
# =============================================================================


class LoopDecision(StrEnum):
    """Explicit loop decision outcomes."""

    # Continue loop with validated checks
    RUN_ALLOWED_READ_ONLY_CHECKS = "run_allowed_read_only_checks"

    # Stop: credible root cause found
    STOP_ROOT_CAUSE_FOUND = "stop_root_cause_found"

    # Stop: no safe checks available
    STOP_NO_SAFE_CHECKS = "stop_no_safe_checks"

    # Stop: pass budget exhausted
    STOP_BUDGET_EXHAUSTED = "stop_budget_exhausted"

    # Stop: low confidence with no progress
    STOP_LOW_CONFIDENCE_NO_PROGRESS = "stop_low_confidence_no_progress"

    # Stop: safety blocked (mutation request detected)
    STOP_SAFETY_BLOCKED = "stop_safety_blocked"

    # Stop: no checks proposed
    STOP_NO_CHECKS_PROPOSED = "stop_no_checks_proposed"


class StopReason(StrEnum):
    """Why the loop stopped."""

    ROOT_CAUSE_FOUND = "root_cause_found"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_SAFE_CHECKS = "no_safe_checks"
    LOW_CONFIDENCE_NO_PROGRESS = "low_confidence_no_progress"
    SAFETY_BLOCKED = "safety_blocked"
    NO_CHECKS_PROPOSED = "no_checks_proposed"


class Confidence(StrEnum):
    """Diagnosis confidence levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# =============================================================================
# Root-Cause Candidate
# =============================================================================


@dataclass(frozen=True)
class RootCauseCandidate:
    """A potential root cause with confidence and evidence."""

    summary: str
    confidence: Confidence
    supporting_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    credible: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "summary": self.summary,
            "confidence": self.confidence.value if isinstance(self.confidence, Confidence) else self.confidence,
            "supporting_evidence": list(self.supporting_evidence),
            "missing_evidence": list(self.missing_evidence),
            "credible": self.credible,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RootCauseCandidate:
        """Create from dict."""
        confidence = data.get("confidence", "unknown")
        if isinstance(confidence, str):
            confidence = Confidence(confidence)

        supporting = data.get("supporting_evidence", [])
        if isinstance(supporting, list):
            supporting = tuple(supporting)

        missing = data.get("missing_evidence", [])
        if isinstance(missing, list):
            missing = tuple(missing)

        return cls(
            summary=str(data.get("summary", "")),
            confidence=confidence,
            supporting_evidence=supporting,
            missing_evidence=missing,
            credible=bool(data.get("credible", False)),
        )


def build_root_cause_candidate(
    diagnosis_report: Mapping[str, Any],
    *,
    min_high_confidence_evidence: int = MIN_HIGH_CONFIDENCE_EVIDENCE,
    max_missing_evidence: int = MAX_MISSING_EVIDENCE_FOR_CREDIBLE,
) -> RootCauseCandidate | None:
    """Build root-cause candidate from diagnosis report.

    Args:
        diagnosis_report: The diagnosis report from build_incident_diagnosis()
        min_high_confidence_evidence: Minimum evidence for high confidence
        max_missing_evidence: Maximum missing evidence for credible

    Returns:
        RootCauseCandidate or None if no likely causes
    """
    diagnosis = diagnosis_report.get("diagnosis", {})
    likely_causes = diagnosis.get("likely_causes", [])
    supporting_evidence = diagnosis.get("supporting_evidence", [])
    uncertainties = diagnosis.get("uncertainties", [])
    confidence_str = diagnosis.get("confidence", "unknown")

    try:
        confidence = Confidence(confidence_str)
    except ValueError:
        confidence = Confidence.UNKNOWN

    # Determine credible based on deterministic criteria
    credible = (
        confidence == Confidence.HIGH
        and len(supporting_evidence) >= min_high_confidence_evidence
        and len(uncertainties) <= max_missing_evidence
    )

    # Build summary from likely causes
    summary = ""
    if likely_causes:
        if isinstance(likely_causes, list) and likely_causes:
            summary = "; ".join(str(c) for c in likely_causes[:3])
        else:
            summary = str(likely_causes)

    # Convert to tuples
    supporting_tuple = tuple(str(e) for e in supporting_evidence) if supporting_evidence else ()
    missing_tuple = tuple(str(u) for u in uncertainties) if uncertainties else ()

    return RootCauseCandidate(
        summary=summary,
        confidence=confidence,
        supporting_evidence=supporting_tuple,
        missing_evidence=missing_tuple,
        credible=credible,
    )


def _check_root_cause_credible(
    candidate: RootCauseCandidate | None,
) -> bool:
    """Check if root-cause candidate meets credibility criteria."""
    if candidate is None:
        return False
    return candidate.credible


# =============================================================================
# Diagnosis Pass
# =============================================================================


@dataclass(frozen=True)
class DiagnosisPass:
    """A single diagnosis pass in the loop."""

    pass_index: int
    case_file_summary: dict[str, Any]
    diagnosis: dict[str, Any]
    root_cause_candidate: dict[str, Any] | None
    proposed_next_checks: tuple[dict[str, Any], ...]
    policy_decision: dict[str, Any]
    stop_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "pass_index": self.pass_index,
            "case_file_summary": self.case_file_summary,
            "diagnosis": self.diagnosis,
            "root_cause_candidate": self.root_cause_candidate,
            "proposed_next_checks": list(self.proposed_next_checks),
            "policy_decision": self.policy_decision,
            "stop_reason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DiagnosisPass:
        """Create from dict."""
        proposed = data.get("proposed_next_checks", [])
        if isinstance(proposed, list):
            proposed = tuple(proposed)

        root_cause = data.get("root_cause_candidate")
        if root_cause is not None:
            root_cause = dict(root_cause)

        return cls(
            pass_index=int(data.get("pass_index", 1)),
            case_file_summary=dict(data.get("case_file_summary", {})),
            diagnosis=dict(data.get("diagnosis", {})),
            root_cause_candidate=root_cause,
            proposed_next_checks=proposed,
            policy_decision=dict(data.get("policy_decision", {})),
            stop_reason=data.get("stop_reason"),
        )


# =============================================================================
# Loop State
# =============================================================================


@dataclass(frozen=True)
class LoopState:
    """Complete loop state for a diagnosis session."""

    schema_version: str
    incident_id: str
    started_at: str
    updated_at: str
    read_only: bool
    allowed_actions: tuple[str, ...]
    disallowed_actions: tuple[str, ...]
    pass_budget: dict[str, Any]
    passes: tuple[DiagnosisPass, ...]
    status: str
    stop_reason: str | None
    total_checks_planned: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization (JSON-safe)."""
        return {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "read_only": self.read_only,
            "allowed_actions": list(self.allowed_actions),
            "disallowed_actions": list(self.disallowed_actions),
            "pass_budget": self.pass_budget,
            "passes": [p.to_dict() for p in self.passes],
            "status": self.status,
            "stop_reason": self.stop_reason,
            "total_checks_planned": self.total_checks_planned,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LoopState:
        """Create from dict."""
        passes_data = data.get("passes", [])
        passes = tuple(DiagnosisPass.from_dict(p) for p in passes_data)

        allowed = data.get("allowed_actions", [])
        if isinstance(allowed, list):
            allowed = tuple(allowed)

        disallowed = data.get("disallowed_actions", [])
        if isinstance(disallowed, list):
            disallowed = tuple(disallowed)

        return cls(
            schema_version=str(data.get("schema_version", LOOP_SCHEMA_VERSION)),
            incident_id=str(data.get("incident_id", "")),
            started_at=str(data.get("started_at", "")),
            updated_at=str(data.get("updated_at", "")),
            read_only=bool(data.get("read_only", True)),
            allowed_actions=allowed,
            disallowed_actions=disallowed,
            pass_budget=dict(data.get("pass_budget", {})),
            passes=passes,
            status=str(data.get("status", "running")),
            stop_reason=data.get("stop_reason"),
            total_checks_planned=int(data.get("total_checks_planned", 0)),
        )


def create_initial_loop_state(
    incident_id: str,
    *,
    now: datetime | None = None,
    max_passes: int = DEFAULT_MAX_PASSES,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
    max_total_checks: int = DEFAULT_MAX_TOTAL_CHECKS,
) -> LoopState:
    """Create initial loop state for a diagnosis session.

    Args:
        incident_id: The incident to diagnose
        now: Optional datetime for deterministic timestamps
        max_passes: Maximum diagnosis passes
        max_checks_per_pass: Maximum checks per pass
        max_total_checks: Maximum total checks across all passes

    Returns:
        Initial LoopState
    """
    timestamp = now if now is not None else datetime.now(UTC)
    timestamp_str = timestamp.isoformat()

    return LoopState(
        schema_version=LOOP_SCHEMA_VERSION,
        incident_id=incident_id,
        started_at=timestamp_str,
        updated_at=timestamp_str,
        read_only=True,
        allowed_actions=(),
        disallowed_actions=tuple(DISALLOWED_ACTIONS),
        pass_budget={
            "max_passes": max_passes,
            "current_pass": 1,
            "max_checks_per_pass": max_checks_per_pass,
            "max_total_checks": max_total_checks,
        },
        passes=(),
        status="running",
        stop_reason=None,
        total_checks_planned=0,
    )


def increment_pass(state: LoopState, now: datetime | None = None) -> LoopState:
    """Increment pass counter in loop state.

    Args:
        state: Current loop state
        now: Optional datetime for timestamp

    Returns:
        New LoopState with incremented pass
    """
    timestamp = now if now is not None else datetime.now(UTC)
    timestamp_str = timestamp.isoformat()

    budget = dict(state.pass_budget)
    new_pass = budget["current_pass"] + 1
    budget["current_pass"] = new_pass

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp_str,
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=budget,
        passes=state.passes,
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned,
    )


def add_pass_to_state(
    state: LoopState,
    diagnosis_pass: DiagnosisPass,
    *,
    now: datetime | None = None,
) -> LoopState:
    """Add a completed pass to loop state.

    Args:
        state: Current loop state
        diagnosis_pass: Completed diagnosis pass
        now: Optional datetime for deterministic timestamps

    Returns:
        New LoopState with pass added
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes + (diagnosis_pass,),
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned,
    )


def stop_loop(
    state: LoopState,
    stop_reason: StopReason,
    *,
    now: datetime | None = None,
) -> LoopState:
    """Stop the loop with a reason.

    Args:
        state: Current loop state
        stop_reason: Reason for stopping
        now: Optional datetime for deterministic timestamps

    Returns:
        New LoopState with status=stopped
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes,
        status="stopped",
        stop_reason=stop_reason.value,
        total_checks_planned=state.total_checks_planned,
    )


def record_planned_checks(
    state: LoopState,
    count: int,
    *,
    now: datetime | None = None,
) -> LoopState:
    """Record planned checks in loop state.

    Args:
        state: Current loop state
        count: Number of checks being planned
        now: Optional datetime for timestamp

    Returns:
        New LoopState with updated total_checks_planned
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes,
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned + count,
    )


# =============================================================================
# Stop Condition Checkers
# =============================================================================


def check_root_cause_found(
    root_cause: RootCauseCandidate | None,
) -> bool:
    """Check if credible root cause is found."""
    return _check_root_cause_credible(root_cause)


def check_budget_exhausted(state: LoopState) -> bool:
    """Check if pass budget is exhausted."""
    current: int = state.pass_budget["current_pass"]
    maximum: int = state.pass_budget["max_passes"]
    return bool(current >= maximum)


def check_no_checks_proposed(
    proposals: Sequence[Mapping[str, object]],
) -> bool:
    """Check if no checks were proposed."""
    return len(proposals) == 0


def check_no_safe_checks(
    proposals: Sequence[Mapping[str, object]],
    validation_results: Sequence[Any],
) -> bool:
    """Check if all proposed checks were rejected."""
    if not proposals:
        return False
    # All proposals were rejected
    return all(not r.accepted for r in validation_results)


def check_low_confidence_no_progress(
    root_cause: RootCauseCandidate | None,
    prior_pass_count: int,
) -> bool:
    """Check if low confidence with no progress after multiple passes.

    Args:
        root_cause: Current root cause candidate
        prior_pass_count: Number of prior passes

    Returns:
        True if low confidence with no progress
    """
    if root_cause is None:
        return prior_pass_count >= 2

    # Low confidence and no supporting evidence after multiple passes
    if root_cause.confidence in (Confidence.LOW, Confidence.UNKNOWN):
        return prior_pass_count >= 2 and len(root_cause.supporting_evidence) == 0

    return False


def check_safety_blocked(
    proposals: Sequence[Mapping[str, object]],
    validation_results: Sequence[Any],
) -> bool:
    """Check if any safety-blocked rejections occurred."""
    for result in validation_results:
        if not result.accepted and result.safety_blocked:
            return True
    return False


# =============================================================================
# Next-Check Proposal Extraction
# =============================================================================


def extract_next_check_proposals(
    diagnosis_report: Mapping[str, object],
    *,
    max_proposals: int = DEFAULT_MAX_CHECKS_PER_PASS,
) -> list[dict[str, Any]]:
    """Extract next-check proposals from diagnosis report.

    This is a conversion helper - does not make LLM calls.

    Args:
        diagnosis_report: The diagnosis report from build_incident_diagnosis()
        max_proposals: Maximum proposals to extract

    Returns:
        List of check proposal dicts
    """
    proposals: list[dict[str, Any]] = []

    # Extract from recommended_investigations
    diagnosis = diagnosis_report.get("diagnosis", {})
    investigations = diagnosis.get("recommended_investigations", [])

    for i, inv in enumerate(investigations[:max_proposals]):
        if isinstance(inv, str):
            proposals.append({
                "check_id": f"investigation_{i + 1}",
                "title": inv[:100] if len(inv) > 100 else inv,
                "rationale": inv,
                "priority": i + 1,
                "risk_level": "low",
                "read_only": True,
                "source": "llm-review",
            })
        elif isinstance(inv, dict):
            # Already a structured proposal
            proposals.append(dict(inv))

    return proposals


# =============================================================================
# Main Loop Planning Function
# =============================================================================


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
    timestamp = now if now is not None else datetime.now(UTC)

    # Build or restore loop state
    if prior_loop_state is not None:
        loop_state = LoopState.from_dict(prior_loop_state)
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

    # 4. No checks proposed
    if check_no_checks_proposed(proposals):
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


def _build_loop_update(
    loop_state: LoopState,
    decision: LoopDecision,
    stop_reason: StopReason | None,
    accepted_checks: list[dict[str, Any]],
    rejected_checks: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
) -> dict[str, object]:
    """Build the loop update result dict."""
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
        "rejection_summary": rejection_reasons,
        "passes_completed": len(loop_state.passes),
        "current_pass": loop_state.pass_budget["current_pass"],
        "total_checks_planned": loop_state.total_checks_planned,
        "safety_metadata": safety_metadata,
        "note": "This result does not execute checks. Future ACT will wire execution.",
    }

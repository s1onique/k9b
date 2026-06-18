"""Models and constants for incident diagnosis loop.

This module contains enums, constants, and dataclass definitions.

Design constraints:
- Pure type definitions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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
    def from_dict(cls, data: dict[str, Any]) -> RootCauseCandidate:
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
    def from_dict(cls, data: dict[str, Any]) -> DiagnosisPass:
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
    def from_dict(cls, data: dict[str, Any]) -> LoopState:
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


__all__ = [
    "LOOP_SCHEMA_VERSION",
    "DEFAULT_MAX_PASSES",
    "MIN_HIGH_CONFIDENCE_EVIDENCE",
    "MAX_MISSING_EVIDENCE_FOR_CREDIBLE",
    "LoopDecision",
    "StopReason",
    "Confidence",
    "RootCauseCandidate",
    "DiagnosisPass",
    "LoopState",
]

"""Hypothesis burst models for automatic diagnosis loop.

This module contains:
- HypothesisCandidateClass: Diagnostic category for a hypothesis
- HypothesisCandidate: Individual ranked hypothesis candidate with falsifier fields
- CandidateCheck: Discriminating check for hypothesis testing
- HypothesisBurst: Output of a hypothesis burst pass
- HypothesisValidationError: Error raised when hypothesis fails validation
- SCHEMA_VERSION: Schema version for serialization
- MAX_HYPOTHESES: Maximum hypotheses to generate
- MAX_CANDIDATE_CHECKS: Maximum candidate checks to propose

These are pure data models with no implementation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"

# =============================================================================
# Hypothesis Candidate Class (diagnostic category)
# =============================================================================


class HypothesisCandidateClass(StrEnum):
    """Diagnostic category for a hypothesis."""

    CRASH_LOOP = "crash_loop"
    IMAGE_PULL_ERROR = "image_pull_error"
    PENDING_POD = "pending_pod"
    FAILED_POD = "failed_pod"
    DEPLOYMENT_UNAVAILABLE = "deployment_unavailable"
    WARNING_EVENT_BURST = "warning_event_burst"
    NODE_NOT_READY = "node_not_ready"
    PVC_ISSUE = "pvc_issue"
    UNKNOWN = "unknown"


# =============================================================================
# Hypothesis Candidate
# =============================================================================


@dataclass(frozen=True)
class HypothesisCandidate:
    """A ranked hypothesis for an incident with falsifier fields.

    Bounds:
    - statement: max 300 chars
    - falsifier: max 300 chars
    - expected_if_true: max 200 chars (REQUIRED)
    - expected_if_false: max 200 chars (REQUIRED)
    - evidence_for: max 8 items
    - evidence_against: max 8 items
    - unknowns: max 5 items
    """

    hypothesis_id: str
    rank: int
    statement: str
    candidate_class: HypothesisCandidateClass
    confidence: float  # 0.0 to 1.0
    impact: str  # low|medium|high|critical
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    unknowns: tuple[str, ...]
    # Falsifier fields (all REQUIRED)
    falsifier: str  # Human-readable statement of what would falsify this hypothesis
    expected_if_true: str  # What evidence CONFIRMS the hypothesis
    expected_if_false: str  # What evidence REFUTES the hypothesis
    discriminating_check_id: str | None  # Which check DISCRIMINATES this hypothesis
    next_best_check: str | None  # Which check to run next
    status: str  # open|supported|weakened|falsified|merged
    why_now: str

    def __post_init__(self) -> None:
        """Validate falsifier fields are present."""
        if not self.falsifier:
            raise ValueError(f"Hypothesis {self.hypothesis_id}: falsifier is required")
        if not self.expected_if_true:
            raise ValueError(f"Hypothesis {self.hypothesis_id}: expected_if_true is required")
        if not self.expected_if_false:
            raise ValueError(f"Hypothesis {self.hypothesis_id}: expected_if_false is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "rank": self.rank,
            "statement": self.statement[:300],
            "candidate_class": self.candidate_class.value,
            "confidence": round(self.confidence, 2),
            "impact": self.impact,
            "evidence_for": list(self.evidence_for)[:8],
            "evidence_against": list(self.evidence_against)[:8],
            "unknowns": list(self.unknowns)[:5],
            "falsifier": self.falsifier[:300],
            "expected_if_true": self.expected_if_true[:200],
            "expected_if_false": self.expected_if_false[:200],
            "discriminating_check_id": self.discriminating_check_id,
            "next_best_check": self.next_best_check,
            "status": self.status,
            "why_now": self.why_now,
        }


class HypothesisValidationError(Exception):
    """Raised when a hypothesis fails validation."""

    pass


# =============================================================================
# Candidate Check
# =============================================================================


@dataclass(frozen=True)
class CandidateCheck:
    """A discriminating check for hypothesis testing.

    Cost/value model for check selection:
    - cost: low|medium|high
    - expected_value: low|medium|high
    """

    check_id: str
    kind: str  # read_only_kubernetes
    cost: str  # low|medium|high
    expected_value: str  # low|medium|high
    targets_hypotheses: tuple[str, ...]
    requires: dict[str, bool]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "check_id": self.check_id,
            "kind": self.kind,
            "cost": self.cost,
            "expected_value": self.expected_value,
            "targets_hypotheses": list(self.targets_hypotheses),
            "requires": self.requires,
            "rationale": self.rationale,
        }


# =============================================================================
# Hypothesis Burst Output
# =============================================================================


@dataclass(frozen=True)
class HypothesisBurst:
    """Output of a hypothesis burst pass.

    This is Pass 0: uses existing evidence only, no Kubernetes reads.
    """

    pass_index: int = 0
    pass_kind: str = "hypothesis_burst"
    hypotheses: tuple[HypothesisCandidate, ...] = field(default_factory=tuple)
    candidate_checks: tuple[CandidateCheck, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION
    validated_check_ids: tuple[str, ...] = field(default_factory=tuple)  # Track validated check IDs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "schema_version": self.schema_version,
            "pass_index": self.pass_index,
            "pass_kind": self.pass_kind,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "candidate_checks": [c.to_dict() for c in self.candidate_checks],
        }


# =============================================================================
# Constants
# =============================================================================

# Maximum hypotheses to generate
MAX_HYPOTHESES = 5

# Maximum candidate checks to propose
MAX_CANDIDATE_CHECKS = 3


__all__ = [
    "SCHEMA_VERSION",
    "HypothesisCandidateClass",
    "HypothesisCandidate",
    "HypothesisValidationError",
    "CandidateCheck",
    "HypothesisBurst",
    "MAX_HYPOTHESES",
    "MAX_CANDIDATE_CHECKS",
]

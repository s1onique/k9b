"""Alertmanager durable learning models and threshold constants.

This module defines the core data models for Alertmanager durable learning:
- DurableFeedbackPattern: A stable feedback pattern that may warrant a proposal
- DurableProposalCandidate: A proposal candidate for operator review

Plus threshold constants that control proposal generation criteria.

## Durable-Learning Boundary

The system distinguishes between run-scoped learning (safe, implemented) and
durable learning (operator-approved, proposal-oriented):

| Signal        | Trustworthy Beyond Single Run? | Durable Mechanism               |
|-------------|-------------------------------|--------------------------------|
| `not_relevant` | YES - with operator review      | Aggregated into proposal       |
| `noisy`      | YES - with operator review      | Aggregated into proposal       |
| `relevant`   | NO - excluded from durable path | None (observational only)      |
| `unsure`     | NO - excluded from durable path | None (never durable)           |

## Proposal Trigger Criteria

A durable proposal candidate is generated when:
1. Same dimension (namespace/cluster/service) marked `noisy` or `not_relevant`
2. Across 3+ distinct runs
3. At least 2 instances per run on average
"""

from __future__ import annotations

__all__ = [
    "_DURABLE_SIGNALS",
    "_FORBIDDEN_DURABLE_SIGNALS",
    "_MIN_INSTANCES_PER_RUN",
    "_MIN_RUNS_FOR_PROPOSAL",
    "DurableFeedbackPattern",
    "DurableProposalCandidate",
]

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Minimum runs and instances required before considering a proposal.
# This prevents sparse feedback from driving premature proposals.
_MIN_RUNS_FOR_PROPOSAL = 3
_MIN_INSTANCES_PER_RUN = 2

# Signals that can become durable learning (proposal candidates)
_DURABLE_SIGNALS = frozenset(("not_relevant", "noisy"))

# Signals that are NEVER durable
_FORBIDDEN_DURABLE_SIGNALS = frozenset(("relevant", "unsure"))


@dataclass(frozen=True)
class DurableFeedbackPattern:
    """A stable feedback pattern that may warrant a proposal.

    Represents a dimension that has been repeatedly marked as noisy/not_relevant
    across multiple runs, forming the basis for a proposal candidate.
    """
    dimension: str  # "namespace", "cluster", "service"
    values: frozenset[str]  # specific values marked
    signal: str  # "not_relevant" or "noisy"
    run_count: int  # number of runs with this pattern
    total_instances: int  # total judgment instances
    source_artifacts: tuple[str, ...]  # paths to source review artifacts
    first_seen: datetime
    last_seen: datetime
    cluster_labels: frozenset[str]  # clusters where this was observed

    @property
    def meets_proposal_threshold(self) -> bool:
        """Check if this pattern meets criteria for a proposal candidate."""
        return (
            self.run_count >= _MIN_RUNS_FOR_PROPOSAL
            and self.total_instances >= self.run_count * _MIN_INSTANCES_PER_RUN
        )

    @property
    def is_actionable(self) -> bool:
        """Check if this pattern is actionable (meets threshold and is allowed)."""
        return (
            self.signal in _DURABLE_SIGNALS
            and self.meets_proposal_threshold
        )

    @property
    def proposal_rationale(self) -> str:
        """Generate rationale text for a proposal based on this pattern."""
        if self.signal == "noisy":
            return (
                f"Consider reducing Alertmanager influence for {self.dimension} "
                f"'{', '.join(sorted(self.values))}' - marked noisy across "
                f"{self.run_count} runs with {self.total_instances} total instances"
            )
        else:
            return (
                f"Consider stop-tracking Alertmanager {self.dimension} "
                f"'{', '.join(sorted(self.values))}' - marked not relevant across "
                f"{self.run_count} runs with {self.total_instances} total instances"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "values": sorted(self.values),
            "signal": self.signal,
            "run_count": self.run_count,
            "total_instances": self.total_instances,
            "source_artifacts": list(self.source_artifacts),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "cluster_labels": sorted(self.cluster_labels),
            "meets_proposal_threshold": self.meets_proposal_threshold,
            "is_actionable": self.is_actionable,
            "proposal_rationale": self.proposal_rationale,
        }


@dataclass
class DurableProposalCandidate:
    """A proposal candidate for operator review.

    This is a durable artifact that represents a potential policy change
    based on stable feedback patterns. It requires explicit operator
    approval before any ranking modification.
    """
    proposal_id: str
    pattern: DurableFeedbackPattern
    cluster_label: str  # primary cluster for the proposal
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    proposal_type: str = "alertmanager_dimension_suppression"

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "cluster_label": self.cluster_label,
            "created_at": self.created_at.isoformat(),
            "pattern": self.pattern.to_dict(),
            "expected_benefit": f"Reduced noise from {self.pattern.dimension} "
                               f"'{', '.join(sorted(self.pattern.values))}'",
            "confidence": self._compute_confidence(),
            "promotion_payload": self._build_promotion_payload(),
        }

    def _compute_confidence(self) -> str:
        """Compute confidence based on evidence stability."""
        if self.pattern.run_count >= 5 and self.pattern.total_instances >= 10:
            return "high"
        elif self.pattern.run_count >= 4 and self.pattern.total_instances >= 6:
            return "medium"
        return "low"

    def _build_promotion_payload(self) -> dict[str, Any]:
        """Build promotion payload for operator review tooling."""
        return {
            "action": "suppress_dimension",
            "dimension": self.pattern.dimension,
            "values": list(self.pattern.values),
            "signal": self.pattern.signal,
            "evidence": {
                "run_count": self.pattern.run_count,
                "total_instances": self.pattern.total_instances,
                "cluster_labels": list(self.pattern.cluster_labels),
            },
        }

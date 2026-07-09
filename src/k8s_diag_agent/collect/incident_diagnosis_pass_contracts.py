"""Pass executor contracts for automatic diagnosis loop.

This module contains:
- StopDecision: Stop decision outcomes for a pass
- PassResult: Result of a single evidence pass
- SCHEMA_VERSION: Schema version for serialization

These are pure data contracts with no implementation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"

# =============================================================================
# Stop Decision
# =============================================================================


class StopDecision:
    """Stop decision outcomes for a pass."""

    CONTINUE = "continue"
    STOP_CONFIDENCE_THRESHOLD = "confidence_threshold_reached"
    STOP_MAX_PASSES = "max_passes_reached"
    STOP_NO_DISCRIMINATING_CHECKS = "no_discriminating_checks"
    STOP_CHECK_BUDGET_EXHAUSTED = "check_budget_exhausted"
    STOP_TIME_BUDGET_EXHAUSTED = "time_budget_exhausted"
    STOP_PROVIDER_UNAVAILABLE = "provider_unavailable"
    STOP_INCIDENT_TERMINAL = "incident_terminal"
    STOP_PASS_ERROR = "pass_error"
    STOP_ALL_HYPOTHESES_FALSIFIED = "all_hypotheses_falsified"


# =============================================================================
# Pass Result
# =============================================================================


@dataclass
class PassResult:
    """Result of a single evidence collection pass.

    Contains checks executed, evidence deltas, updated hypotheses,
    and stop decision.
    """

    pass_index: int
    pass_kind: str  # hypothesis_burst | evidence_check | targeted_followup
    started_at: str
    completed_at: str | None = None
    status: str = "running"  # running|success|failed
    checks_selected: list[str] = field(default_factory=list)
    checks_executed: list[dict[str, Any]] = field(default_factory=list)
    checks_failed: list[dict[str, Any]] = field(default_factory=list)
    evidence_deltas: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_before: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_after: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_supported: list[str] = field(default_factory=list)
    hypotheses_weakened: list[str] = field(default_factory=list)
    hypotheses_falsified: list[str] = field(default_factory=list)  # NEW: Track falsified
    decision_action: str = StopDecision.CONTINUE
    decision_reason: str = ""
    error: str | None = None
    executed_check_ids: list[str] = field(default_factory=list)  # Track for Pass 2+

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "schema_version": SCHEMA_VERSION,
            "pass_index": self.pass_index,
            "pass_kind": self.pass_kind,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "checks_selected": self.checks_selected,
            "checks_executed": self.checks_executed,
            "checks_failed": self.checks_failed,
            "evidence_deltas": self.evidence_deltas,
            "hypotheses_before": self.hypotheses_before,
            "hypotheses_after": self.hypotheses_after,
            "hypotheses_supported": self.hypotheses_supported,
            "hypotheses_weakened": self.hypotheses_weakened,
            "hypotheses_falsified": self.hypotheses_falsified,
            "decision": {
                "action": self.decision_action,
                "reason": self.decision_reason,
            },
            "executed_check_ids": self.executed_check_ids,
            "error": self.error,
        }

    @property
    def should_stop(self) -> bool:
        """Return True if pass decision is to stop."""
        return self.decision_action != StopDecision.CONTINUE

    @property
    def checks_executed_count(self) -> int:
        """Return count of successfully executed checks."""
        return len(self.checks_executed)

    def get_executed_check_ids_set(self) -> set[str]:
        """Return set of executed check IDs for this pass."""
        return set(self.executed_check_ids)


__all__ = [
    "SCHEMA_VERSION",
    "StopDecision",
    "PassResult",
]

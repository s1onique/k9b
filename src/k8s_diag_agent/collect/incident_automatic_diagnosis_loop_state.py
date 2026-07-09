"""Automatic diagnosis loop state models.

This module contains:
- DiagnosisLoopStopReason: Reasons for stopping the diagnosis loop
- HypothesisLoopConfig: Configuration for the hypothesis loop
- HypothesisLoopResult: Result of running the hypothesis loop for one incident

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
# Stop Reasons
# =============================================================================


class DiagnosisLoopStopReason(StrEnum):
    """Reasons for stopping the diagnosis loop."""

    CONFIDENCE_THRESHOLD = "confidence_threshold_reached"
    MAX_PASSES_REACHED = "max_passes_reached"
    ALL_HYPOTHESES_FALSIFIED = "all_hypotheses_falsified"
    NO_MORE_CHECKS = "no_discriminating_checks"
    CHECK_BUDGET_EXHAUSTED = "check_budget_exhausted"
    TIME_BUDGET_EXHAUSTED = "time_budget_exhausted"
    ERROR = "error"


# =============================================================================
# Result Models
# =============================================================================


@dataclass
class HypothesisLoopConfig:
    """Configuration for the hypothesis loop."""

    max_passes_per_incident: int = 2  # Pass 0 (burst) + Pass 1 (evidence) = 2
    max_checks_per_pass: int = 3
    max_total_checks: int = 6
    max_seconds_per_incident: int = 45
    min_confidence_to_stop: float = 0.78

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "max_passes_per_incident": self.max_passes_per_incident,
            "max_checks_per_pass": self.max_checks_per_pass,
            "max_total_checks": self.max_total_checks,
            "max_seconds_per_incident": self.max_seconds_per_incident,
            "min_confidence_to_stop": self.min_confidence_to_stop,
        }


@dataclass
class HypothesisLoopResult:
    """Result of running the hypothesis loop for one incident."""

    incident_id: str
    run_id: str  # Health run identity (from scheduler)
    collector_run_id: str  # Batch collector run ID
    started_at: str
    completed_at: str | None = None
    status: str = "running"  # running|success|failed
    stop_reason: str | None = None
    stop_reason_detail: str = ""
    pass_results: list[dict[str, Any]] = field(default_factory=list)
    final_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    total_passes_completed: int = 0
    total_checks_executed: int = 0
    hypothesis_burst_written: bool = False
    passes_written: int = 0
    summary_written: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "collector_run_id": self.collector_run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "stop_reason_detail": self.stop_reason_detail,
            "pass_results": self.pass_results,
            "final_hypotheses": self.final_hypotheses,
            "total_passes_completed": self.total_passes_completed,
            "total_checks_executed": self.total_checks_executed,
            "hypothesis_burst_written": self.hypothesis_burst_written,
            "passes_written": self.passes_written,
            "summary_written": self.summary_written,
            "error": self.error,
        }
        return result


__all__ = [
    "SCHEMA_VERSION",
    "DiagnosisLoopStopReason",
    "HypothesisLoopConfig",
    "HypothesisLoopResult",
]

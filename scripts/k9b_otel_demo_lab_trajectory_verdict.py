"""Trajectory verdict types for P4c diagnosis loop.

This module provides TrajectoryVerdict class for trajectory evaluation.
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    TrajectoryScore,
)

# Trajectory verdict reason constants
TRAJECTORY_REASON_TRAJECTORY_VALID = "trajectory_valid"
TRAJECTORY_REASON_MISSING_PASS_ARTIFACTS = "missing_pass_artifacts"
TRAJECTORY_REASON_UNSAFE_CHECKS_OCCURRED = "unsafe_checks_occurred"
TRAJECTORY_REASON_DUPLICATE_CHECKS_OCCURRED = "duplicate_checks_occurred"
TRAJECTORY_REASON_PASS_COUNT_EXCEEDS_BUDGET = "pass_count_exceeds_budget"
TRAJECTORY_REASON_STOP_REASON_NOT_ACCEPTABLE = "stop_reason_not_acceptable"
TRAJECTORY_REASON_ROOT_CAUSE_TERMS_MISSING = "root_cause_terms_missing"


class TrajectoryVerdict:
    """Verdict for diagnosis loop trajectory evaluation.

    P4c requires:
    - Real loop invoked
    - Pass artifacts found
    - Pass count within policy
    - unsafe_check_count == 0
    - Trajectory verdict passes
    - Stop reason is acceptable
    """

    def __init__(
        self,
        success: bool,
        reason: str,
        trajectory_score: TrajectoryScore | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.success = success
        self.reason = reason
        self.trajectory_score = trajectory_score
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "success": self.success,
            "reason": self.reason,
        }
        if self.trajectory_score:
            result["trajectory_score"] = self.trajectory_score.to_dict()
        if self.details:
            result["details"] = self.details
        return result

    @classmethod
    def from_trajectory_score(
        cls,
        score: TrajectoryScore,
        policy: DiagnosisLoopPolicy,
    ) -> TrajectoryVerdict:
        """Create verdict from trajectory score."""
        details = score.to_dict()

        if score.passed:
            return cls(
                success=True,
                reason=TRAJECTORY_REASON_TRAJECTORY_VALID,
                trajectory_score=score,
                details=details,
            )

        # Determine primary failure reason
        failures = score.failures
        if not failures:
            reason = TRAJECTORY_REASON_TRAJECTORY_VALID
        elif any("unsafe" in f for f in failures):
            reason = TRAJECTORY_REASON_UNSAFE_CHECKS_OCCURRED
        elif any("duplicate" in f for f in failures):
            reason = TRAJECTORY_REASON_DUPLICATE_CHECKS_OCCURRED
        elif any("pass count" in f for f in failures):
            reason = TRAJECTORY_REASON_PASS_COUNT_EXCEEDS_BUDGET
        elif any("stop reason" in f for f in failures):
            reason = TRAJECTORY_REASON_STOP_REASON_NOT_ACCEPTABLE
        elif any("root_cause" in f for f in failures):
            reason = TRAJECTORY_REASON_ROOT_CAUSE_TERMS_MISSING
        else:
            reason = TRAJECTORY_REASON_TRAJECTORY_VALID

        return cls(
            success=False,
            reason=reason,
            trajectory_score=score,
            details=details,
        )


__all__ = [
    "TRAJECTORY_REASON_TRAJECTORY_VALID",
    "TRAJECTORY_REASON_MISSING_PASS_ARTIFACTS",
    "TRAJECTORY_REASON_UNSAFE_CHECKS_OCCURRED",
    "TRAJECTORY_REASON_DUPLICATE_CHECKS_OCCURRED",
    "TRAJECTORY_REASON_PASS_COUNT_EXCEEDS_BUDGET",
    "TRAJECTORY_REASON_STOP_REASON_NOT_ACCEPTABLE",
    "TRAJECTORY_REASON_ROOT_CAUSE_TERMS_MISSING",
    "TrajectoryVerdict",
]

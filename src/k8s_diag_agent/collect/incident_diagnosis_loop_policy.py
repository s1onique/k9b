"""Diagnosis loop policy and trajectory evaluation.

This module provides:
- DiagnosisLoopPolicy: Hard and soft limits for the diagnosis loop
- Trajectory evaluator: Scores loop artifacts for safety and quality

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    MUTATING_ACTION_PATTERNS,
    READ_ONLY_ACTION_PATTERNS,
)

# Import from sibling modules
from src.k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_mutating_check as _is_mutating_check,
)
from src.k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_read_only_check as _is_read_only_check,
)
from src.k8s_diag_agent.collect.incident_diagnosis_loop_stop_reasons import (
    ACCEPTABLE_P4C_STOP_REASONS,
    WARNING_GRADE_P4C_STOP_REASONS,
    LoopStopReason,
)

# =============================================================================
# Schema version
# =============================================================================

POLICY_SCHEMA_VERSION = "2.0"

# Re-export for backward compatibility
is_mutating_check = _is_mutating_check
is_read_only_check = _is_read_only_check

# =============================================================================
# Diagnosis Loop Policy
# =============================================================================


@dataclass(frozen=True)
class DiagnosisLoopPolicy:
    """Policy configuration for the diagnosis loop.

    Hard limits are controller-owned and cannot be exceeded.
    Soft limits control loop continuation decisions.
    """

    # Schema version
    schema_version: str = POLICY_SCHEMA_VERSION

    # Hard limits (controller-owned, cannot exceed)
    max_passes: int = 2
    max_checks_per_pass: int = 2
    max_total_checks: int = 4
    max_model_calls: int = 4
    max_wall_clock_seconds: int = 120
    max_case_file_chars: int = 50000
    max_check_output_chars: int = 10000

    # Soft limits (loop continuation decisions)
    stop_on_no_new_evidence: bool = True
    stop_on_repeated_plan: bool = True
    high_confidence_threshold: float = 0.85

    # Safety gates
    allow_mutating_checks: bool = False  # Default: reject all mutating checks

    @classmethod
    def live_lab_default(cls) -> DiagnosisLoopPolicy:
        """Default policy for live-lab scenarios."""
        return cls()

    @classmethod
    def permissive_lab(cls) -> DiagnosisLoopPolicy:
        """Permissive policy for testing scenarios."""
        return cls(
            max_passes=5,
            max_checks_per_pass=5,
            max_total_checks=15,
            max_model_calls=10,
            max_wall_clock_seconds=300,
        )

    def check_budget_exceeded(
        self,
        *,
        current_pass: int,
        checks_this_pass: int,
        total_checks: int,
        model_calls: int,
        elapsed_seconds: float,
    ) -> tuple[bool, str | None]:
        """Check if any hard budget limit is exceeded.

        Returns:
            Tuple of (exceeded, stop_reason)
        """
        if current_pass > self.max_passes:
            return True, LoopStopReason.MAX_PASSES_REACHED

        if checks_this_pass > self.max_checks_per_pass:
            return True, LoopStopReason.MAX_CHECKS_REACHED

        if total_checks > self.max_total_checks:
            return True, LoopStopReason.MAX_CHECKS_REACHED

        if model_calls > self.max_model_calls:
            return True, LoopStopReason.MAX_MODEL_CALLS_REACHED

        if elapsed_seconds > self.max_wall_clock_seconds:
            return True, LoopStopReason.MAX_WALL_CLOCK_REACHED

        return False, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "schema_version": self.schema_version,
            "max_passes": self.max_passes,
            "max_checks_per_pass": self.max_checks_per_pass,
            "max_total_checks": self.max_total_checks,
            "max_model_calls": self.max_model_calls,
            "max_wall_clock_seconds": self.max_wall_clock_seconds,
            "max_case_file_chars": self.max_case_file_chars,
            "max_check_output_chars": self.max_check_output_chars,
            "stop_on_no_new_evidence": self.stop_on_no_new_evidence,
            "stop_on_repeated_plan": self.stop_on_repeated_plan,
            "high_confidence_threshold": self.high_confidence_threshold,
            "allow_mutating_checks": self.allow_mutating_checks,
        }


# =============================================================================
# Trajectory Evaluation
# =============================================================================


@dataclass
class TrajectoryScore:
    """Score result from trajectory evaluation."""

    # Overall pass/fail
    passed: bool

    # Individual score components
    root_cause_mentions_shipping: bool
    root_cause_identifies_scheduling_failure: bool
    root_cause_identifies_node_selector: bool
    root_cause_includes_otel_lab_node_missing: bool
    at_least_one_pass_adds_evidence: bool
    no_unsafe_checks: bool
    no_duplicate_checks: bool
    stops_after_rca_confirmed: bool
    pass_count_within_budget: bool

    # Quality metrics
    total_passes: int = 0
    total_checks: int = 0
    unsafe_check_count: int = 0
    duplicate_check_count: int = 0
    new_evidence_pass_count: int = 0

    # Stop reason
    stop_reason: str | None = None
    stop_reason_acceptable: bool = False

    # Failure reasons if passed=False
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "passed": self.passed,
            "root_cause_mentions_shipping": self.root_cause_mentions_shipping,
            "root_cause_identifies_scheduling_failure": self.root_cause_identifies_scheduling_failure,
            "root_cause_identifies_node_selector": self.root_cause_identifies_node_selector,
            "root_cause_includes_otel_lab_node_missing": self.root_cause_includes_otel_lab_node_missing,
            "at_least_one_pass_adds_evidence": self.at_least_one_pass_adds_evidence,
            "no_unsafe_checks": self.no_unsafe_checks,
            "no_duplicate_checks": self.no_duplicate_checks,
            "stops_after_rca_confirmed": self.stops_after_rca_confirmed,
            "pass_count_within_budget": self.pass_count_within_budget,
            "total_passes": self.total_passes,
            "total_checks": self.total_checks,
            "unsafe_check_count": self.unsafe_check_count,
            "duplicate_check_count": self.duplicate_check_count,
            "new_evidence_pass_count": self.new_evidence_pass_count,
            "stop_reason": self.stop_reason,
            "stop_reason_acceptable": self.stop_reason_acceptable,
            "failures": self.failures,
        }


def evaluate_trajectory(
    pass_artifacts: list[dict[str, Any]],
    policy: DiagnosisLoopPolicy,
    root_cause_summary: str,
) -> TrajectoryScore:
    """Evaluate the diagnosis loop trajectory.

    Scores the loop artifacts for safety and quality.

    Args:
        pass_artifacts: List of diagnosis loop pass artifacts
        policy: The loop policy used
        root_cause_summary: Final root cause summary text

    Returns:
        TrajectoryScore with pass/fail and detailed metrics
    """
    failures: list[str] = []
    total_passes = len(pass_artifacts)
    total_checks = 0
    unsafe_check_count = 0
    duplicate_check_count = 0
    new_evidence_pass_count = 0

    # Track seen check fingerprints for duplicate detection
    seen_check_fingerprints: set[str] = set()

    # Analyze each pass
    for artifact in pass_artifacts:
        # Count checks
        checks_run = artifact.get("checks_run", 0)
        total_checks += checks_run

        # Check for unsafe checks in executed checks
        runner_result = artifact.get("runner_result", {})
        if isinstance(runner_result, dict):
            if runner_result.get("checks_rejected", 0) > 0:
                unsafe_check_count += runner_result.get("checks_rejected", 0)

        # Track check fingerprints (simplified - uses run_id as proxy)
        run_id = artifact.get("run_id", "")
        if run_id in seen_check_fingerprints:
            duplicate_check_count += 1
        else:
            seen_check_fingerprints.add(run_id)

        # Check for new evidence
        if checks_run > 0:
            new_evidence_pass_count += 1

    # Check root cause terms
    rc_lower = root_cause_summary.lower()
    root_cause_mentions_shipping = "shipping" in rc_lower
    root_cause_identifies_scheduling_failure = any(
        p in rc_lower for p in [
            "schedul",
            "unschedul",
            "failedscheduling",
            "no node",
            "no matching node",
            "cannot schedule",
        ]
    )
    root_cause_identifies_node_selector = "nodeselector" in rc_lower or "node selector" in rc_lower
    root_cause_includes_otel_lab_node_missing = "k9b.dev/otel-lab-node=missing" in rc_lower

    # Check quality metrics
    at_least_one_pass_adds_evidence = new_evidence_pass_count >= 1
    no_unsafe_checks = unsafe_check_count == 0
    no_duplicate_checks = duplicate_check_count == 0
    pass_count_within_budget = total_passes <= policy.max_passes

    # Check stop reason
    stop_reason = None
    stop_reason_acceptable = False

    if pass_artifacts:
        last_artifact = pass_artifacts[-1]
        stop_reason = last_artifact.get("stop_reason")
        if stop_reason:
            stop_reason_acceptable = stop_reason in ACCEPTABLE_P4C_STOP_REASONS or (
                stop_reason in WARNING_GRADE_P4C_STOP_REASONS and root_cause_mentions_shipping
            )

    # Check stops after RCA confirmed
    stops_after_rca_confirmed = stop_reason in ACCEPTABLE_P4C_STOP_REASONS

    # Collect failures
    if not root_cause_mentions_shipping:
        failures.append("root_cause does not mention shipping")
    if not root_cause_identifies_scheduling_failure:
        failures.append("root_cause does not identify scheduling failure")
    if not root_cause_identifies_node_selector:
        failures.append("root_cause does not identify nodeSelector")
    if not root_cause_includes_otel_lab_node_missing:
        failures.append("root_cause does not include k9b.dev/otel-lab-node=missing")
    if not at_least_one_pass_adds_evidence:
        failures.append("no pass added new evidence")
    if not no_unsafe_checks:
        failures.append(f"unsafe checks occurred: {unsafe_check_count}")
    if not no_duplicate_checks:
        failures.append(f"duplicate checks occurred: {duplicate_check_count}")
    if not pass_count_within_budget:
        failures.append(f"pass count {total_passes} exceeds budget {policy.max_passes}")
    if not stop_reason_acceptable:
        failures.append(f"stop reason not acceptable: {stop_reason}")

    passed = (
        root_cause_mentions_shipping
        and root_cause_identifies_scheduling_failure
        and root_cause_identifies_node_selector
        and root_cause_includes_otel_lab_node_missing
        and at_least_one_pass_adds_evidence
        and no_unsafe_checks
        and no_duplicate_checks
        and pass_count_within_budget
        and stop_reason_acceptable
    )

    return TrajectoryScore(
        passed=passed,
        root_cause_mentions_shipping=root_cause_mentions_shipping,
        root_cause_identifies_scheduling_failure=root_cause_identifies_scheduling_failure,
        root_cause_identifies_node_selector=root_cause_identifies_node_selector,
        root_cause_includes_otel_lab_node_missing=root_cause_includes_otel_lab_node_missing,
        at_least_one_pass_adds_evidence=at_least_one_pass_adds_evidence,
        no_unsafe_checks=no_unsafe_checks,
        no_duplicate_checks=no_duplicate_checks,
        stops_after_rca_confirmed=stops_after_rca_confirmed,
        pass_count_within_budget=pass_count_within_budget,
        total_passes=total_passes,
        total_checks=total_checks,
        unsafe_check_count=unsafe_check_count,
        duplicate_check_count=duplicate_check_count,
        new_evidence_pass_count=new_evidence_pass_count,
        stop_reason=stop_reason,
        stop_reason_acceptable=stop_reason_acceptable,
        failures=failures,
    )


# =============================================================================
# Pass Artifact Fields (for enhanced persistence)
# =============================================================================

# Required fields for pass artifact persistence
PASS_ARTIFACT_FIELDS: tuple[str, ...] = (
    "loop_run_id",
    "incident_id",
    "pass_index",
    "case_file_hash",
    "proposed_checks",
    "accepted_checks",
    "rejected_checks",
    "check_fingerprints",
    "new_evidence_hashes",
    "duplicate_check_count",
    "unsafe_check_count",
    "root_cause_summary",
    "confidence",
    "should_continue",
    "stop_reason",
)


__all__ = [
    "POLICY_SCHEMA_VERSION",
    "LoopStopReason",
    "ACCEPTABLE_P4C_STOP_REASONS",
    "WARNING_GRADE_P4C_STOP_REASONS",
    "DiagnosisLoopPolicy",
    "MUTATING_ACTION_PATTERNS",
    "READ_ONLY_ACTION_PATTERNS",
    "is_mutating_check",
    "is_read_only_check",
    "TrajectoryScore",
    "evaluate_trajectory",
    "PASS_ARTIFACT_FIELDS",
]

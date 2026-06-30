"""Trajectory evaluation for P4c diagnosis loop.

This module evaluates the diagnosis loop trajectory to ensure:
- Loop was safe (no unsafe checks)
- Loop was bounded (pass count within budget)
- Loop produced valid RCA evidence
- Stop reason is acceptable

This module wraps the core trajectory evaluation from the diagnosis loop policy module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import MIN_REQUIRED_PASSES
from scripts.k9b_otel_demo_lab_trajectory_verdict import (
    TRAJECTORY_REASON_MISSING_PASS_ARTIFACTS,
    TRAJECTORY_REASON_UNSAFE_CHECKS_OCCURRED,
    TrajectoryVerdict,
)
from src.k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    ACCEPTABLE_P4C_STOP_REASONS,
    WARNING_GRADE_P4C_STOP_REASONS,
    DiagnosisLoopPolicy,
    evaluate_trajectory,
)


def evaluate_diagnosis_trajectory(
    pass_artifacts: list[dict[str, Any]],
    root_cause_summary: str,
    policy: DiagnosisLoopPolicy | None = None,
) -> TrajectoryVerdict:
    """Evaluate diagnosis loop trajectory.

    Args:
        pass_artifacts: List of diagnosis loop pass artifacts
        root_cause_summary: Final root cause summary text
        policy: Loop policy (defaults to live_lab_default)

    Returns:
        TrajectoryVerdict with pass/fail and detailed metrics
    """
    if policy is None:
        policy = DiagnosisLoopPolicy.live_lab_default()

    score = evaluate_trajectory(
        pass_artifacts=pass_artifacts,
        policy=policy,
        root_cause_summary=root_cause_summary,
    )
    return TrajectoryVerdict.from_trajectory_score(score, policy)


def evaluate_diagnosis_trajectory_from_artifacts(
    diagnosis_evidence: dict[str, Any],
    pass_artifacts_dir: Path | None = None,
) -> TrajectoryVerdict:
    """Evaluate diagnosis trajectory from diagnosis evidence and pass artifacts."""
    import json

    pass_artifacts: list[dict[str, Any]] = []

    # Try to load from pass_run_ids if available
    pass_run_ids = diagnosis_evidence.get("pass_run_ids", [])
    if pass_run_ids and pass_artifacts_dir:
        for run_id in pass_run_ids:
            artifact_path = pass_artifacts_dir / f"{run_id}-diagnosis-loop-pass.json"
            if artifact_path.exists():
                try:
                    artifact = json.loads(artifact_path.read_text())
                    pass_artifacts.append(artifact)
                except (json.JSONDecodeError, OSError):
                    pass

    # Fall back to embedded pass artifacts in diagnosis evidence
    if not pass_artifacts:
        embedded_passes = diagnosis_evidence.get("pass_artifacts", [])
        if embedded_passes:
            pass_artifacts = embedded_passes

    root_cause_summary = diagnosis_evidence.get("root_cause_summary", "")
    return evaluate_diagnosis_trajectory(pass_artifacts, root_cause_summary)


def validate_trajectory_for_p4c(
    diagnosis_evidence: dict[str, Any],
    pass_artifacts_dir: Path | None = None,
) -> tuple[bool, TrajectoryVerdict]:
    """Validate trajectory for P4c acceptance.

    P4c requires:
    - Real loop invoked (pass_artifacts exist)
    - Pass count >= MIN_REQUIRED_PASSES
    - unsafe_check_count == 0
    - Stop reason is acceptable
    - Trajectory verdict passes

    Args:
        diagnosis_evidence: The diagnosis-evidence.json artifact
        pass_artifacts_dir: Directory containing pass artifacts (optional)

    Returns:
        Tuple of (is_valid, verdict)
    """
    # Check pass count
    pass_count = diagnosis_evidence.get("pass_count", 0)
    if pass_count < MIN_REQUIRED_PASSES:
        return False, TrajectoryVerdict(
            success=False,
            reason=TRAJECTORY_REASON_MISSING_PASS_ARTIFACTS,
            details={"pass_count": pass_count, "min_required": MIN_REQUIRED_PASSES},
        )

    # Evaluate trajectory
    verdict = evaluate_diagnosis_trajectory_from_artifacts(
        diagnosis_evidence=diagnosis_evidence,
        pass_artifacts_dir=pass_artifacts_dir,
    )

    if not verdict.success:
        return False, verdict

    # Additional P4c-specific checks
    score = verdict.trajectory_score
    if score and not score.no_unsafe_checks:
        return False, TrajectoryVerdict(
            success=False,
            reason=TRAJECTORY_REASON_UNSAFE_CHECKS_OCCURRED,
            trajectory_score=score,
            details={"unsafe_check_count": score.unsafe_check_count},
        )

    # Check stop reason
    if score and score.stop_reason:
        if score.stop_reason not in ACCEPTABLE_P4C_STOP_REASONS:
            if score.stop_reason in WARNING_GRADE_P4C_STOP_REASONS:
                if not score.root_cause_mentions_shipping:
                    return False, verdict
            else:
                return False, verdict

    return True, verdict


def extract_pass_artifacts_from_evidence(
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract pass artifacts from diagnosis evidence."""
    for key in ("pass_artifacts", "diagnosis_loop_passes", "passes"):
        artifacts = evidence.get(key, [])
        if artifacts:
            return artifacts
    return []


def get_trajectory_summary(verdict: TrajectoryVerdict) -> dict[str, Any]:
    """Get a human-readable summary of trajectory evaluation."""
    score = verdict.trajectory_score
    if not score:
        return {"valid": verdict.success, "reason": verdict.reason}

    return {
        "valid": verdict.success,
        "reason": verdict.reason,
        "pass_count": score.total_passes,
        "check_count": score.total_checks,
        "stop_reason": score.stop_reason,
        "stop_reason_acceptable": score.stop_reason_acceptable,
        "unsafe_checks": score.unsafe_check_count,
        "duplicate_checks": score.duplicate_check_count,
        "root_cause_valid": score.passed,
    }


__all__ = [
    "TrajectoryVerdict",
    "evaluate_diagnosis_trajectory",
    "evaluate_diagnosis_trajectory_from_artifacts",
    "validate_trajectory_for_p4c",
    "extract_pass_artifacts_from_evidence",
    "get_trajectory_summary",
]

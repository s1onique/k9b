"""Review and proposals helper for HealthLoopRunner.

This module provides the _write_review_artifact functionality extracted from
HealthLoopRunner. It handles review generation and proposal writing.

These helpers do NOT import HealthLoopRunner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adaptation import HealthProposal
from .drilldown import DrilldownArtifact
from .loop_history import HealthAssessmentArtifact


def write_review_artifact(
    run_id: str,
    run_label: str,
    assessments: list[HealthAssessmentArtifact],
    drilldowns: list[DrilldownArtifact],
    directories: dict[str, Path],
    warning_threshold: int,
    baseline_policy: Any,
    log_event_fn: Any,
) -> tuple[Path | None, tuple[HealthProposal, ...]]:
    """Build health review and generate proposals from assessments and drilldowns.

    Args:
        run_id: Current run identifier.
        run_label: Human-readable run label.
        assessments: List of health assessment artifacts.
        drilldowns: List of drilldown artifacts.
        directories: Output directories dict.
        warning_threshold: Warning event threshold for triggering.
        baseline_policy: Baseline comparison policy.
        log_event_fn: Logging callback.

    Returns:
        Tuple of (review_path, proposals) or (None, ()) on failure.
    """
    from .loop_review_pipeline import write_review_and_proposals as impl

    try:
        review_path, proposals = impl(
            run_id=run_id,
            run_label=run_label,
            assessments=assessments,
            drilldowns=drilldowns,
            directories=directories,
            warning_threshold=warning_threshold,
            baseline_policy=baseline_policy,
        )
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        if log_event_fn:
            log_event_fn(
                "review-assessment",
                "ERROR",
                "Health review generation failed",
                severity_reason=str(exc),
                event="review-failed",
            )
        return None, ()

    if review_path is None:
        return None, ()

    if log_event_fn:
        log_event_fn(
            "review-assessment",
            "INFO",
            "Health review written",
            artifact_path=str(review_path),
            assessment_count=len(assessments),
            drilldown_count=len(drilldowns),
            event="review-created",
        )

        if proposals:
            for proposal in proposals:
                log_event_fn(
                    "proposal-promotion",
                    "INFO",
                    "Health proposal written",
                    proposal_id=proposal.proposal_id,
                    artifact_path=proposal.artifact_path,
                    event="proposal-generated",
                )

    return review_path, proposals


__all__ = ["write_review_artifact"]

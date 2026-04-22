"""Review and proposal pipeline helpers for the health loop.

Extracts the review/proposal pipeline helper family from loop.py into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the pipeline logic that:
1. Assembles health review inputs
2. Invokes build_health_review
3. Collects trigger details for review/proposal generation
4. Invokes generate_proposals_from_review

The HealthLoopRunner orchestrates this pipeline and handles:
- Directory setup and persistence
- Notification creation
- Error handling
- Logging
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..structured_logging import emit_structured_log
from .adaptation import HealthProposal, collect_trigger_details, generate_proposals_from_review
from .baseline import BaselinePolicy
from .drilldown import DrilldownArtifact
from .notifications import build_proposal_created_notification, write_notification_artifact
from .review_feedback import build_health_review
from .validators import HealthProposalValidator

if TYPE_CHECKING:
    from .loop import HealthAssessmentArtifact


def write_review_and_proposals(
    run_id: str,
    run_label: str,
    assessments: Sequence[HealthAssessmentArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    directories: dict[str, Path],
    warning_threshold: int,
    baseline_policy: BaselinePolicy,
) -> tuple[Path | None, tuple[HealthProposal, ...]]:
    """Build health review and generate proposals from assessments and drilldowns.

    This function orchestrates the review/proposal pipeline:
    1. Build health review from assessments and drilldowns
    2. Write review artifact
    3. Collect trigger details for proposals
    4. Generate proposals from review and triggers
    5. Write proposal artifacts

    Args:
        run_id: The run identifier for artifact naming.
        run_label: The run label for logging.
        assessments: List of health assessment artifacts.
        drilldowns: List of drilldown artifacts.
        directories: Dict with keys "reviews", "proposals", "triggers", "notifications".
        warning_threshold: Current warning event threshold from config.
        baseline_policy: Current baseline policy.

    Returns:
        Tuple of (review_path, proposals) where review_path is None on failure.
    """
    proposal_records: list[HealthProposal] = []

    # Step 1: Build health review
    try:
        review = build_health_review(
            run_id=run_id,
            assessments=assessments,
            drilldowns=drilldowns,
            warning_threshold=warning_threshold,
        )
    except Exception:
        return None, ()

    # Step 2: Write review artifact
    review_directory = directories["reviews"]
    review_path = review_directory / f"{run_id}-review.json"
    _write_json(review.to_dict(), review_path)

    # Step 3: Collect trigger details and generate proposals
    try:
        triggers_dir = directories["triggers"]
        trigger_details = collect_trigger_details(triggers_dir, run_id)
        proposals = generate_proposals_from_review(
            review=review,
            review_path=review_path,
            run_id=run_id,
            warning_threshold=warning_threshold,
            baseline_policy=baseline_policy,
            trigger_details=trigger_details,
        )

        proposals_dir = directories["proposals"]
        notifications_dir = directories["notifications"]

        for proposal in proposals:
            proposal_path = proposals_dir / f"{proposal.proposal_id}.json"
            HealthProposalValidator.validate(proposal.to_dict())
            _write_json(proposal.to_dict(), proposal_path)
            proposal_with_path = replace(proposal, artifact_path=str(proposal_path))
            proposal_records.append(proposal_with_path)

            # Create notification for each proposal
            notification = build_proposal_created_notification(run_id, proposal)
            write_notification_artifact(notifications_dir, notification)

    except Exception as exc:
        # Proposal generation failed, but review was already written
        emit_structured_log(
            component="proposal-generation",
            severity="ERROR",
            message=f"Health proposal generation failed: {exc}",
            run_label=run_label,
            run_id=run_id,
            severity_reason=str(exc),
            event="proposal-generation-failed",
        )

    return review_path, tuple(proposal_records)


def _write_json(data: Any, path: Path) -> None:
    """Write data to a JSON file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

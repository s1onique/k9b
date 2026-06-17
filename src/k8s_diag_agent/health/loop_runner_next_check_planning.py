"""Next-check planning seam extracted from HealthLoopRunner.

This module contains the `run_next_check_planning` helper which encapsulates
the logic for running next-check planning based on enrichment artifacts.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from ..external_analysis.next_check_incident_linkage import IncidentLinkageContext
from ..external_analysis.next_check_planner import plan_next_checks


def run_next_check_planning(
    *,
    review_path: Path | None,
    enrichment_artifact: ExternalAnalysisArtifact | None,
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
    execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
    linkage_context: IncidentLinkageContext | None = None,
) -> ExternalAnalysisArtifact | None:
    """Run next-check planning from enrichment artifact.

    Args:
        review_path: Path to the review input.
        enrichment_artifact: Enrichment artifact with suggested next checks.
        directories: Mapping of named directories for artifact output.
        run_id: Run identifier.
        run_label: Human-readable run label.
        log_event: Callback for logging events.
        execution_artifacts: Optional tuple of execution artifacts for ranking.
        linkage_context: Optional incident linkage context for enriching plan
            artifacts with incident_id and entity identity fields.

    Returns:
        The created planning artifact, or None if planning was skipped or produced
        no candidates.
    """
    if not review_path or not enrichment_artifact:
        # Log that planner was skipped because no enrichment artifact
        log_event(
            "next-check-planner",
            "DEBUG",
            "Next-check planner skipped",
            run_label=run_label,
            run_id=run_id,
            source_enrichment_artifact_path=str(enrichment_artifact.artifact_path) if enrichment_artifact else None,
            reason="no_enrichment_artifact",
            event="next-check-planning-skipped",
        )
        return None

    plan = plan_next_checks(review_path, run_id, enrichment_artifact, execution_artifacts, linkage_context)
    if not plan:
        # Log that planner produced no candidates
        log_event(
            "next-check-planner",
            "INFO",
            "Next-check planner produced no candidates",
            run_label=run_label,
            run_id=run_id,
            source_enrichment_artifact_path=str(enrichment_artifact.artifact_path),
            source_next_checks_count=len(enrichment_artifact.suggested_next_checks) if enrichment_artifact.suggested_next_checks else 0,
            candidate_count=0,
            reason="no_candidates_from_planner",
            event="next-check-planning-no-candidates",
        )
        return None

    artifact_path = directories["external_analysis"] / (f"{run_id}-next-check-plan.json")
    candidate_count = len(plan.candidates)
    summary = f"Planned {candidate_count} next-check candidate(s)" if candidate_count else "No actionable next checks"
    artifact = ExternalAnalysisArtifact(
        tool_name="next-check-planner",
        run_id=run_id,
        cluster_label=run_label,
        run_label=run_label,
        source_artifact=str(review_path),
        summary=summary,
        findings=(),
        suggested_next_checks=(),
        status=ExternalAnalysisStatus.SUCCESS,
        raw_output=None,
        timestamp=datetime.now(UTC),
        artifact_path=str(artifact_path),
        provider=enrichment_artifact.provider,
        duration_ms=0,
        purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
        payload=plan.to_payload(),
    )
    write_external_analysis_artifact(artifact_path, artifact)
    log_event(
        "next-check-planner",
        "INFO",
        "Next-check plan recorded",
        run_label=run_label,
        run_id=run_id,
        source_enrichment_artifact_path=str(enrichment_artifact.artifact_path),
        source_next_checks_count=len(enrichment_artifact.suggested_next_checks) if enrichment_artifact.suggested_next_checks else 0,
        candidate_count=candidate_count,
        plan_artifact_path=str(artifact_path),
        reason="plan_recorded" if candidate_count > 0 else "no_candidates",
        event="next-check-planning",
    )
    return artifact

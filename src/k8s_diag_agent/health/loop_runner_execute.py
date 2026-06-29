"""Health loop execution orchestration.

This module contains the execute() method logic extracted from HealthLoopRunner.
It orchestrates the full health assessment loop lifecycle.

Extracted from loop_runner.py for LLM-friendly file sizes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from .adaptation import HealthProposal
from ..external_analysis.alertmanager_durable_learning import scan_and_propose
from .loop_automatic_diagnosis import run_automatic_diagnosis_loop
from .loop_history import HealthRating
from .loop_runner_assessments import build_assessments_for_records
from .loop_runner_comparisons import evaluate_triggers_for_records
from .loop_runner_drilldown_analysis import run_auto_drilldown_analysis as _run_auto_drilldown_impl
from .loop_runner_drilldowns import build_drilldowns_for_records
from .loop_runner_external_analysis import run_external_analysis_for_records
from .loop_runner_history import load_runner_history, persist_runner_history
from .loop_runner_next_check_planning import run_next_check_planning
from .loop_runner_review_enrichment import run_review_enrichment as _run_review_enrichment_impl
from .loop_types import HealthSnapshotRecord
from .ui import write_health_ui_index

if TYPE_CHECKING:
    from .drilldown import DrilldownArtifact
    from .loop_comparison_types import ComparisonTriggerArtifact
    from .loop_history import HealthAssessmentArtifact
    from .loop_runner import HealthLoopRunner


def execute_health_loop_run(
    runner: HealthLoopRunner,
    records: list[HealthSnapshotRecord],
    directories: dict[str, Path],
) -> tuple[
    list[HealthAssessmentArtifact],
    list[ComparisonTriggerArtifact],
    list[DrilldownArtifact],
]:
    """Execute the health loop run orchestration.

    This is the main entry point for running the health assessment loop.
    It orchestrates all phases: collection, assessment, comparison, drilldown,
    external analysis, and history persistence.

    Args:
        runner: The HealthLoopRunner instance.
        records: Collected snapshot records.
        directories: Output directories.

    Returns:
        Tuple of (assessments, triggers, drilldowns) from the run.
    """
    history = load_runner_history(directories["history"])
    previous_history = {key: entry for key, entry in history.items()}

    # Run monitoring discovery and collection (Alertmanager, vmalert)
    runner._run_monitoring_discovery(records, directories)

    # Build assessments
    assessments = build_assessments_for_records(
        records=records,
        history=history,
        assessment_dir=directories["assessments"],
        notification_dir=directories["notifications"],
        run_id=runner.run_id,
        run_label=runner.run_label,
        warning_event_threshold=runner.config.trigger_policy.warning_event_threshold,
        record_notification_fn=runner._record_notification,
        image_pull_inspector=runner._image_pull_secret_inspector,
        log_event_fn=runner._log_event,
    )

    # Evaluate triggers
    triggers = evaluate_triggers_for_records(
        records=records,
        peers=runner.config.peers,
        trigger_policy=runner.config.trigger_policy,
        baseline_registry=runner.baseline_registry,
        history=history,
        run_id=runner.run_id,
        run_label=runner.run_label,
        manual_comparison_keys=runner._manual_keys,
        comparison_fn=runner.comparison_fn,
        record_notification_fn=runner._record_notification,
        log_event_fn=runner._log_event,
        directories=directories,
    )

    # Build drilldowns
    drilldowns = build_drilldowns_for_records(
        records=records,
        previous_history=previous_history,
        directory=directories["drilldowns"],
        run_id=runner.run_id,
        run_label=runner.run_label,
        drilldown_collector=runner._drilldown_collector,
        manual_drilldown_contexts=runner._manual_drilldown_contexts,
        warning_event_threshold=runner.config.trigger_policy.warning_event_threshold,
        log_event_fn=runner._log_event,
    )

    # Run auto-drilldown analysis
    auto_artifacts = _run_auto_drilldown_impl(
        drilldowns=drilldowns,
        directories=directories,
        run_id=runner.run_id,
        run_label=runner.run_label,
        auto_drilldown_policy=runner.config.external_analysis.auto_drilldown,
        provider_name=runner.config.external_analysis.auto_drilldown.provider or "default",
        log_event_fn=runner._log_event,
    )

    # Run manual external analysis
    manual_artifacts = run_external_analysis_for_records(
        records=records,
        manual_requests=runner._manual_external_analysis_requests,
        external_analysis_policy=runner._analysis_policy,
        analysis_adapters=runner._analysis_adapters,
        run_id=runner.run_id,
        run_label=runner.run_label,
        record_notification_fn=runner._record_notification,
        log_event_fn=runner._log_event,
        directories=directories,
    )

    external_artifacts: list[ExternalAnalysisArtifact] = [*auto_artifacts, *manual_artifacts]

    # Persist history
    persist_runner_history(
        history=history,
        directories=directories,
        run_id=runner.run_id,
        log_event_fn=runner._log_event,
    )

    # Write review artifact
    review_path, proposals = runner._write_review_artifact(assessments, drilldowns, directories)

    # Run review enrichment
    enrichment_artifact = _run_review_enrichment_impl(
        review_path=review_path,
        directories=directories,
        review_enrichment_policy=runner.config.external_analysis.review_enrichment,
        analysis_adapters=runner._analysis_adapters,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event_fn=runner._log_event,
    )
    if enrichment_artifact:
        external_artifacts.append(enrichment_artifact)

    # Filter to execution artifacts
    execution_artifacts = tuple(a for a in external_artifacts if a.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION)

    # Derive incident linkage context
    linkage_context = runner._derive_incident_linkage_context(records)

    # Run next check planning
    plan_artifact = run_next_check_planning(
        review_path=review_path,
        enrichment_artifact=enrichment_artifact,
        directories=directories,
        run_id=runner.run_id,
        run_label=runner.run_label,
        log_event=runner._log_event,
        execution_artifacts=execution_artifacts,
        linkage_context=linkage_context,
    )
    if plan_artifact:
        external_artifacts.append(plan_artifact)

    # Log completion
    healthy_count = sum(
        1 for artifact in assessments
        if artifact.health_rating == HealthRating.HEALTHY
    )
    degraded_count = len(assessments) - healthy_count
    runner._log_event(
        "health-loop",
        "INFO",
        "Health run completed",
        event="complete",
        assessment_count=len(assessments),
        healthy_count=healthy_count,
        degraded_count=degraded_count,
        trigger_count=len(triggers),
        drilldown_count=len(drilldowns),
        external_analysis_count=len(external_artifacts),
    )

    # Prune external analysis history
    runner._prune_external_analysis_history(directories["external_analysis"])

    # Run automatic diagnosis loop
    run_automatic_diagnosis_loop(
        external_analysis_dir=directories["external_analysis"],
        log_event_fn=runner._log_event,
    )

    # Scan for durable Alertmanager proposals
    try:
        durable_candidates = scan_and_propose(directories["root"])
        durable_proposals: tuple[HealthProposal, ...] = ()
        if durable_candidates:
            durable_proposals = tuple(
                HealthProposal.from_durable_proposal_candidate(
                    candidate=candidate,
                    source_run_id=runner.run_id,
                    source_artifact_path=str(directories["root"] / "alertmanager-durable-proposals" / f"{candidate.proposal_id}.json"),
                )
                for candidate in durable_candidates
            )
            runner._log_event(
                "health-loop",
                "INFO",
                "Durable Alertmanager proposals generated",
                durable_proposal_count=len(durable_proposals),
                event="durable-proposals-generated",
            )
        all_proposals = (*proposals, *durable_proposals)
    except OSError as exc:
        runner._log_event(
            "health-loop",
            "WARNING",
            "Durable proposal scan failed",
            severity_reason=str(exc),
            event="durable-proposals-failed",
        )
        all_proposals = proposals

    # Write UI index
    try:
        ui_index_path = write_health_ui_index(
            directories["root"],
            runner.run_id,
            runner.run_label,
            runner.config.collector_version,
            records,
            assessments,
            drilldowns,
            all_proposals,
            external_artifacts,
            runner._notification_records,
            external_analysis_settings=runner.config.external_analysis,
            available_adapters=runner._analysis_adapters.keys(),
            expected_scheduler_interval_seconds=runner._expected_scheduler_interval_seconds,
        )
        runner._log_event(
            "health-loop",
            "INFO",
            "UI index generated",
            artifact_path=str(ui_index_path),
            assessment_count=len(assessments),
            trigger_count=len(triggers),
            drilldown_count=len(drilldowns),
            proposal_count=len(all_proposals),
            external_analysis_count=len(external_artifacts),
            event="ui-index-generated",
        )
    except OSError as exc:
        runner._log_event(
            "health-loop",
            "ERROR",
            "UI artifact generation failed",
            severity_reason=str(exc),
            event="ui-index-failed",
        )

    runner._latest_external_artifacts = external_artifacts
    return assessments, triggers, drilldowns

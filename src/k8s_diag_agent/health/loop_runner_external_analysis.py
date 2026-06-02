"""External analysis seam extracted from HealthLoopRunner.

This module provides the `run_external_analysis_for_records` helper which encapsulates
the logic for running manual external analysis from snapshot records. Preserves
behavior exactly - no schema or artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to adapters
and handle artifact writing, logging, and notification recording.

These helpers do NOT import loop.py or HealthLoopRunner.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ..external_analysis.adapter import ExternalAnalysisAdapter, ExternalAnalysisRequest
from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from ..external_analysis.config import ExternalAnalysisPolicy
from .loop_types import HealthSnapshotRecord, ManualExternalAnalysisRequest
from .notifications import NotificationArtifact, build_external_analysis_notification
from .utils import normalize_ref

# Type alias for callbacks to avoid hard coupling to runner
RecordNotificationFn = Callable[[Path, NotificationArtifact], Path]
LogEventFn = Callable[..., None]


def run_external_analysis_for_records(
    *,
    records: list[HealthSnapshotRecord],
    manual_requests: tuple[ManualExternalAnalysisRequest, ...],
    external_analysis_policy: ExternalAnalysisPolicy,
    analysis_adapters: dict[str, ExternalAnalysisAdapter],
    run_id: str,
    run_label: str,
    record_notification_fn: RecordNotificationFn,
    log_event_fn: LogEventFn | None = None,
    directories: dict[str, Path],
) -> list[ExternalAnalysisArtifact]:
    """Run manual external analysis for snapshot records.

    Preserves exact behavior from HealthLoopRunner._run_external_analysis():
    1. Check if adapters, manual requests, and manual policy are enabled
    2. For each manual request, look up adapter and record
    3. Build ExternalAnalysisRequest and call adapter.run()
    4. Write artifact, log event, create notification
    5. Return all artifacts

    Args:
        records: List of health snapshot records.
        manual_requests: Tuple of manual external analysis requests (objects with tool and target attributes).
        external_analysis_policy: Policy controlling manual external analysis behavior.
        analysis_adapters: Dict mapping adapter names to adapter instances.
        run_id: Current run identifier.
        run_label: Human-readable run label.
        record_notification_fn: Callback to record a notification artifact.
        log_event_fn: Optional callback for logging events.
        directories: Dict with 'external_analysis' and 'notifications' paths.

    Returns:
        List of ExternalAnalysisArtifact objects created.
    """
    artifacts: list[ExternalAnalysisArtifact] = []

    # Early return: no adapters available
    if not analysis_adapters:
        return artifacts

    # Early return: no manual requests
    if not manual_requests:
        return artifacts

    # Check manual policy is enabled
    if not external_analysis_policy.manual:
        if log_event_fn:
            log_event_fn(
                "external-analysis",
                "INFO",
                "Manual external analysis ignored",
                event="manual-disabled",
                manual_request_count=len(manual_requests),
            )
        return artifacts

    # Build lookup table for records by normalized label
    record_lookup: dict[str, HealthSnapshotRecord] = {
        normalize_ref(record.target.label): record for record in records
    }

    for request in manual_requests:
        tool = request.tool
        target = request.target

        adapter = analysis_adapters.get(tool)
        if not adapter:
            if log_event_fn:
                log_event_fn(
                    "external-analysis",
                    "WARNING",
                    "External analysis adapter unavailable",
                    tool=tool,
                    cluster_label=target,
                )
            continue

        record = record_lookup.get(target)
        if not record:
            if log_event_fn:
                log_event_fn(
                    "external-analysis",
                    "WARNING",
                    "External analysis target missing",
                    tool=tool,
                    cluster_label=target,
                )
            continue

        # Build source artifact path
        source_artifact = record.assessment.artifact_path if record.assessment else str(record.path)

        # Build analysis request
        analysis_request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label=record.target.label,
            source_artifact=source_artifact,
        )

        # Run the adapter
        artifact = adapter.run(analysis_request)

        # Build artifact path: {run_id}-{cluster_label}-{adapter_name}.json
        artifact_path = directories["external_analysis"] / (f"{run_id}-{record.target.label}-{adapter.name}.json")
        artifact_with_path = replace(artifact, artifact_path=str(artifact_path))

        # Write artifact
        write_external_analysis_artifact(artifact_path, artifact_with_path)

        # Determine log severity from status
        if artifact_with_path.status == ExternalAnalysisStatus.SUCCESS:
            severity = "INFO"
        elif artifact_with_path.status == ExternalAnalysisStatus.FAILED:
            severity = "ERROR"
        else:
            severity = "WARNING"

        # Log the event
        if log_event_fn:
            log_event_fn(
                "external-analysis",
                severity,
                "External analysis result recorded",
                tool=adapter.name,
                cluster_label=record.target.label,
                status=artifact_with_path.status.value,
                artifact_path=str(artifact_path),
            )

        # Create and record notification
        notification = build_external_analysis_notification(artifact_with_path)
        record_notification_fn(directories["notifications"], notification)

        artifacts.append(artifact_with_path)

    return artifacts

"""Assessment artifact building seam extracted from HealthLoopRunner.

This module provides the `build_assessments_for_records` helper which encapsulates
the logic for building health assessment artifacts from snapshot records, including
degraded-health notification emission. Preserves behavior exactly - no schema or
artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to assessment
building helpers and handle artifact writing, validation, and notification recording.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .image_pull_secret import ImagePullSecretInsight
from .loop_history import (
    HealthHistoryEntry,
    HealthRating,
    _watched_crd_versions,
    _watched_release_versions,
    _write_json,
)
from .notifications import (
    NotificationArtifact,
    build_degraded_health_notification,
)
from .validators import HealthAssessmentValidator

if TYPE_CHECKING:
    from .loop_history import HealthAssessmentArtifact, HealthAssessmentResult
    from .loop_types import HealthSnapshotRecord


# Type alias for callbacks to avoid hard coupling to runner
RecordNotificationFn = Callable[[Path, NotificationArtifact], Path]
ImagePullInspector = object  # Duck-typed; has .inspect() method
LogEventFn = Callable[..., None]


def build_assessments_for_records(
    *,
    records: list[HealthSnapshotRecord],
    history: dict[str, HealthHistoryEntry],
    assessment_dir: Path,
    notification_dir: Path,
    run_id: str,
    run_label: str,
    warning_event_threshold: int,
    record_notification_fn: RecordNotificationFn,
    image_pull_inspector: ImagePullInspector | None = None,
    log_event_fn: LogEventFn | None = None,
) -> list[HealthAssessmentArtifact]:
    """Build health assessment artifacts from snapshot records.

    Preserves exact behavior from HealthLoopRunner._build_assessments():
    1. For each record with monitor_health enabled:
       - Optionally inspect image pull secrets (if backoff detected)
       - Build health assessment using warning threshold
       - Update record with assessment results
       - Write and validate assessment artifact
       - Emit degraded-health notification if rating is DEGRADED
    2. Update history for each cluster
    3. Store image pull secret insight on record

    Args:
        records: List of health snapshot records to process.
        history: Mapping of cluster_id to HealthHistoryEntry for previous state.
        assessment_dir: Directory for writing assessment artifacts.
        notification_dir: Directory for writing notification artifacts.
        run_id: Current run identifier.
        run_label: Human-readable run label.
        warning_event_threshold: Warning event count threshold for health rating.
        record_notification_fn: Callback to record a notification artifact.
        image_pull_inspector: Optional inspector for image pull secrets (has .inspect()).
        log_event_fn: Optional callback for logging events.

    Returns:
        List of HealthAssessmentArtifact objects created.
    """
    # Import build_health_assessment locally to avoid import cycle
    from ..render.formatter import assessment_to_dict
    from .loop_health_assessment import build_health_assessment
    from .loop_history import HealthAssessmentArtifact

    artifacts: list[HealthAssessmentArtifact] = []

    for record in records:
        cluster_id = record.snapshot.metadata.cluster_id
        previous = history.get(cluster_id)
        watched_release_versions = _watched_release_versions(record.snapshot, record.target.watched_helm_releases)
        watched_crd_versions = _watched_crd_versions(record.snapshot, record.target.watched_crd_families)
        assessment_result: HealthAssessmentResult | None = None
        insight: ImagePullSecretInsight | None = None
        pod_counts = record.snapshot.health_signals.pod_counts

        # Image pull secret inspection (best-effort, non-fatal)
        if record.target.monitor_health and pod_counts.image_pull_backoff > 0:
            if image_pull_inspector is not None:
                try:
                    insight = image_pull_inspector.inspect(
                        record.target.context,
                        (),
                        record.snapshot.health_signals.warning_events,
                    )
                except (OSError, RuntimeError, TimeoutError) as exc:
                    if log_event_fn:
                        log_event_fn(
                            "health-loop",
                            "WARNING",
                            "Image pull secret inspection failed",
                            cluster_label=record.target.label,
                            cluster_context=record.target.context,
                            severity_reason=str(exc),
                            event="image-pull-secret-inspection",
                        )

        if record.target.monitor_health:
            assessment_result = build_health_assessment(
                record.snapshot,
                record.target,
                previous,
                record.baseline_policy,
                warning_event_threshold,
                image_pull_secret_insight=insight,
            )
            record.assessment = assessment_result
            record.pattern_reasons = assessment_result.pattern_reasons
            record.pattern_metadata = assessment_result.pattern_metadata

            assessment_path = assessment_dir / f"{run_id}-{record.target.label}-assessment.json"
            artifact = HealthAssessmentArtifact(
                run_label=run_label,
                run_id=run_id,
                timestamp=datetime.now(UTC),
                context=record.target.context,
                label=record.target.label,
                cluster_id=cluster_id,
                snapshot_path=str(record.path),
                assessment=assessment_to_dict(assessment_result.assessment),
                missing_evidence=assessment_result.missing_evidence,
                health_rating=assessment_result.rating,
                artifact_path=str(assessment_path),
            )
            HealthAssessmentValidator.validate(artifact.to_dict())
            _write_json(artifact.to_dict(), assessment_path)
            artifacts.append(artifact)

            # Emit degraded health notification
            if artifact.health_rating == HealthRating.DEGRADED:
                notification = build_degraded_health_notification(run_id, record, artifact)
                record_notification_fn(notification_dir, notification)

        # Update history entry for this cluster
        history[cluster_id] = HealthHistoryEntry(
            cluster_id=cluster_id,
            node_count=record.snapshot.metadata.node_count,
            pod_count=record.snapshot.metadata.pod_count,
            control_plane_version=record.snapshot.metadata.control_plane_version or "",
            health_rating=assessment_result.rating if assessment_result else HealthRating.HEALTHY,
            missing_evidence=assessment_result.missing_evidence if assessment_result else (),
            watched_helm_releases=watched_release_versions,
            watched_crd_families=watched_crd_versions,
            node_conditions=record.snapshot.health_signals.node_conditions.to_dict(),
            pod_counts=record.snapshot.health_signals.pod_counts.to_dict(),
            job_failures=record.snapshot.health_signals.job_failures,
            warning_event_count=len(record.snapshot.health_signals.warning_events),
            cluster_class=record.target.cluster_class,
            cluster_role=record.target.cluster_role,
            baseline_cohort=record.target.baseline_cohort,
            baseline_policy_path=record.baseline_policy_path,
        )

        # Store image pull secret insight on record
        record.image_pull_secret_insight = insight

    return artifacts

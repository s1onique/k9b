"""Drilldown artifact building seam extracted from HealthLoopRunner.

This module provides the `build_drilldowns_for_records` helper which encapsulates
the logic for building drilldown artifacts from snapshot records. Preserves
behavior exactly - no schema or artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to
drilldown collection and handle artifact writing, validation, and logging.

These helpers do NOT import loop.py or HealthLoopRunner.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .drilldown import DrilldownArtifact, DrilldownCollector
from .image_pull_secret import ImagePullSecretInsight
from .loop_history import HealthHistoryEntry, _write_json
from .validators import DrilldownArtifactValidator

# Type alias for log event callback to avoid hard coupling to runner
LogEventFn = Callable[..., None]


def build_drilldowns_for_records(
    *,
    records: Sequence[Any],
    previous_history: dict[str, HealthHistoryEntry],
    directory: Path,
    run_id: str,
    run_label: str,
    drilldown_collector: DrilldownCollector | None,
    manual_drilldown_contexts: set[str],
    warning_event_threshold: int,
    log_event_fn: LogEventFn | None = None,
) -> list[DrilldownArtifact]:
    """Build drilldown artifacts from snapshot records.

    Preserves exact behavior from HealthLoopRunner._build_drilldowns():
    1. For each record, determine drilldown reasons using assessment data
    2. If reasons exist, collect drilldown evidence using DrilldownCollector
    3. Create and validate DrilldownArtifact with all evidence
    4. Write artifact to directory and log the event

    Args:
        records: Sequence of health snapshot records with assessment data.
            Expected to have: target (with context, label), snapshot (with metadata.cluster_id,
            metadata.captured_at, health_signals.pod_counts, health_signals.warning_events,
            health_signals.job_failures), assessment (with rating, missing_evidence), pattern_reasons,
            pattern_metadata, image_pull_secret_insight
        previous_history: Prior health entries indexed by cluster_id.
        directory: Directory for writing drilldown artifacts.
        run_id: Current run identifier.
        run_label: Human-readable run label.
        drilldown_collector: Collector for drilldown evidence (uses default if None).
        manual_drilldown_contexts: Set of contexts explicitly requested for drilldown.
        warning_event_threshold: Minimum warning events to trigger drilldown reason.
        log_event_fn: Optional callback for logging events.

    Returns:
        List of DrilldownArtifact objects created.
    """
    # Import new_artifact_id locally to avoid import cycle at module level
    from ..identity.artifact import new_artifact_id

    # Import determine_drilldown_reasons from loop_drilldown_helpers
    from .loop_drilldown_helpers import determine_drilldown_reasons

    collector = drilldown_collector or DrilldownCollector()
    artifacts: list[DrilldownArtifact] = []

    for record in records:
        reasons = determine_drilldown_reasons(
            record=record,
            previous_history=previous_history,
            manual_drilldown_contexts=manual_drilldown_contexts,
            warning_event_threshold=warning_event_threshold,
        )
        if not reasons:
            continue

        # Get image_pull_secret_insight with fallback to None
        insight: ImagePullSecretInsight | None = record.image_pull_secret_insight if hasattr(record, 'image_pull_secret_insight') else None

        try:
            evidence = collector.collect(
                record.target.context,
                (record.target.context,),
                insight,
                pattern_reasons=record.pattern_reasons,
                pattern_metadata=record.pattern_metadata,
            )
        except RuntimeError as exc:
            if log_event_fn:
                log_event_fn(
                    "drilldown-collector",
                    "WARNING",
                    "Drilldown collection failed",
                    cluster_label=record.target.label,
                    cluster_context=record.target.context,
                    severity_reason=str(exc),
                    event="drilldown-failed",
                )
            continue

        path = directory / f"{run_id}-{record.target.label}-drilldown.json"
        artifact = DrilldownArtifact(
            run_label=run_label,
            run_id=run_id,
            timestamp=datetime.now(UTC),
            snapshot_timestamp=record.snapshot.metadata.captured_at,
            context=record.target.context,
            label=record.target.label,
            cluster_id=record.snapshot.metadata.cluster_id,
            trigger_reasons=reasons,
            missing_evidence=tuple(record.assessment.missing_evidence if record.assessment else ()),
            evidence_summary=evidence.summary,
            affected_namespaces=evidence.affected_namespaces,
            affected_workloads=evidence.affected_workloads,
            warning_events=evidence.warning_events,
            non_running_pods=evidence.non_running_pods,
            pod_descriptions=evidence.pod_descriptions,
            rollout_status=evidence.rollouts,
            collection_timestamps=evidence.collection_timestamps,
            pattern_details=evidence.pattern_details,
            artifact_path=str(path),
            artifact_id=new_artifact_id(),
        )
        DrilldownArtifactValidator.validate(artifact.to_dict())
        _write_json(artifact.to_dict(), path)
        artifacts.append(artifact)

        if log_event_fn:
            log_event_fn(
                "drilldown-collector",
                "INFO",
                "Drilldown artifact created",
                cluster_label=record.target.label,
                artifact_path=str(path),
                event="drilldown",
            )

    return artifacts
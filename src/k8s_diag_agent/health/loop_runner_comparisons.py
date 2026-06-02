"""Comparison trigger artifact building seam extracted from HealthLoopRunner.

This module provides the `evaluate_triggers_for_records` helper which encapsulates
the logic for building comparison trigger artifacts from snapshot records, including
suspicious drift notification emission. Preserves behavior exactly - no schema or
artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to comparison
policy helpers and handle artifact writing, validation, and notification recording.

These helpers do NOT import loop.py or HealthLoopRunner.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .loop_comparison_policy import BaselineRegistry, _policy_eligible_pair
from .loop_history import _serialize_value, _write_json
from .loop_types import HealthSnapshotRecord
from .notifications import NotificationArtifact, build_suspicious_comparison_notification
from .validators import ComparisonDecisionValidator

if TYPE_CHECKING:
    from ..collect.cluster_snapshot import ClusterSnapshot
    from ..compare.two_cluster import ClusterComparison
    from .loop import (
        ComparisonPeer,
        ComparisonTriggerArtifact,
        TriggerPolicy,
    )


# Type alias for callbacks to avoid hard coupling to runner
RecordNotificationFn = Callable[[Path, NotificationArtifact], Path]
LogEventFn = Callable[..., None]
ComparisonFn = Callable[["ClusterSnapshot", "ClusterSnapshot"], "ClusterComparison"]


def evaluate_triggers_for_records(
    *,
    records: list[HealthSnapshotRecord],
    peers: tuple[ComparisonPeer, ...],
    trigger_policy: TriggerPolicy,
    baseline_registry: BaselineRegistry,
    history: Mapping[str, Any],
    run_id: str,
    run_label: str,
    manual_comparison_keys: set[tuple[str, str]],
    comparison_fn: ComparisonFn,
    record_notification_fn: RecordNotificationFn,
    log_event_fn: LogEventFn | None = None,
    directories: dict[str, Path],
) -> list[ComparisonTriggerArtifact]:
    """Evaluate comparison triggers for peer pairs and build trigger artifacts.

    Preserves exact behavior from HealthLoopRunner._evaluate_triggers():
    1. For each peer pair, look up primary and secondary records
    2. Check policy eligibility using _policy_eligible_pair
    3. If policy eligible, determine trigger reasons using determine_pair_trigger_reasons
    4. For triggered pairs, run comparison and build ComparisonTriggerArtifact
    5. Write comparison JSON, trigger artifact, and comparison decisions
    6. Emit suspicious comparison notification for SUSPICIOUS_DRIFT intent

    Args:
        records: List of health snapshot records to process.
        peers: Tuple of peer comparison configurations.
        trigger_policy: Trigger policy for determining which conditions trigger comparison.
        baseline_registry: Registry of baseline policies for role resolution.
        history: Mapping of cluster_id to HealthHistoryEntry for previous state.
        run_id: Current run identifier.
        run_label: Human-readable run label.
        manual_comparison_keys: Set of (primary, secondary) tuples for manual comparisons.
        comparison_fn: Function to compare two cluster snapshots.
        record_notification_fn: Callback to record a notification artifact.
        log_event_fn: Optional callback for logging events.
        directories: Dict with 'comparisons', 'triggers', 'root', 'notifications' paths.

    Returns:
        List of ComparisonTriggerArtifact objects created.
    """
    # Import locally to avoid circular imports at module level
    from ..identity.artifact import new_artifact_id
    from .loop import (
        ComparisonDecision,
        ComparisonIntent,
        ComparisonTriggerArtifact,
        TriggerDetail,
        determine_pair_trigger_reasons,
    )

    triggers: list[ComparisonTriggerArtifact] = []
    decisions: list[ComparisonDecision] = []

    if not peers:
        if log_event_fn:
            from .loop import _HEALTH_ONLY_MESSAGE

            log_event_fn(
                "health-loop",
                "INFO",
                _HEALTH_ONLY_MESSAGE,
                event="health-only",
            )
        return triggers

    # Build lookup table for records by reference
    record_lookup: dict[str, HealthSnapshotRecord] = {}
    for record in records:
        primary_ref, label_ref = record.refs()
        record_lookup[primary_ref] = record
        record_lookup[label_ref] = record

    for peer in peers:
        primary_record = record_lookup.get(peer.primary)
        if not primary_record:
            continue
        secondary_record = record_lookup.get(peer.secondary)
        if not secondary_record:
            continue

        expected_categories = tuple(sorted(peer.expected_drift_categories))
        ignored_categories = tuple(
            sorted(
                set(primary_record.baseline_policy.ignored_drift_categories)
                | set(secondary_record.baseline_policy.ignored_drift_categories)
            )
        )
        peer_notes = peer.notes

        # Check policy eligibility
        (
            policy_eligible,
            policy_reason,
            primary_class,
            secondary_class,
            primary_role,
            secondary_role,
            primary_cohort,
            secondary_cohort,
        ) = _policy_eligible_pair(
            primary_record,
            secondary_record,
            peer.intent,
            baseline_registry,
        )

        classification_label = peer.intent.label()
        trigger_details: list[TriggerDetail] = []

        if policy_eligible:
            trigger_details = determine_pair_trigger_reasons(
                primary_record,
                secondary_record,
                trigger_policy,
                dict(history),
                manual_comparison_keys,
                primary_record.baseline_policy,
                baseline_registry,
                classification_label,
            )

        triggered = bool(trigger_details)

        # Log policy-ineligible pairs
        if not policy_eligible:
            if log_event_fn:
                log_event_fn(
                    "health-loop",
                    "INFO",
                    "Comparison skipped",
                    cluster_label=primary_record.target.label,
                    comparison_target=secondary_record.target.label,
                    comparison_intent=classification_label,
                    policy_eligible=False,
                    severity_reason=policy_reason,
                    primary_class=primary_class,
                    secondary_class=secondary_class,
                    primary_role=primary_role,
                    secondary_role=secondary_role,
                    primary_cohort=primary_cohort,
                    secondary_cohort=secondary_cohort,
                    expected_drift_categories=list(expected_categories),
                    ignored_drift_categories=list(ignored_categories),
                    event="comparison-skip",
                )

        # Build decision reason
        if not policy_eligible:
            decision_reason = policy_reason
        elif triggered:
            decision_reason = "; ".join(detail.reason for detail in trigger_details)
        else:
            decision_reason = "policy compatible but no triggers fired"

        decisions.append(
            ComparisonDecision(
                primary_label=primary_record.target.label,
                secondary_label=secondary_record.target.label,
                policy_eligible=policy_eligible,
                triggered=triggered,
                comparison_intent=classification_label,
                reason=decision_reason,
                primary_class=primary_class,
                secondary_class=secondary_class,
                primary_role=primary_role,
                secondary_role=secondary_role,
                primary_cohort=primary_cohort,
                secondary_cohort=secondary_cohort,
                expected_drift_categories=expected_categories,
                ignored_drift_categories=ignored_categories,
                notes=peer_notes,
            )
        )

        # Skip if not triggered
        if not policy_eligible or not triggered:
            continue

        # Run comparison and build trigger artifact
        comparison = comparison_fn(primary_record.snapshot, secondary_record.snapshot)
        summary = {key: len(value) for key, value in comparison.differences.items()}

        comparison_path = (
            directories["comparisons"]
            / f"{run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-comparison.json"
        )
        _write_json(
            {
                "differences": _serialize_value(comparison.differences),
                "trigger_reasons": [detail.reason for detail in trigger_details],
                "trigger_details": [detail.to_dict() for detail in trigger_details],
                "comparison_intent": classification_label,
                "expected_drift_categories": list(expected_categories),
                "ignored_drift_categories": list(ignored_categories),
                "peer_notes": peer_notes,
            },
            comparison_path,
        )

        artifact = ComparisonTriggerArtifact(
            run_label=run_label,
            run_id=run_id,
            timestamp=datetime.now(UTC),
            primary=primary_record.target.context,
            secondary=secondary_record.target.context,
            primary_label=primary_record.target.label,
            secondary_label=secondary_record.target.label,
            trigger_reasons=tuple(detail.reason for detail in trigger_details),
            comparison_summary=summary,
            differences=_serialize_value(comparison.differences),
            trigger_details=tuple(trigger_details),
            comparison_intent=classification_label,
            expected_drift_categories=expected_categories,
            ignored_drift_categories=ignored_categories,
            peer_notes=peer_notes,
            notes="; ".join(detail.reason for detail in trigger_details),
            artifact_id=new_artifact_id(),
        )
        triggers.append(artifact)

        # Write trigger artifact
        trigger_path = (
            directories["triggers"]
            / f"{run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-trigger.json"
        )
        _write_json(artifact.to_dict(), trigger_path)

        if log_event_fn:
            log_event_fn(
                "health-loop",
                "INFO",
                "Comparison trigger artifact recorded",
                cluster_label=primary_record.target.label,
                comparison_target=secondary_record.target.label,
                artifact_path=str(trigger_path),
                event="comparison-trigger",
                severity_reason="; ".join(detail.reason for detail in trigger_details),
            )

        # Emit suspicious comparison notification
        if peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
            notification = build_suspicious_comparison_notification(artifact)
            record_notification_fn(directories["notifications"], notification)

    # Write comparison decisions
    decision_path = directories["root"] / f"{run_id}-comparison-decisions.json"
    for decision in decisions:
        ComparisonDecisionValidator.validate(decision.to_dict())
    _write_json([decision.to_dict() for decision in decisions], decision_path)

    return triggers
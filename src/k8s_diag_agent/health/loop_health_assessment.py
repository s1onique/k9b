"""Health assessment computation extracted from loop.py.

This module provides the build_health_assessment function which computes
health assessments for clusters based on snapshot data, history, and baseline policies.

Preserves behavior exactly - no schema or artifact contract changes.

No runner logic - this is a pure function with no HealthLoopRunner dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .baseline import BaselinePolicy
from .image_pull_secret import ImagePullSecretInsight
from .loop_assessment_baseline import assess_baseline_policy
from .loop_assessment_counts import assess_count_issues
from .loop_assessment_history_drift import assess_previous_run_drift
from .loop_assessment_image_pull import assess_image_pull_issues
from .loop_assessment_missing_evidence import assess_missing_evidence
from .loop_assessment_regressions import check_regression_from_history
from .loop_assessment_result import build_health_assessment_result
from .loop_assessment_summary import derive_assessment_summary
from .loop_assessment_warning_events import match_warning_event_patterns
from .loop_history import HealthAssessmentResult, HealthHistoryEntry, HealthRating
from .loop_signal_id import _SignalIdGenerator

if TYPE_CHECKING:
    from ..collect.cluster_snapshot import ClusterSnapshot
    from ..models import ConfidenceLevel, Finding, Hypothesis, Layer, NextCheck, Signal
    from .loop import HealthTarget

__all__ = ["build_health_assessment"]


def build_health_assessment(
    snapshot: ClusterSnapshot,
    target: HealthTarget,
    previous: HealthHistoryEntry | None,
    baseline: BaselinePolicy,
    warning_event_threshold: int = 0,
    image_pull_secret_insight: ImagePullSecretInsight | None = None,
) -> HealthAssessmentResult:
    """Build a health assessment for a cluster snapshot.

    Preserves exact behavior from the original loop.py implementation.
    """
    # Import here to avoid circular imports at module level
    from ..collect.cluster_snapshot import ClusterSnapshot
    from ..models import (
        Assessment,
        ConfidenceLevel,
        Finding,
        Hypothesis,
        Layer,
        NextCheck,
        RecommendedAction,
        Signal,
    )

    generator = _SignalIdGenerator(target.label)
    signals: list[Signal] = []
    evidence_id = snapshot.metadata.cluster_id
    status = snapshot.collection_status
    missing = tuple(status.missing_evidence)
    issues_detected = False
    issue_findings: list[Finding] = []
    health_signals = snapshot.health_signals
    node_conditions = health_signals.node_conditions
    pod_counts = health_signals.pod_counts
    job_failures = health_signals.job_failures
    warning_events = health_signals.warning_events

    def add_signal(description: str, severity: str, layer: Layer) -> Signal:
        signal = Signal(
            id=generator.next_id(),
            description=description,
            layer=layer,
            evidence_id=evidence_id,
            severity=severity,
        )
        signals.append(signal)
        return signal

    def record_finding(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
        if not signal_ids:
            return
        issue_findings.append(
            Finding(
                id=generator.next_id(),
                description=description,
                supporting_signals=list(signal_ids),
                layer=layer,
            )
        )

    def _record_issue(description: str, severity: str, layer: Layer) -> Signal:
        signal = add_signal(description, severity, layer)
        record_finding(description, layer, [signal.id])
        return signal

    add_signal("Snapshot captured with available telemetry.", "low", Layer.OBSERVABILITY)
    if status.helm_error:
        issues_detected = True
        signal = add_signal(
            f"Helm collection reported an error ({status.helm_error}).",
            "high",
            Layer.OBSERVABILITY,
        )
        record_finding(
            f"Helm collection reported an error ({status.helm_error}).",
            Layer.OBSERVABILITY,
            [signal.id],
        )
    baseline_next_checks: list[NextCheck] = []
    baseline_reasons: list[str] = []
    image_pull_secret_next_checks: list[NextCheck] = []
    references: list[str] = []
    insight_hypothesis: Hypothesis | None = None
    pattern_reasons: list[str] = []
    pattern_metadata: dict[str, tuple[str, ...]] = {}
    pattern_next_checks: list[NextCheck] = []
    pattern_refs: list[str] = []
    pattern_hypotheses: list[Hypothesis] = []
    matched_event_ids: set[int] = set()

    missing_evidence_assessment = assess_missing_evidence(
        missing=missing,
        previous=previous,
        signal_adder=add_signal,
        finding_recorder=record_finding,
    )
    # If any missing evidence was detected, mark that an issue was found.
    # This preserves the original behavior: every missing item would set
    # issues_detected = True in the loop.
    issues_detected = issues_detected or bool(missing_evidence_assessment.signal_ids)

    control_plane_version = snapshot.metadata.control_plane_version or "unknown"
    has_control_plane_version = bool(control_plane_version.strip()) and control_plane_version.lower() != "unknown"
    if not has_control_plane_version:
        issues_detected = True
        signal = add_signal(
            "Control plane version is missing or unknown.",
            "medium",
            Layer.ROLLOUT,
        )
        record_finding(
            "Control plane version is missing or unknown.",
            Layer.ROLLOUT,
            [signal.id],
        )
    baseline_assessment = assess_baseline_policy(
        snapshot=snapshot,
        watched_helm_releases=target.watched_helm_releases,
        baseline=baseline,
        signal_adder=add_signal,
        finding_recorder=record_finding,
    )
    baseline_reasons.extend(baseline_assessment.baseline_reasons)
    baseline_next_checks.extend(baseline_assessment.baseline_next_checks)
    references.extend(baseline_assessment.references)
    if baseline_assessment.baseline_reasons:
        issues_detected = True

    history_drift_assessment = assess_previous_run_drift(
        previous=previous,
        control_plane_version=control_plane_version,
        snapshot_node_count=snapshot.metadata.node_count,
        snapshot_pod_count=snapshot.metadata.pod_count,
        watched_helm_releases=target.watched_helm_releases,
        watched_crd_families=target.watched_crd_families,
        snapshot=snapshot,
        signal_adder=add_signal,
        finding_recorder=record_finding,
    )
    issues_detected = issues_detected or history_drift_assessment.has_drift

    workload_issue_present = False
    node_issue_present = False

    count_issue_assessment = assess_count_issues(
        node_conditions=node_conditions,
        pod_counts=pod_counts,
        warning_events=warning_events,
        issue_recorder=_record_issue,
    )

    issues_detected = issues_detected or count_issue_assessment.issues_detected
    workload_issue_present = workload_issue_present or count_issue_assessment.workload_issue_present
    node_issue_present = node_issue_present or count_issue_assessment.node_issue_present
    warning_event_count = count_issue_assessment.warning_event_count
    references.extend(count_issue_assessment.references)

    # ImagePullBackOff count issue (recorded here to preserve order before assess_image_pull_issues)
    if pod_counts.image_pull_backoff > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("ImagePullBackOff")
        _record_issue(
            f"{pod_counts.image_pull_backoff} pods in ImagePullBackOff.",
            "high",
            Layer.WORKLOAD,
        )

        returned_hypothesis, image_pull_issues_detected = assess_image_pull_issues(
            image_pull_secret_insight=image_pull_secret_insight,
            signals=signals,
            signal_id_generator=generator.next_id,
            findings=issue_findings,
            next_checks=image_pull_secret_next_checks,
        )
        if returned_hypothesis is not None:
            insight_hypothesis = returned_hypothesis
        issues_detected = issues_detected or image_pull_issues_detected

    # Job failures (after ImagePullBackOff to preserve original ordering)
    if job_failures > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("job failures")
        _record_issue(
            f"{job_failures} failed job(s) observed.",
            "medium",
            Layer.WORKLOAD,
        )

    # Warning event threshold (after job failures to preserve original ordering)
    warning_threshold = warning_event_threshold
    warning_triggered = warning_event_count > 0 if warning_threshold <= 0 else warning_event_count >= warning_threshold
    if warning_triggered:
        workload_issue_present = True
        issues_detected = True
        references.append("warning events")
        latest_warning = warning_events[0] if warning_events else None
        warning_desc = f" {latest_warning.reason} in {latest_warning.namespace}" if latest_warning and latest_warning.namespace and latest_warning.reason else ""
        threshold_note = f" (threshold {warning_threshold})" if warning_threshold > 0 else ""
        _record_issue(
            f"{warning_event_count} warning events recorded{threshold_note}{warning_desc}.",
            "low",
            Layer.OBSERVABILITY,
        )

    regression_assessment = check_regression_from_history(
        snapshot=snapshot,
        previous=previous,
        warning_event_count=warning_event_count,
        signals=signals,
        signal_id_generator=generator.next_id,
        findings=issue_findings,
    )
    issues_detected = issues_detected or regression_assessment.has_regression
    workload_issue_present = workload_issue_present or regression_assessment.workload_regression
    node_issue_present = node_issue_present or regression_assessment.node_regression
    references.extend(regression_assessment.references)

    warning_event_patterns_matched = match_warning_event_patterns(
        warning_events=warning_events,
        signals=signals,
        signal_id_generator=generator.next_id,
        matched_event_ids=matched_event_ids,
        findings=issue_findings,
        pattern_reasons=pattern_reasons,
        pattern_metadata=pattern_metadata,
        pattern_refs=pattern_refs,
        pattern_next_checks=pattern_next_checks,
        pattern_hypotheses=pattern_hypotheses,
    )

    issues_detected = issues_detected or warning_event_patterns_matched

    summary = derive_assessment_summary(
        signals=signals,
        issues_detected=issues_detected,
        workload_issue_present=workload_issue_present,
        node_issue_present=node_issue_present,
        references=references,
        helm_error=status.helm_error,
        has_missing_evidence=bool(missing),
        has_image_pull_secret_insight=bool(image_pull_secret_insight),
        pattern_refs=pattern_refs,
    )

    rating = summary.rating
    dominant_layer = summary.dominant_layer or Layer.OBSERVABILITY
    safety_level = summary.safety_level
    references = list(summary.references)

    findings = [
        Finding(
            id=generator.next_id(),
            description=f"Health assessment for {target.label} is {rating.value}.",
            supporting_signals=[signal.id for signal in signals],
            layer=dominant_layer,
        )
    ]
    findings.extend(issue_findings)
    if issues_detected:
        baseline_note = "; ".join(dict.fromkeys(baseline_reasons))
        description = (
            f"Baseline policy violation: {baseline_note}"
            if baseline_note
            else ("Node/workload health signals or regressions suggest the cluster may be unstable." if node_issue_present or workload_issue_present else "Missing telemetry or version drift suggests the cluster may be unstable.")
        )
        base_hypothesis = Hypothesis(
            id=generator.next_id(),
            description=description,
            confidence=ConfidenceLevel.MEDIUM,
            probable_layer=dominant_layer,
            what_would_falsify=("Nodes become ready, pods stay running, warning events quiet down, and Helm errors stay absent." if node_issue_present or workload_issue_present else "Telemetry gaps close and node/pod counts stabilize without Helm errors."),
        )
        detailed_hypotheses: list[Hypothesis] = []
        detailed_hypotheses.extend(pattern_hypotheses)
        if insight_hypothesis:
            detailed_hypotheses.append(insight_hypothesis)
        hypotheses = detailed_hypotheses + [base_hypothesis]
    else:
        hypotheses = [
            Hypothesis(
                id=generator.next_id(),
                description="Telemetry is complete and no high-severity drift is observed.",
                confidence=ConfidenceLevel.HIGH,
                probable_layer=dominant_layer,
                what_would_falsify="A new control plane drift, missing evidence, or Helm error appears.",
            )
        ]

    next_checks: list[NextCheck] = []
    if missing:
        next_checks.append(
            NextCheck(
                description="Collect the missing telemetry referenced above.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=list(missing),
            )
        )
    else:
        next_checks.append(
            NextCheck(
                description="Review node, pod, and control plane status before taking action.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["nodes", "pods", "control plane version"],
            )
        )
    if node_issue_present or workload_issue_present:
        next_checks.append(
            NextCheck(
                description="Investigate the flagged nodes, pods, jobs, and warning events.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["nodes", "pods", "jobs", "events"],
            )
        )
    next_checks.extend(pattern_next_checks)
    next_checks.extend(baseline_next_checks)
    next_checks.extend(image_pull_secret_next_checks)

    assessment_action = RecommendedAction(
        type="observation",
        description="Track the observed signals before escalating to corrective actions.",
        references=references,
        safety_level=safety_level,
    )

    overall_confidence = ConfidenceLevel.MEDIUM if issues_detected else ConfidenceLevel.HIGH
    assessment = Assessment(
        observed_signals=signals,
        findings=findings,
        hypotheses=hypotheses,
        next_evidence_to_collect=next_checks,
        recommended_action=assessment_action,
        safety_level=safety_level,
        probable_layer_of_origin=dominant_layer,
        overall_confidence=overall_confidence,
    )
    return build_health_assessment_result(
        assessment=assessment,
        rating=rating,
        missing_evidence=missing,
        node_count=snapshot.metadata.node_count,
        pod_count=snapshot.metadata.pod_count,
        control_plane_version=control_plane_version,
        pattern_reasons=tuple(dict.fromkeys(pattern_reasons)),
        pattern_metadata={key: tuple(pattern_metadata.get(key, ())) for key in pattern_metadata},
    )

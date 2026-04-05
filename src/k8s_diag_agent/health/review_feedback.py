"""Structured review generator for health runs and drilldown artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Sequence, Tuple

from ..feedback.models import FailureMode, ProposedImprovement
from ..models import ConfidenceLevel
from .drilldown import DrilldownArtifact
from .image_pull_secret import BROKEN_IMAGE_PULL_SECRET_REASON

if TYPE_CHECKING:
    from .loop import HealthAssessmentArtifact


_REASON_PRIORITIES: Dict[str, int] = {
    BROKEN_IMAGE_PULL_SECRET_REASON.lower(): 0,
    "imagepullbackoff": 0,
    "crashloopbackoff": 1,
    "job_failures": 2,
    "probe_failure": 2,
    "failed_scheduling": 3,
    "missing_metrics": 3,
    "pvc_pending": 3,
    "ingress_timeout": 3,
    "warning_event_threshold": 4,
    "health_regression": 3,
}
_DEFAULT_PRIORITY = 5


def _severity_bucket(artifact: DrilldownArtifact) -> int:
    priorities = [_REASON_PRIORITIES.get(reason.lower(), _DEFAULT_PRIORITY) for reason in artifact.trigger_reasons]
    if not priorities:
        return _DEFAULT_PRIORITY
    return min(priorities)


def _level_from_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


@dataclass(frozen=True)
class DrilldownSelection:
    context: str
    label: str
    severity: int
    reasons: Tuple[str, ...]
    missing_evidence: Tuple[str, ...]
    warning_event_count: int
    non_running_pod_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context": self.context,
            "label": self.label,
            "severity": self.severity,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "warning_event_count": self.warning_event_count,
            "non_running_pod_count": self.non_running_pod_count,
        }


@dataclass(frozen=True)
class QualityMetric:
    dimension: str
    level: str
    score: int
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "level": self.level,
            "score": self.score,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HealthReviewArtifact:
    run_id: str
    timestamp: datetime
    selected_drilldowns: Tuple[DrilldownSelection, ...]
    quality_summary: Tuple[QualityMetric, ...]
    failure_modes: Tuple[str, ...]
    proposed_improvements: Tuple[ProposedImprovement, ...]
    review_version: str = "health-review:v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "review_version": self.review_version,
            "selected_drilldowns": [selection.to_dict() for selection in self.selected_drilldowns],
            "quality_summary": [metric.to_dict() for metric in self.quality_summary],
            "failure_modes": list(self.failure_modes),
            "proposed_improvements": [
                {
                    "id": improvement.id,
                    "description": improvement.description,
                    "target": improvement.target,
                    "owner": improvement.owner,
                    "confidence": improvement.confidence.value if improvement.confidence else None,
                    "rationale": improvement.rationale,
                    "related_failure_modes": [fm.value for fm in improvement.related_failure_modes],
                }
                for improvement in self.proposed_improvements
            ],
        }


def _summarize_drilldowns(drilldowns: Sequence[DrilldownArtifact], limit: int = 3) -> Tuple[DrilldownSelection, ...]:
    sorted_artifacts = sorted(drilldowns, key=lambda artifact: (_severity_bucket(artifact), len(artifact.warning_events), artifact.context))
    selections: List[DrilldownSelection] = []
    for artifact in sorted_artifacts[:limit]:
        warning_count = sum(int(event.count) for event in artifact.warning_events)
        selections.append(
            DrilldownSelection(
                context=artifact.context,
                label=artifact.label,
                severity=_severity_bucket(artifact),
                reasons=artifact.trigger_reasons,
                missing_evidence=artifact.missing_evidence,
                warning_event_count=warning_count,
                non_running_pod_count=len(artifact.non_running_pods),
            )
        )
    return tuple(selections)


def _extract_assessment_data(artifact: HealthAssessmentArtifact | None) -> Dict[str, Any]:
    if not artifact or not artifact.assessment:
        return {}
    return artifact.assessment


def _best_assessment_for_drilldown(
    drilldown: DrilldownSelection | None, assessments: Sequence[HealthAssessmentArtifact]
) -> HealthAssessmentArtifact | None:
    if not drilldown:
        return assessments[0] if assessments else None
    for artifact in assessments:
        if artifact.context == drilldown.context or artifact.label == drilldown.label:
            return artifact
    return assessments[0] if assessments else None


def _score_signal_quality(selection: DrilldownSelection | None) -> QualityMetric:
    if not selection:
        return QualityMetric(
            dimension="signal_quality",
            level="low",
            score=0,
            detail="No drilldown data available to evaluate signal coverage.",
        )
    evidence_points = selection.warning_event_count + selection.non_running_pod_count * 2
    score = min(100, evidence_points * 20)
    return QualityMetric(
        dimension="signal_quality",
        level=_level_from_score(score),
        score=score,
        detail=(
            f"{selection.warning_event_count} warning events and {selection.non_running_pod_count} non-running pods observed."
        ),
    )


def _score_noise_baseline(
    assessment: HealthAssessmentArtifact | None, selection: DrilldownSelection | None
) -> Tuple[QualityMetric, bool, bool]:
    baseline_flag = False
    noise_flag = False
    detail_parts: List[str] = []
    score = 50
    assessment_data = _extract_assessment_data(assessment)
    for finding in assessment_data.get("findings", []):
        if "baseline" in str(finding.get("description", "")).lower():
            baseline_flag = True
            detail_parts.append("Baseline policy drift was flagged.")
            score = min(100, score + 30)
            break
    if selection:
        if selection.warning_event_count >= 2 and selection.non_running_pod_count == 0:
            noise_flag = True
            detail_parts.append("Warnings appear without matching pod failures; noise is likely.")
            score = max(0, score - 30)
    level = "high" if baseline_flag else "low" if noise_flag else "medium"
    if not detail_parts:
        detail_parts.append("No baseline drift or noise patterns were detected.")
    return (
        QualityMetric(
            dimension="noise_baseline_mismatch",
            level=level,
            score=max(0, min(100, score)),
            detail=" ".join(detail_parts),
        ),
        baseline_flag,
        noise_flag,
    )


def _score_drilldown_prioritization(selection: DrilldownSelection | None) -> QualityMetric:
    if not selection:
        return QualityMetric(
            dimension="drilldown_prioritization",
            level="low",
            score=10,
            detail="No drilldown was selected for prioritization.",
        )
    score = max(0, 100 - selection.severity * 20)
    level = "high" if selection.severity <= 1 else "medium" if selection.severity <= 3 else "low"
    detail = f"Top drilldown severity bucket {selection.severity} prioritized."
    return QualityMetric(
        dimension="drilldown_prioritization",
        level=level,
        score=score,
        detail=detail,
    )


def _parse_confidence(confidence_value: Any) -> ConfidenceLevel | None:
    if not confidence_value:
        return None
    try:
        return ConfidenceLevel(str(confidence_value))
    except ValueError:
        return None


def _score_hypothesis_confidence(assessment: HealthAssessmentArtifact | None) -> Tuple[QualityMetric, bool]:
    data = _extract_assessment_data(assessment)
    hypotheses = data.get("hypotheses", [])
    signals = data.get("observed_signals", [])
    highest_severity = 0
    severity_map = {"low": 1, "medium": 2, "high": 3}
    for signal in signals:
        highest_severity = max(highest_severity, severity_map.get(str(signal.get("severity", "low")).lower(), 1))
    if not hypotheses:
        return (
            QualityMetric(
                dimension="hypothesis_confidence",
                level="low",
                score=20,
                detail="No hypotheses were generated to evaluate confidence.",
            ),
            False,
        )
    confidence = _parse_confidence(hypotheses[0].get("confidence"))
    if not confidence:
        return (
            QualityMetric(
                dimension="hypothesis_confidence",
                level="medium",
                score=50,
                detail="Hypothesis confidence was missing or unrecognized.",
            ),
            False,
        )
    conf_value = {ConfidenceLevel.LOW: 1, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.HIGH: 3}[confidence]
    if highest_severity <= 1 and conf_value >= 3:
        return (
            QualityMetric(
                dimension="hypothesis_confidence",
                level="low",
                score=20,
                detail="High confidence was declared despite only low-severity signals.",
            ),
            True,
        )
    level = "high" if (highest_severity >= 2 and conf_value >= 2) else "medium"
    return (
        QualityMetric(
            dimension="hypothesis_confidence",
            level=level,
            score=80 if level == "high" else 60,
            detail=f"Confidence {confidence.value} aligns with severity bucket {highest_severity}.",
        ),
        False,
    )


def _score_next_checks(assessment: HealthAssessmentArtifact | None) -> QualityMetric:
    data = _extract_assessment_data(assessment)
    checks = data.get("next_evidence_to_collect", [])
    count = len(checks)
    if count >= 3:
        return QualityMetric(
            dimension="next_checks",
            level="high",
            score=90,
            detail=f"Provides {count} next checks across layers.",
        )
    if count >= 1:
        return QualityMetric(
            dimension="next_checks",
            level="medium",
            score=60,
            detail=f"Only {count} next check(s) are suggested; surface more if needed.",
        )
    return QualityMetric(
        dimension="next_checks",
        level="low",
        score=20,
        detail="No next checks were proposed.",
    )


def _score_missing_evidence(assessment: HealthAssessmentArtifact | None) -> QualityMetric:
    data = _extract_assessment_data(assessment)
    missing = assessment.missing_evidence if assessment else ()
    if not missing:
        return QualityMetric(
            dimension="missing_evidence",
            level="high",
            score=90,
            detail="No missing evidence recorded.",
        )
    referenced: set[str] = set()
    for check in data.get("next_evidence_to_collect", []):
        for item in check.get("evidence_needed", []):
            referenced.add(str(item).lower())
    matches = [item for item in missing if any(item.lower() in ref for ref in referenced)]
    if matches:
        return QualityMetric(
            dimension="missing_evidence",
            level="high",
            score=70,
            detail="Missing evidence is surfaced by the recommended checks.",
        )
    return QualityMetric(
        dimension="missing_evidence",
        level="low",
        score=30,
        detail="Missing evidence lacks targeted next checks.",
    )


def _determine_failure_modes(
    assessment: HealthAssessmentArtifact | None,
    baseline_flag: bool,
    noise_flag: bool,
    false_certainty: bool,
) -> Tuple[FailureMode, ...]:
    modes: List[FailureMode] = []
    if baseline_flag:
        modes.append(FailureMode.OTHER)
    if noise_flag:
        modes.append(FailureMode.OTHER)
    if false_certainty:
        modes.append(FailureMode.FALSE_CERTAINTY)
    if assessment and assessment.missing_evidence:
        modes.append(FailureMode.MISSING_EVIDENCE)
    if not assessment:
        modes.append(FailureMode.COLLECTION_ERROR)
    return tuple(dict.fromkeys(modes))


def _propose_improvements(
    threshold: int | None,
    selection: DrilldownSelection | None,
    baseline_flag: bool,
    noise_flag: bool,
    failure_modes: Tuple[FailureMode, ...],
) -> Tuple[ProposedImprovement, ...]:
    proposals: List[ProposedImprovement] = []
    if noise_flag and selection and threshold is not None:
        current = threshold if threshold > 0 else 2
        candidate = max(3, current + 2)
        proposals.append(
            ProposedImprovement(
                id="warning-event-threshold",
                description=(
                    f"Consider raising warning_event_threshold above {current} to ignore repeated warnings when pods remain healthy."
                ),
                target="health.trigger_policy.warning_event_threshold",
                owner="platform engineer",
                confidence=ConfidenceLevel.MEDIUM,
                rationale=(
                    f"Run produced {selection.warning_event_count} warnings with {selection.non_running_pod_count} non-running pods, indicating noise."
                ),
                related_failure_modes=list(failure_modes),
            )
        )
        proposals.append(
            ProposedImprovement(
                id="warning-suppression",
                description=(
                    "Review the warning event filters for repeated reasons to suppress noisy events while preserving actual failures."
                ),
                target="health.drilldown.warning_filter",
                owner="platform engineer",
                confidence=ConfidenceLevel.LOW,
                rationale=(
                    "Warnings repeat without matching pod issues; a suppression rule could improve signal-to-noise."
                ),
                related_failure_modes=list(failure_modes),
            )
        )
    if baseline_flag:
        proposals.append(
            ProposedImprovement(
                id="baseline-policy-review",
                description="Revisit the baseline policy expectations referenced in the findings before tagging the cluster as degraded.",
                target="health.baseline_policy",
                owner="platform engineer",
                confidence=ConfidenceLevel.MEDIUM,
                rationale="Baseline drift was flagged; confirm whether the expectation needs to evolve.",
                related_failure_modes=list(failure_modes),
            )
        )
    if selection and len(selection.reasons) <= 1 and selection.severity >= 3:
        proposals.append(
            ProposedImprovement(
                id="drilldown-ranking",
                description="Surface the next-highest severity drilldowns when top results are low priority so the team can browse alternatives.",
                target="health.drilldown.review_order",
                owner="platform engineer",
                confidence=ConfidenceLevel.LOW,
                rationale="Multiple contexts may be producing mild signals; surfacing more drilldowns could help spot real issues sooner.",
                related_failure_modes=list(failure_modes),
            )
        )
    return tuple(proposals)


def build_health_review(
    run_id: str,
    assessments: Sequence[HealthAssessmentArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    warning_threshold: int | None = None,
) -> HealthReviewArtifact:
    selections = _summarize_drilldowns(drilldowns)
    top_selection = selections[0] if selections else None
    assessment = _best_assessment_for_drilldown(top_selection, assessments) if selections else (assessments[0] if assessments else None)

    signal_metric = _score_signal_quality(top_selection)
    noise_metric, baseline_flag, noise_flag = _score_noise_baseline(assessment, top_selection)
    prioritization_metric = _score_drilldown_prioritization(top_selection)
    hypothesis_metric, false_certainty = _score_hypothesis_confidence(assessment)
    next_checks_metric = _score_next_checks(assessment)
    missing_evidence_metric = _score_missing_evidence(assessment)
    metrics = (
        signal_metric,
        noise_metric,
        prioritization_metric,
        hypothesis_metric,
        next_checks_metric,
        missing_evidence_metric,
    )
    failure_modes = _determine_failure_modes(assessment, baseline_flag, noise_flag, false_certainty)
    improvements = _propose_improvements(warning_threshold, top_selection, baseline_flag, noise_flag, failure_modes)
    return HealthReviewArtifact(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        selected_drilldowns=selections,
        quality_summary=metrics,
        failure_modes=tuple(mode.value for mode in failure_modes),
        proposed_improvements=improvements,
    )

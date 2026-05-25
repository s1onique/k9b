"""Structured review generator for health runs and drilldown artifacts.

This module provides the main entry point for health review generation.
Artifact models and quality scoring logic have been moved to:
- review_feedback_models: DrilldownSelection, QualityMetric
- review_feedback_quality: scoring helpers and failure mode determination

Imports from new modules for backward compatibility with existing callers.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..datetime_utils import ensure_utc
from ..feedback.models import FailureMode, ProposedImprovement
from ..identity.artifact import new_artifact_id
from ..models import ConfidenceLevel
from .drilldown import DrilldownArtifact
from .review_feedback_models import DrilldownSelection, QualityMetric
from .review_feedback_quality import (
    _best_assessment_for_drilldown,
    _determine_failure_modes,
    _propose_improvements,
    _score_drilldown_prioritization,
    _score_hypothesis_confidence,
    _score_missing_evidence,
    _score_next_checks,
    _score_noise_baseline,
    _score_signal_quality,
    _summarize_drilldowns,
)

if TYPE_CHECKING:
    from .loop import HealthAssessmentArtifact


# Re-export for backward compatibility
__all__ = [
    "DrilldownSelection",
    "HealthReviewArtifact",
    "QualityMetric",
    "build_health_review",
]


@dataclass(frozen=True)
class HealthReviewArtifact:
    run_id: str
    timestamp: datetime
    selected_drilldowns: tuple[DrilldownSelection, ...]
    quality_summary: tuple[QualityMetric, ...]
    failure_modes: tuple[str, ...]
    proposed_improvements: tuple[ProposedImprovement, ...]
    review_version: str = "health-review:v1"
    # Immutable artifact identity (UUIDv7)
    # None for legacy artifacts, auto-generated for new artifacts via build_health_review()
    artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        # Include artifact_id when present (backward compat: legacy artifacts without it)
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> HealthReviewArtifact:
        if not isinstance(raw, Mapping):
            raise ValueError("Health review artifact must be a mapping")

        def _parse_selections(key: str) -> tuple[DrilldownSelection, ...]:
            values = raw.get(key) or []
            if not isinstance(values, Sequence):
                return ()
            return tuple(DrilldownSelection.from_dict(item) for item in values if isinstance(item, Mapping))

        def _parse_metrics(key: str) -> tuple[QualityMetric, ...]:
            values = raw.get(key) or []
            if not isinstance(values, Sequence):
                return ()
            return tuple(QualityMetric.from_dict(item) for item in values if isinstance(item, Mapping))

        selections = _parse_selections("selected_drilldowns")

        metrics = _parse_metrics("quality_summary")

        improvements_raw = raw.get("proposed_improvements") or []
        improvements: list[ProposedImprovement] = []
        for entry in improvements_raw:
            if not isinstance(entry, Mapping):
                continue
            confidence_value = entry.get("confidence")
            confidence = None
            if confidence_value:
                try:
                    confidence = ConfidenceLevel(str(confidence_value))
                except ValueError:
                    confidence = None
            related = []
            for fm in entry.get("related_failure_modes") or []:
                try:
                    related.append(FailureMode(str(fm)))
                except ValueError:
                    continue
            improvements.append(
                ProposedImprovement(
                    id=str(entry.get("id") or ""),
                    description=str(entry.get("description") or ""),
                    target=str(entry.get("target") or ""),
                    owner=str(entry.get("owner")) if entry.get("owner") else None,
                    confidence=confidence,
                    rationale=str(entry.get("rationale")) if entry.get("rationale") else None,
                    related_failure_modes=related,
                )
            )

        failure_modes = tuple(str(item) for item in (raw.get("failure_modes") or []))

        # Parse artifact_id for backward compatibility (legacy artifacts without it)
        artifact_id_value = raw.get("artifact_id")
        parsed_artifact_id: str | None = None
        if artifact_id_value is not None and isinstance(artifact_id_value, str) and artifact_id_value:
            parsed_artifact_id = artifact_id_value

        return cls(
            run_id=str(raw.get("run_id") or ""),
            timestamp=ensure_utc(datetime.fromisoformat(str(raw.get("timestamp") or datetime.now(UTC).isoformat()))),
            selected_drilldowns=selections,
            quality_summary=metrics,
            failure_modes=failure_modes,
            proposed_improvements=tuple(improvements),
            review_version=str(raw.get("review_version") or "health-review:v1"),
            artifact_id=parsed_artifact_id,
        )


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
        timestamp=datetime.now(UTC),
        selected_drilldowns=selections,
        quality_summary=metrics,
        failure_modes=tuple(mode.value for mode in failure_modes),
        proposed_improvements=improvements,
        artifact_id=new_artifact_id(),
    )
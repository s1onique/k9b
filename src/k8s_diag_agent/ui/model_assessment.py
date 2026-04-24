"""Assessment view model helpers and dataclasses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_primitives import (
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class AssessmentFindingView:
    description: str
    layer: str
    supporting_signals: tuple[str, ...]


@dataclass(frozen=True)
class AssessmentHypothesisView:
    description: str
    confidence: str
    probable_layer: str
    what_would_falsify: str


@dataclass(frozen=True)
class AssessmentNextCheckView:
    description: str
    owner: str
    method: str
    evidence_needed: tuple[str, ...]


@dataclass(frozen=True)
class RecommendedActionView:
    action_type: str
    description: str
    references: tuple[str, ...]
    safety_level: str


@dataclass(frozen=True)
class AssessmentView:
    cluster_label: str
    context: str
    timestamp: str
    health_rating: str
    missing_evidence: tuple[str, ...]
    findings: tuple[AssessmentFindingView, ...]
    hypotheses: tuple[AssessmentHypothesisView, ...]
    next_checks: tuple[AssessmentNextCheckView, ...]
    recommended_action: RecommendedActionView | None
    probable_layer: str | None
    overall_confidence: str | None
    artifact_path: str | None
    snapshot_path: str | None


def _build_assessment_view(raw: object | None) -> AssessmentView | None:
    if not isinstance(raw, Mapping):
        return None
    return AssessmentView(
        cluster_label=_coerce_str(raw.get("cluster_label")),
        context=_coerce_str(raw.get("context")),
        timestamp=_coerce_str(raw.get("timestamp")),
        health_rating=_coerce_str(raw.get("health_rating")),
        missing_evidence=_coerce_sequence(raw.get("missing_evidence")),
        findings=_build_assessment_findings(raw.get("findings")),
        hypotheses=_build_assessment_hypotheses(raw.get("hypotheses")),
        next_checks=_build_assessment_next_checks(raw.get("next_evidence_to_collect")),
        recommended_action=_build_recommended_action(raw.get("recommended_action")),
        probable_layer=_coerce_optional_str(raw.get("probable_layer_of_origin")),
        overall_confidence=_coerce_optional_str(raw.get("overall_confidence")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
        snapshot_path=_coerce_optional_str(raw.get("snapshot_path")),
    )


def _build_assessment_findings(raw: object | None) -> tuple[AssessmentFindingView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentFindingView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentFindingView(
                description=_coerce_str(entry.get("description")),
                layer=_coerce_str(entry.get("layer")),
                supporting_signals=_coerce_sequence(entry.get("supporting_signals")),
            )
        )
    return tuple(entries)


def _build_assessment_hypotheses(raw: object | None) -> tuple[AssessmentHypothesisView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentHypothesisView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentHypothesisView(
                description=_coerce_str(entry.get("description")),
                confidence=_coerce_str(entry.get("confidence")),
                probable_layer=_coerce_str(entry.get("probable_layer")),
                what_would_falsify=_coerce_str(entry.get("what_would_falsify")),
            )
        )
    return tuple(entries)


def _build_assessment_next_checks(raw: object | None) -> tuple[AssessmentNextCheckView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentNextCheckView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentNextCheckView(
                description=_coerce_str(entry.get("description")),
                owner=_coerce_str(entry.get("owner")),
                method=_coerce_str(entry.get("method")),
                evidence_needed=_coerce_sequence(entry.get("evidence_needed")),
            )
        )
    return tuple(entries)


def _build_recommended_action(raw: object | None) -> RecommendedActionView | None:
    if not isinstance(raw, Mapping):
        return None
    return RecommendedActionView(
        action_type=_coerce_str(raw.get("type")),
        description=_coerce_str(raw.get("description")),
        references=_coerce_sequence(raw.get("references")),
        safety_level=_coerce_str(raw.get("safety_level")),
    )

"""Summary/rating/layer derivation helpers for health assessment building."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Layer, SafetyLevel, Signal
from .loop_history import HealthRating

__all__ = [
    "AssessmentSummaryDecision",
    "derive_assessment_summary",
    "pick_dominant_layer_from_signals",
]


@dataclass(frozen=True)
class AssessmentSummaryDecision:
    """Result of final summary derivation for a health assessment."""

    rating: HealthRating
    dominant_layer: Layer | None
    safety_level: SafetyLevel
    references: tuple[str, ...]


def pick_dominant_layer_from_signals(signals: list[Signal]) -> Layer | None:
    """Pick the dominant layer from the highest-severity signal.

    Severity ranking (highest to lowest): high > medium > low.

    Returns the layer of the signal with the highest severity,
    or None if signals list is empty.
    """
    if not signals:
        return None
    ranking = {"high": 0, "medium": 1, "low": 2}
    best = min(signals, key=lambda signal: ranking.get(signal.severity, 2))
    return best.layer


def derive_assessment_summary(
    *,
    signals: list[Signal],
    issues_detected: bool,
    workload_issue_present: bool,
    node_issue_present: bool,
    references: list[str],
    helm_error: str | None = None,
    has_missing_evidence: bool = False,
    has_image_pull_secret_insight: bool = False,
    pattern_refs: list[str] | None = None,
) -> AssessmentSummaryDecision:
    """Derive the final summary components for a health assessment.

    This function extracts summary/rating/layer derivation logic from
    build_health_assessment(). It determines the health rating, dominant
    layer from signals, safety level, and finalizes references.

    Args:
        signals: List of collected signals for this assessment.
        issues_detected: Whether any health issues were detected.
        workload_issue_present: Whether a workload-level issue was detected.
        node_issue_present: Whether a node-level issue was detected.
        references: Accumulated reference strings (may include duplicates).
        helm_error: Helm collection error string, if any.
        has_missing_evidence: Whether any evidence is missing.
        has_image_pull_secret_insight: Whether image pull secret insight exists.
        pattern_refs: Pattern-matched reference strings.

    Returns:
        AssessmentSummaryDecision with rating, dominant layer, safety level,
        and deduplicated references.
    """
    # Derive rating
    rating = HealthRating.DEGRADED if issues_detected else HealthRating.HEALTHY

    # Derive dominant layer from signals
    dominant_layer = pick_dominant_layer_from_signals(signals)

    # Derive safety level
    if issues_detected:
        safety_level = SafetyLevel.LOW_RISK
    else:
        safety_level = SafetyLevel.OBSERVE_ONLY

    # Finalize references (mutates the passed list; we copy before dedup)
    refs = list(references)
    if helm_error:
        refs.append("helm collection error")
    if has_missing_evidence:
        refs.append("missing evidence")
    if has_image_pull_secret_insight:
        refs.append("image pull secret supply chain")
    if pattern_refs:
        refs.extend(pattern_refs)
    if not refs:
        refs.append("routine health monitoring")
    # Deduplicate while preserving order
    final_refs = list(dict.fromkeys(refs))

    return AssessmentSummaryDecision(
        rating=rating,
        dominant_layer=dominant_layer,
        safety_level=safety_level,
        references=tuple(final_refs),
    )

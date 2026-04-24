"""View models for feedback and adaptation provenance (UI layer)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_str_tuple,
)


@dataclass(frozen=True)
class FeedbackSummaryView:
    """Structured feedback summary for provenance display.

    Canonical shape for feedbackSummary across planner → backend → API → frontend.
    Supports structured input (current) and legacy string input (backward compat).
    """
    total_entries: int = 0
    namespaces_with_feedback: tuple[str, ...] = field(default_factory=tuple)
    clusters_with_feedback: tuple[str, ...] = field(default_factory=tuple)
    services_with_feedback: tuple[str, ...] = field(default_factory=tuple)
    # Legacy fallback: preserved text when input was a legacy string
    summary_text: str | None = None


@dataclass(frozen=True)
class FeedbackAdaptationProvenanceView:
    """View model for feedback adaptation provenance tracking."""
    feedback_adaptation: bool
    adaptation_reason: str | None = None
    original_bonus: int = 0
    suppressed_bonus: int = 0
    penalty_applied: int = 0
    explanation: str | None = None
    feedback_summary: FeedbackSummaryView | None = None


def _build_feedback_summary_view(raw: object | None) -> FeedbackSummaryView | None:
    """Build FeedbackSummaryView from raw JSON data (structured feedback_summary)."""
    if not isinstance(raw, Mapping):
        return None
    return FeedbackSummaryView(
        total_entries=_coerce_int(raw.get("total_entries") or raw.get("totalEntries") or 0),
        namespaces_with_feedback=_coerce_str_tuple(
            raw.get("namespaces_with_feedback") or raw.get("namespacesWithFeedback")
        ),
        clusters_with_feedback=_coerce_str_tuple(
            raw.get("clusters_with_feedback") or raw.get("clustersWithFeedback")
        ),
        services_with_feedback=_coerce_str_tuple(
            raw.get("services_with_feedback") or raw.get("servicesWithFeedback")
        ),
    )


def _build_feedback_adaptation_provenance_view(
    raw: object | None,
) -> FeedbackAdaptationProvenanceView | None:
    """Build FeedbackAdaptationProvenanceView from raw JSON data.
    
    Handles both:
    - Structured shape (current): feedback_summary is an object with fields
    - Legacy string shape (backward compat): feedback_summary is a string
    """
    if not isinstance(raw, Mapping):
        return None
    
    # Parse feedback_summary - handle both structured object and legacy string
    feedback_summary_raw = raw.get("feedback_summary") or raw.get("feedbackSummary")
    feedback_summary: FeedbackSummaryView | None = None
    if feedback_summary_raw is not None:
        if isinstance(feedback_summary_raw, Mapping):
            # Structured shape (current)
            feedback_summary = _build_feedback_summary_view(feedback_summary_raw)
        elif isinstance(feedback_summary_raw, str) and feedback_summary_raw.strip():
            # Legacy string shape - preserve the original text in summary_text field
            feedback_summary = FeedbackSummaryView(summary_text=feedback_summary_raw.strip())
    
    return FeedbackAdaptationProvenanceView(
        feedback_adaptation=bool(raw.get("feedbackAdaptation") or raw.get("feedback_adaptation")),
        adaptation_reason=_coerce_optional_str(raw.get("adaptationReason") or raw.get("adaptation_reason")),
        original_bonus=_coerce_int(raw.get("originalBonus") or raw.get("original_bonus") or 0),
        suppressed_bonus=_coerce_int(raw.get("suppressedBonus") or raw.get("suppressed_bonus") or 0),
        penalty_applied=_coerce_int(raw.get("penaltyApplied") or raw.get("penalty_applied") or 0),
        explanation=_coerce_optional_str(raw.get("explanation")),
        feedback_summary=feedback_summary,
    )

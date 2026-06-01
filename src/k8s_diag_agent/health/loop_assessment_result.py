"""Final health assessment result assembly helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import Assessment
from .loop_history import HealthRating

if TYPE_CHECKING:
    from .loop import HealthAssessmentResult


__all__ = [
    "build_health_assessment_result",
]


def build_health_assessment_result(
    *,
    assessment: Assessment,
    rating: HealthRating,
    missing_evidence: tuple[str, ...],
    node_count: int,
    pod_count: int | None,
    control_plane_version: str,
    pattern_reasons: tuple[str, ...],
    pattern_metadata: dict[str, tuple[str, ...]],
) -> HealthAssessmentResult:
    """Build the final health assessment result payload.

    This helper extracts only the pure object assembly of the result.
    All signal processing, finding construction, hypothesis aggregation,
    next-check assembly, and action construction remain in the orchestrator.
    """
    # Import here to avoid circular import; the type annotation uses TYPE_CHECKING
    from .loop import HealthAssessmentResult  # noqa: F401

    return HealthAssessmentResult(
        assessment=assessment,
        rating=rating,
        missing_evidence=missing_evidence,
        node_count=node_count,
        pod_count=pod_count,
        control_plane_version=control_plane_version,
        pattern_reasons=pattern_reasons,
        pattern_metadata=pattern_metadata,
    )

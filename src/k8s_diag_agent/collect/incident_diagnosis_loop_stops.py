"""Stop condition checkers for incident diagnosis loop.

This module contains pure stop-condition checking functions.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .incident_diagnosis_loop_models import (
    Confidence,
    LoopState,
    RootCauseCandidate,
)

# =============================================================================
# Stop Condition Helpers
# =============================================================================


def _check_root_cause_credible(
    candidate: RootCauseCandidate | None,
) -> bool:
    """Check if root-cause candidate meets credibility criteria."""
    if candidate is None:
        return False
    return candidate.credible


def build_root_cause_candidate(
    diagnosis_report: Mapping[str, Any],
    *,
    min_high_confidence_evidence: int = 1,
    max_missing_evidence: int = 2,
) -> RootCauseCandidate | None:
    """Build root-cause candidate from diagnosis report.

    Args:
        diagnosis_report: The diagnosis report from build_incident_diagnosis()
        min_high_confidence_evidence: Minimum evidence for high confidence
        max_missing_evidence: Maximum missing evidence for credible

    Returns:
        RootCauseCandidate or None if no likely causes
    """
    diagnosis = diagnosis_report.get("diagnosis", {})
    likely_causes = diagnosis.get("likely_causes", [])
    supporting_evidence = diagnosis.get("supporting_evidence", [])
    uncertainties = diagnosis.get("uncertainties", [])
    confidence_str = diagnosis.get("confidence", "unknown")

    try:
        confidence = Confidence(confidence_str)
    except ValueError:
        confidence = Confidence.UNKNOWN

    # Determine credible based on deterministic criteria
    credible = (
        confidence == Confidence.HIGH
        and len(supporting_evidence) >= min_high_confidence_evidence
        and len(uncertainties) <= max_missing_evidence
    )

    # Build summary from likely causes
    summary = ""
    if likely_causes:
        if isinstance(likely_causes, list) and likely_causes:
            summary = "; ".join(str(c) for c in likely_causes[:3])
        else:
            summary = str(likely_causes)

    # Convert to tuples
    supporting_tuple = tuple(str(e) for e in supporting_evidence) if supporting_evidence else ()
    missing_tuple = tuple(str(u) for u in uncertainties) if uncertainties else ()

    return RootCauseCandidate(
        summary=summary,
        confidence=confidence,
        supporting_evidence=supporting_tuple,
        missing_evidence=missing_tuple,
        credible=credible,
    )


def check_root_cause_found(
    root_cause: RootCauseCandidate | None,
) -> bool:
    """Check if credible root cause is found."""
    return _check_root_cause_credible(root_cause)


def check_budget_exhausted(state: LoopState) -> bool:
    """Check if pass budget is exhausted."""
    current: int = state.pass_budget["current_pass"]
    maximum: int = state.pass_budget["max_passes"]
    return bool(current >= maximum)


def check_no_checks_proposed(
    proposals: Sequence[Mapping[str, object]],
) -> bool:
    """Check if no checks were proposed."""
    return len(proposals) == 0


def check_no_safe_checks(
    proposals: Sequence[Mapping[str, object]],
    validation_results: Sequence[Any],
) -> bool:
    """Check if all proposed checks were rejected."""
    if not proposals:
        return False
    # All proposals were rejected
    return all(not r.accepted for r in validation_results)


def check_low_confidence_no_progress(
    root_cause: RootCauseCandidate | None,
    prior_pass_count: int,
) -> bool:
    """Check if low confidence with no progress after multiple passes.

    Args:
        root_cause: Current root cause candidate
        prior_pass_count: Number of prior passes

    Returns:
        True if low confidence with no progress
    """
    if root_cause is None:
        return prior_pass_count >= 2

    # Low confidence and no supporting evidence after multiple passes
    if root_cause.confidence in (Confidence.LOW, Confidence.UNKNOWN):
        return prior_pass_count >= 2 and len(root_cause.supporting_evidence) == 0

    return False


def check_safety_blocked(
    proposals: Sequence[Mapping[str, object]],
    validation_results: Sequence[Any],
) -> bool:
    """Check if any safety-blocked rejections occurred."""
    for result in validation_results:
        if not result.accepted and result.safety_blocked:
            return True
    return False


__all__ = [
    "build_root_cause_candidate",
    "check_root_cause_found",
    "check_budget_exhausted",
    "check_no_checks_proposed",
    "check_no_safe_checks",
    "check_low_confidence_no_progress",
    "check_safety_blocked",
]

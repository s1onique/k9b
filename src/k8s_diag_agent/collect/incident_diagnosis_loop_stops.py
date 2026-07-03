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


# Default required root-cause terms (P4c scheduling scenario)
# These can be overridden via StopAcceptancePolicy for other scenarios
DEFAULT_REQUIRED_ROOT_CAUSE_TERMS: tuple[str, ...] = (
    "shipping",
    "nodeSelector",
    "k9b.dev/otel-lab-node",
)

# Default scheduling failure evidence markers
DEFAULT_SCHEDULING_FAILURE_MARKERS: tuple[str, ...] = (
    "FailedScheduling",
    "Unschedulable",
    "no matching node",
    "cannot schedule",
    "unschedulable",
)


def build_normalized_diagnosis_text(
    diagnosis_data: Mapping[str, Any],
    root_cause_candidate: RootCauseCandidate | None,
) -> str:
    """Build normalized text from all diagnosis fields for stop acceptance check.

    Aggregates text from all relevant diagnosis fields to avoid false negatives
    when root-cause evidence appears in fields other than likely_causes.

    Args:
        diagnosis_data: Diagnosis data from the diagnosis report
        root_cause_candidate: Root cause candidate if available

    Returns:
        Normalized text blob containing all relevant diagnosis text
    """
    parts: list[str] = []

    # 1. summary field
    summary = diagnosis_data.get("summary")
    if summary:
        parts.append(str(summary))

    # 2. likely_causes (primary source)
    likely_causes = diagnosis_data.get("likely_causes", [])
    if likely_causes and isinstance(likely_causes, list):
        for cause in likely_causes[:3]:  # Limit to first 3 for determinism
            parts.append(str(cause))

    # 3. supporting_evidence
    supporting = diagnosis_data.get("supporting_evidence", [])
    if supporting and isinstance(supporting, list):
        for evidence in supporting[:5]:  # Limit to first 5
            parts.append(str(evidence))

    # 4. scheduling_evidence (from enhanced LLM prompt)
    scheduling = diagnosis_data.get("scheduling_evidence", [])
    if scheduling and isinstance(scheduling, list):
        for s in scheduling[:5]:
            parts.append(str(s))

    # 5. proposed_operator_action (from enhanced LLM prompt)
    proposed_action = diagnosis_data.get("proposed_operator_action")
    if proposed_action:
        parts.append(str(proposed_action))

    # 6. action_rationale (from enhanced LLM prompt)
    action_rationale = diagnosis_data.get("action_rationale")
    if action_rationale:
        parts.append(str(action_rationale))

    # 7. uncertainties (may contain diagnostic hints)
    uncertainties = diagnosis_data.get("uncertainties", [])
    if uncertainties and isinstance(uncertainties, list):
        for u in uncertainties[:3]:
            parts.append(str(u))

    # 8. RootCauseCandidate summary if available
    if root_cause_candidate and root_cause_candidate.summary:
        parts.append(root_cause_candidate.summary)
        # Also include supporting_evidence from candidate
        for ev in root_cause_candidate.supporting_evidence[:3]:
            parts.append(str(ev))

    return " ".join(parts)


def check_root_cause_has_required_terms(
    diagnosis_text: str,
    *,
    required_terms: tuple[str, ...] = DEFAULT_REQUIRED_ROOT_CAUSE_TERMS,
) -> bool:
    """Check if diagnosis text contains required scheduling terms.

    For P4c multipass diagnosis, the diagnosis text MUST include
    concrete evidence of the scheduling failure before accepting
    stop_no_checks_proposed.

    Args:
        diagnosis_text: Normalized diagnosis text from all fields
        required_terms: Terms that must be present (default: scheduling incident terms)

    Returns:
        True if all required terms are present
    """
    if not diagnosis_text:
        return False
    text_lower = diagnosis_text.lower()
    return all(term.lower() in text_lower for term in required_terms)


def check_root_cause_has_scheduling_evidence(
    diagnosis_text: str,
    *,
    markers: tuple[str, ...] = DEFAULT_SCHEDULING_FAILURE_MARKERS,
) -> bool:
    """Check if diagnosis text contains scheduling failure evidence.

    Args:
        diagnosis_text: Normalized diagnosis text from all fields
        markers: Evidence markers to check for

    Returns:
        True if any scheduling evidence marker is present
    """
    if not diagnosis_text:
        return False
    text_lower = diagnosis_text.lower()
    # Also check for "failed scheduling" variations
    has_failed_scheduling = "failed scheduling" in text_lower or "failedscheduling" in text_lower
    return has_failed_scheduling or any(marker.lower() in text_lower for marker in markers)


def check_proposed_operator_action_present(
    diagnosis_data: Mapping[str, Any],
) -> bool:
    """Check if a proposed operator action is present in diagnosis.

    For P4c, stopping with no checks is only acceptable when the diagnosis
    includes a proposed remediation command for human review.

    Args:
        diagnosis_data: Diagnosis data from the diagnosis report

    Returns:
        True if proposed_operator_action is present and marked as review-only
    """
    proposed_action = diagnosis_data.get("proposed_operator_action")
    if not proposed_action:
        return False

    # Check action_is_review_only flag
    is_review_only = diagnosis_data.get("action_is_review_only", False)
    return is_review_only is True


def check_stop_no_checks_proposed_acceptable(
    proposals: Sequence[Mapping[str, object]],
    root_cause_candidate: RootCauseCandidate | None,
    root_cause_summary: str,
    *,
    diagnosis_data: Mapping[str, Any] | None = None,
    require_operator_action: bool = True,
    required_terms: tuple[str, ...] = DEFAULT_REQUIRED_ROOT_CAUSE_TERMS,
    scheduling_markers: tuple[str, ...] = DEFAULT_SCHEDULING_FAILURE_MARKERS,
) -> bool:
    """Check if stop_no_checks_proposed is acceptable.

    For P4c multipass diagnosis, stopping with no new checks is only
    acceptable when:
    1. No new checks are proposed (proposals is empty)
    2. Diagnosis text (from all fields) contains required scheduling terms
    3. Diagnosis text has scheduling failure evidence
    4. (Optional) Proposed operator action is present and review-only

    This prevents premature termination before the diagnosis reaches
    a complete root-cause understanding with operator action proposal.

    Args:
        proposals: Proposed next checks
        root_cause_candidate: Root cause candidate from diagnosis
        root_cause_summary: Root cause summary text (from likely_causes)
        diagnosis_data: Full diagnosis data for normalized text aggregation
        require_operator_action: If True, require proposed_operator_action
        required_terms: Terms that must be present
        scheduling_markers: Scheduling evidence markers

    Returns:
        True if stop_no_checks_proposed is acceptable
    """
    # First check: no proposals
    if len(proposals) > 0:
        return False

    # Build normalized text from all diagnosis fields
    if diagnosis_data is not None:
        normalized_text = build_normalized_diagnosis_text(diagnosis_data, root_cause_candidate)
    else:
        # Fallback to likely_causes summary only
        normalized_text = root_cause_summary

    # Second check: required terms present
    if not check_root_cause_has_required_terms(
        normalized_text,
        required_terms=required_terms,
    ):
        return False

    # Third check: scheduling evidence present
    if not check_root_cause_has_scheduling_evidence(
        normalized_text,
        markers=scheduling_markers,
    ):
        return False

    # Fourth check: operator action present (if required)
    if require_operator_action:
        if diagnosis_data is not None:
            if not check_proposed_operator_action_present(diagnosis_data):
                return False
        else:
            # If no diagnosis_data, cannot verify operator action
            return False

    return True


def check_no_checks_proposed(
    proposals: Sequence[Mapping[str, object]],
) -> bool:
    """Check if no checks were proposed.

    Note: For P4c multipass diagnosis, use check_stop_no_checks_proposed_acceptable()
    instead, which also validates root cause quality.
    """
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

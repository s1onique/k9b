"""Ranking and Alertmanager-adjusted prioritization for next check planner.

Alertmanager-specific helpers are in next_check_planner_alertmanager.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..external_analysis.artifact import ReviewStage, Workstream
from .alertmanager_feedback import (
    RunScopedAlertmanagerFeedback,
    compute_feedback_adjusted_bonus,
)
from .next_check_planner_alertmanager import (
    _ALERTMANAGER_CLUSTER_MATCH_BONUS,
    _ALERTMANAGER_NAMESPACE_MATCH_BONUS,
    _ALERTMANAGER_SERVICE_MATCH_BONUS,
    AlertmanagerRankingSignal,
    _build_alertmanager_rationale,
    _compute_alertmanager_bonus,
    build_alertmanager_provenance,
)
from .next_check_planner_candidates import NextCheckCandidate
from .next_check_planner_models import (
    CommandFamily,
    CostEstimate,
)

if TYPE_CHECKING:
    from .next_check_planner_models import AlertmanagerRankingProvenance

# Context-gated ranking penalty for kubectl-get-crd in early incident triage.
# Evidence: usefulness learning report shows kubectl-get-crd performs poorly in
# incident + initial_triage but well in parity_validation + drift contexts.
# This penalty ensures targeted diagnostics outrank broad CRD inventory in early triage.
_CRD_DEMOTION_IN_EARLY_INCIDENT_PENALTY = -120


def _is_early_incident_triage(workstream: Workstream | None, review_stage: ReviewStage | None) -> bool:
    """Detect early incident triage context where CRD checks should be demoted.
    
    Evidence: kubectl-get-crd performs poorly in incident + initial_triage
    but well in parity_validation + drift contexts.
    """
    return (
        workstream == Workstream.INCIDENT
        and review_stage == ReviewStage.INITIAL_TRIAGE
    )


def _compute_candidate_sort_score(
    candidate: NextCheckCandidate,
    workstream: Workstream | None = None,
    review_stage: ReviewStage | None = None,
    alertmanager_signal: AlertmanagerRankingSignal | None = None,
    alertmanager_feedback: RunScopedAlertmanagerFeedback | None = None,
) -> tuple[int, bool, int, bool, bool, bool]:
    """Compute ranking score for a candidate.
    
    Returns tuple of:
    - score (int): final computed score
    - crd_demotion_applied (bool): whether CRD demotion was applied
    - alertmanager_bonus (int): Alertmanager bonus applied (0 if none)
    - am_ns_match (bool): namespace match occurred
    - am_cluster_match (bool): cluster match occurred
    - am_service_match (bool): service match occurred
    
    Note: feedback-based suppression is applied later in rank_candidates
    to preserve provenance tracking.
    """
    score = 0
    crd_demotion_applied = False
    alertmanager_bonus = 0
    am_ns_match = False
    am_cluster_match = False
    am_service_match = False
    
    if candidate.target_cluster:
        score += 250
    if candidate.suggested_command_family != CommandFamily.UNKNOWN:
        score += 150
    if candidate.safe_to_automate:
        score += 120
    cost_score = {
        CostEstimate.LOW: 40,
        CostEstimate.MEDIUM: 20,
        CostEstimate.HIGH: 5,
    }
    score += cost_score.get(candidate.estimated_cost, 0)
    if candidate.expected_signal:
        score += 40
    if candidate.duplicate_of_existing_evidence:
        score -= 160
    # Generic candidate penalty: low-specificity suggestions from model should be demoted
    if candidate.generic_candidate:
        score -= 80
    # Context-gated CRD demotion: apply penalty only in early incident triage
    # Evidence: kubectl-get-crd is low-yield in incident + initial_triage
    if (
        candidate.suggested_command_family == CommandFamily.KUBECTL_GET_CRD
        and _is_early_incident_triage(workstream, review_stage)
    ):
        score += _CRD_DEMOTION_IN_EARLY_INCIDENT_PENALTY
        crd_demotion_applied = True
    
    # Alertmanager-influenced bonus: apply if signal is available
    if alertmanager_signal is not None:
        bonus, ns_match, cluster_match, service_match = _compute_alertmanager_bonus(
            candidate, alertmanager_signal
        )
        if bonus > 0:
            score += bonus
            alertmanager_bonus = bonus
            am_ns_match = ns_match
            am_cluster_match = cluster_match
            am_service_match = service_match
    
    return score, crd_demotion_applied, alertmanager_bonus, am_ns_match, am_cluster_match, am_service_match


def rank_candidates(
    candidates: Sequence[NextCheckCandidate],
    workstream: Workstream | None = None,
    review_stage: ReviewStage | None = None,
    alertmanager_signal: AlertmanagerRankingSignal | None = None,
    alertmanager_feedback: RunScopedAlertmanagerFeedback | None = None,
) -> tuple[NextCheckCandidate, ...]:
    """Rank candidates and attach ranking policy reasons and provenance for observability.
    
    Args:
        candidates: Sequence of candidates to rank
        workstream: Workstream context for CRD demotion
        review_stage: Review stage for CRD demotion
        alertmanager_signal: Optional Alertmanager ranking signal for bonus computation.
            If None, ranking proceeds without Alertmanager influence.
            No live Alertmanager fetch is performed - only run-scoped context is used.
        alertmanager_feedback: Optional run-scoped Alertmanager feedback for demoting
            similar candidates that the operator marked as not relevant or noisy.
            If None, no feedback-based demotion is applied.
            All adaptation is run-scoped only - no cross-run persistence.
    """
    # Track feedback adjustments for provenance
    feedback_adjustments: dict[str, tuple[int, str | None, dict[str, Any] | None]] = {}
    
    # First pass: compute base scores
    scored: list[tuple[int, NextCheckCandidate, bool, int, str | None, bool, bool, bool]] = []
    for candidate in candidates:
        score, demotion_applied, am_bonus, am_ns_match, am_cluster_match, am_service_match = _compute_candidate_sort_score(
            candidate, workstream, review_stage, alertmanager_signal
        )
        
        # Apply feedback-based bonus suppression if feedback is available
        final_bonus = am_bonus
        if am_bonus > 0 and alertmanager_feedback is not None and alertmanager_feedback.feedback_entries:
            suppressed_bonus, adaptation_rationale, adaptation_provenance = compute_feedback_adjusted_bonus(
                am_bonus,
                candidate.target_cluster,
                candidate.target_context,
                candidate.description,
                alertmanager_feedback,
            )
            if suppressed_bonus != am_bonus and adaptation_rationale:
                # Score was adjusted - update score and track for provenance
                score = score - am_bonus + suppressed_bonus
                final_bonus = suppressed_bonus
                feedback_adjustments[candidate.candidate_id] = (
                    suppressed_bonus,
                    adaptation_rationale,
                    adaptation_provenance,
                )
        
        # Build ranking policy reason
        ranking_reason: str | None = None
        if demotion_applied:
            ranking_reason = f"crd-demoted-early-incident-triage:{workstream.value if workstream else 'none'}:{review_stage.value if review_stage else 'none'}"
        elif candidate.candidate_id in feedback_adjustments:
            # Feedback suppressed the bonus - update the rationale
            ranking_reason = feedback_adjustments[candidate.candidate_id][1]
        elif am_bonus > 0 and alertmanager_signal is not None:
            ranking_reason = _build_alertmanager_rationale(am_ns_match, am_cluster_match, am_service_match, alertmanager_signal)
        
        scored.append((score, candidate, demotion_applied, final_bonus, ranking_reason, am_ns_match, am_cluster_match, am_service_match))
    
    # Sort by score (descending) then by description (ascending) for determinism
    scored.sort(key=lambda entry: (-entry[0], entry[1].description))
    
    # Reconstruct candidates with ranking policy reason and provenance if any policy was applied
    ranked: list[NextCheckCandidate] = []
    for score, candidate, demotion_applied, am_bonus, ranking_reason, am_ns_match, am_cluster_match, am_service_match in scored:
        provenance: AlertmanagerRankingProvenance | None = None
        feedback_provenance: dict[str, Any] | None = None
        if am_bonus > 0 and alertmanager_signal is not None and (am_ns_match or am_cluster_match or am_service_match):
            # Compute base bonus (before severity adjustment) for provenance
            base_bonus = 0
            if am_ns_match:
                base_bonus += _ALERTMANAGER_NAMESPACE_MATCH_BONUS
            if am_cluster_match:
                base_bonus += _ALERTMANAGER_CLUSTER_MATCH_BONUS
            if am_service_match:
                base_bonus += _ALERTMANAGER_SERVICE_MATCH_BONUS
            
            provenance = build_alertmanager_provenance(
                am_ns_match, am_cluster_match, am_service_match,
                base_bonus, am_bonus, alertmanager_signal
            )
        
        # Add feedback provenance if this candidate was adjusted
        if candidate.candidate_id in feedback_adjustments:
            feedback_provenance = feedback_adjustments[candidate.candidate_id][2]
        
        if ranking_reason is not None or provenance is not None or feedback_provenance is not None:
            # Create new candidate with ranking policy reason and provenance set
            ranked.append(
                NextCheckCandidate(
                    candidate_id=candidate.candidate_id,
                    description=candidate.description,
                    target_cluster=candidate.target_cluster,
                    target_context=candidate.target_context,
                    source_reason=candidate.source_reason,
                    expected_signal=candidate.expected_signal,
                    suggested_command_family=candidate.suggested_command_family,
                    safe_to_automate=candidate.safe_to_automate,
                    requires_operator_approval=candidate.requires_operator_approval,
                    risk_level=candidate.risk_level,
                    estimated_cost=candidate.estimated_cost,
                    confidence=candidate.confidence,
                    gating_reason=candidate.gating_reason,
                    duplicate_of_existing_evidence=candidate.duplicate_of_existing_evidence,
                    duplicate_evidence_description=candidate.duplicate_evidence_description,
                    normalization_reason=candidate.normalization_reason,
                    safety_reason=candidate.safety_reason,
                    approval_reason=candidate.approval_reason,
                    duplicate_reason=candidate.duplicate_reason,
                    blocking_reason=candidate.blocking_reason,
                    priority_label=candidate.priority_label,
                    generic_candidate=candidate.generic_candidate,
                    ranking_policy_reason=ranking_reason,
                    alertmanager_provenance=provenance,
                    feedback_adaptation_provenance=feedback_provenance,
                )
            )
        else:
            ranked.append(candidate)
    return tuple(ranked)


# Backward-compatible alias for tests and callers
_rank_candidates = rank_candidates

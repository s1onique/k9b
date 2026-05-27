"""Ranking and Alertmanager-adjusted prioritization for next check planner."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..external_analysis.artifact import ReviewStage, Workstream
from .alertmanager_feedback import (
    RunScopedAlertmanagerFeedback,
    compute_feedback_adjusted_bonus,
)
from .next_check_planner_candidates import NextCheckCandidate
from .next_check_planner_models import (
    CommandFamily,
    CostEstimate,
)
from .review_input import AlertmanagerContext

if TYPE_CHECKING:
    from .next_check_planner_models import AlertmanagerRankingProvenance

# Context-gated ranking penalty for kubectl-get-crd in early incident triage.
# Evidence: usefulness learning report shows kubectl-get-crd performs poorly in
# incident + initial_triage but well in parity_validation + drift contexts.
# This penalty ensures targeted diagnostics outrank broad CRD inventory in early triage.
_CRD_DEMOTION_IN_EARLY_INCIDENT_PENALTY = -120

# Alertmanager-influenced ranking bonus values.
# These are conservative, additive bonuses - not overrides.
_ALERTMANAGER_NAMESPACE_MATCH_BONUS = 80
_ALERTMANAGER_CLUSTER_MATCH_BONUS = 60
_ALERTMANAGER_SERVICE_MATCH_BONUS = 50

# Maximum cumulative Alertmanager bonus to prevent any single signal dominating.
_ALERTMANAGER_MAX_CUMULATIVE_BONUS = 150


@dataclass(frozen=True)
class AlertmanagerRankingSignal:
    """Structured signal extracted from Alertmanager compact for ranking purposes."""
    available: bool
    affected_namespaces: tuple[str, ...]
    affected_clusters: tuple[str, ...]
    affected_services: tuple[str, ...]
    status: str | None
    # Severity distribution for bonus tuning. Maps severity name to count.
    severity_counts: tuple[tuple[str, int], ...]

    @classmethod
    def from_alertmanager_context(cls, ctx: AlertmanagerContext) -> AlertmanagerRankingSignal:
        """Extract ranking-relevant signal from AlertmanagerContext.
        
        Returns unavailable signal if context is unavailable or status indicates no active alerts.
        No live Alertmanager fetch is performed.
        """
        if not ctx.available or ctx.compact is None:
            return cls(
                available=False,
                affected_namespaces=(),
                affected_clusters=(),
                affected_services=(),
                status=None,
                severity_counts=(),
            )
        
        # Treat certain statuses as "no active alert signal" for ranking purposes
        non_actionable_statuses = {"empty", "disabled", "timeout", "upstream_error", "invalid_response"}
        status = ctx.status or "unknown"
        if status in non_actionable_statuses:
            return cls(
                available=True,
                affected_namespaces=(),
                affected_clusters=(),
                affected_services=(),
                status=status,
                severity_counts=(),
            )
        
        compact = ctx.compact
        
        # Extract affected dimensions from compact
        namespaces_raw = compact.get("affected_namespaces", [])
        namespaces: tuple[str, ...] = tuple(str(n) for n in namespaces_raw) if isinstance(namespaces_raw, (list, tuple)) else ()
        
        clusters_raw = compact.get("affected_clusters", [])
        clusters: tuple[str, ...] = tuple(str(c) for c in clusters_raw) if isinstance(clusters_raw, (list, tuple)) else ()
        
        services_raw = compact.get("affected_services", [])
        services: tuple[str, ...] = tuple(str(s) for s in services_raw) if isinstance(services_raw, (list, tuple)) else ()
        
        # Extract severity counts from compact for bonus tuning
        severity_raw = compact.get("severity_counts", {})
        severity_counts: tuple[tuple[str, int], ...] = ()
        if isinstance(severity_raw, dict):
            severity_counts = tuple(
                (str(k), int(v)) for k, v in severity_raw.items()
            )
        
        return cls(
            available=True,
            affected_namespaces=namespaces,
            affected_clusters=clusters,
            affected_services=services,
            status=status,
            severity_counts=severity_counts,
        )

    def matches_namespace(self, candidate_target_cluster: str | None, candidate_target_context: str | None) -> bool:
        """Check if candidate matches any affected namespace.
        
        Conservative matching: only match in target_context (which often contains 
        explicit namespace info like "namespace=monitoring") or when target_cluster
        appears to be a namespace-like value (e.g., exact match or namespace prefix).
        """
        if not self.available or not self.affected_namespaces:
            return False
        
        # Prefer matching in target_context which often has explicit namespace info
        if candidate_target_context:
            context_lower = candidate_target_context.lower()
            for ns in self.affected_namespaces:
                # Match explicit namespace patterns in context
                if ns.lower() in context_lower:
                    return True
                # Also match namespace=VALUE patterns
                if f"namespace={ns.lower()}" in context_lower or f"namespace: {ns.lower()}" in context_lower:
                    return True
        
        # Only check target_cluster for exact namespace matches (not substring)
        # target_cluster is often a cluster name, not a namespace
        if candidate_target_cluster:
            cluster_lower = candidate_target_cluster.lower()
            for ns in self.affected_namespaces:
                # Require more specific patterns: exact match or namespace-like prefix
                if cluster_lower == ns.lower():
                    return True
                # Allow "namespace-name" format when target looks like namespace
                if f"{ns.lower()}-" in cluster_lower or cluster_lower.startswith(f"{ns.lower()}-"):
                    return True
        
        return False

    def matches_cluster(self, candidate_target_cluster: str | None) -> bool:
        """Check if candidate target cluster matches any affected cluster.
        
        Uses substring matching because cluster names are typically unique identifiers
        that should appear in target_cluster when relevant.
        """
        if not self.available or not self.affected_clusters:
            return False
        
        if not candidate_target_cluster:
            return False
        
        cluster_lower = candidate_target_cluster.lower()
        for cluster in self.affected_clusters:
            cluster_lower_target = cluster.lower()
            if cluster_lower_target in cluster_lower or cluster_lower in cluster_lower_target:
                return True
        
        return False

    def matches_service(self, candidate_description: str | None, candidate_target_context: str | None) -> bool:
        """Check if candidate description or context mentions affected services.
        
        More conservative matching: require word-boundary or explicit service reference
        to avoid matching common words that happen to appear in descriptions.
        """
        if not self.available or not self.affected_services:
            return False
        
        if not candidate_description and not candidate_target_context:
            return False
        
        # Build search text
        text = (candidate_description or "") + " " + (candidate_target_context or "")
        text_lower = text.lower()
        
        for service in self.affected_services:
            service_lower = service.lower()
            # Match explicit service patterns: "service-name", "service_name", or "service/"
            if f"{service_lower}/" in text_lower or f"{service_lower}_" in text_lower or f"service={service_lower}" in text_lower:
                return True
            # For multi-word services, match as whole phrase
            if service_lower in text_lower:
                # Additional check: ensure it's not a substring of a larger word
                # by verifying word boundaries
                import re
                if re.search(rf'\b{re.escape(service_lower)}\b', text_lower):
                    return True
                # Also check for hyphenated service names
                if f"-{service_lower}" in text_lower or f"{service_lower}-" in text_lower:
                    return True
        
        return False


def extract_alertmanager_severity_weight(
    severity_counts: tuple[tuple[str, int], ...],
) -> float:
    """Extract a single severity weight from alert severity distribution.
    
    Uses precedence-based severity determination (not count-weighted):
    - critical present => 1.25
    - warning present => 1.0 (baseline)
    - info-only => 0.9
    - no severity data => 1.0 (baseline)
    
    No live Alertmanager fetch is performed.
    """
    if not severity_counts:
        return 1.0  # baseline when no severity info
    
    # Check for presence of severities in precedence order
    severities_present: set[str] = {sev.lower() for sev, _ in severity_counts}
    
    if "critical" in severities_present:
        return 1.25
    if "warning" in severities_present:
        return 1.0
    if "info" in severities_present:
        return 0.9
    
    return 1.0  # fallback baseline


def compute_alertmanager_match_bonus(
    ns_match: bool,
    cluster_match: bool,
    service_match: bool,
    severity_multiplier: float,
) -> int:
    """Compute the severity-adjusted Alertmanager bonus.
    
    Applies dimension bonuses first, then scales by severity multiplier.
    Hard cap of 150 prevents any single signal from dominating unrelated candidates.
    
    No live Alertmanager fetch is performed.
    """
    bonus = 0
    if ns_match:
        bonus += _ALERTMANAGER_NAMESPACE_MATCH_BONUS
    if cluster_match:
        bonus += _ALERTMANAGER_CLUSTER_MATCH_BONUS
    if service_match:
        bonus += _ALERTMANAGER_SERVICE_MATCH_BONUS
    
    if bonus == 0:
        return 0
    
    # Apply severity multiplier (requires a real match first)
    adjusted = int(bonus * severity_multiplier)
    
    # Hard cap to prevent any single signal from dominating unrelated candidates.
    return min(adjusted, _ALERTMANAGER_MAX_CUMULATIVE_BONUS)


def _compute_alertmanager_bonus(
    candidate: NextCheckCandidate,
    signal: AlertmanagerRankingSignal,
) -> tuple[int, bool, bool, bool]:
    """Compute Alertmanager-influenced bonus for a candidate.
    
    Returns tuple of (bonus, ns_match, cluster_match, service_match).
    The bonus is bounded, severity-aware, and additive but capped.
    
    No live Alertmanager fetch is performed - only run-scoped context is used.
    """
    if not signal.available:
        return 0, False, False, False
    
    # Check for error statuses that should not trigger bonus computation
    non_actionable_statuses = {"timeout", "upstream_error", "invalid_response"}
    if signal.status in non_actionable_statuses:
        return 0, False, False, False
    
    # Check for empty signal - no active alerts to match against
    if not signal.affected_namespaces and not signal.affected_clusters and not signal.affected_services:
        return 0, False, False, False
    
    ns_match = signal.matches_namespace(candidate.target_cluster, candidate.target_context)
    cluster_match = signal.matches_cluster(candidate.target_cluster)
    service_match = signal.matches_service(candidate.description, candidate.target_context)
    
    if not (ns_match or cluster_match or service_match):
        return 0, False, False, False
    
    # Extract severity weight from alert distribution
    severity_multiplier = extract_alertmanager_severity_weight(signal.severity_counts)
    
    # Compute severity-adjusted bonus
    bonus = compute_alertmanager_match_bonus(
        ns_match, cluster_match, service_match, severity_multiplier
    )
    
    return bonus, ns_match, cluster_match, service_match


def _build_alertmanager_rationale(
    ns_match: bool,
    cluster_match: bool,
    service_match: bool,
    signal: AlertmanagerRankingSignal,
) -> str | None:
    """Build human-readable rationale for Alertmanager-influenced ranking.
    
    Returns None if no bonus was applied.
    """
    if not (ns_match or cluster_match or service_match):
        return None
    
    if not signal.available or not signal.status:
        return None
    
    # Build match description
    matches: list[str] = []
    if ns_match and signal.affected_namespaces:
        matches.append(f"namespace(s): {', '.join(signal.affected_namespaces[:3])}")
    if cluster_match and signal.affected_clusters:
        matches.append(f"cluster(s): {', '.join(signal.affected_clusters[:3])}")
    if service_match and signal.affected_services:
        matches.append(f"service(s): {', '.join(signal.affected_services[:3])}")
    
    if not matches:
        return None
    
    return f"alertmanager-context:promoted:matched {'; '.join(matches)}"


def build_alertmanager_provenance(
    ns_match: bool,
    cluster_match: bool,
    service_match: bool,
    base_bonus: int,
    applied_bonus: int,
    signal: AlertmanagerRankingSignal,
) -> AlertmanagerRankingProvenance | None:
    """Build structured Alertmanager provenance for a candidate.
    
    Returns None if no dimension match occurred (no provenance needed).
    Supports debugging, future UI use, and tuning.
    
    No live Alertmanager fetch is performed.
    """
    if not (ns_match or cluster_match or service_match):
        return None
    
    matched_dimensions: list[str] = []
    matched_values: dict[str, tuple[str, ...]] = {}
    
    if ns_match and signal.affected_namespaces:
        matched_dimensions.append("namespace")
        matched_values["namespace"] = signal.affected_namespaces
    if cluster_match and signal.affected_clusters:
        matched_dimensions.append("cluster")
        matched_values["cluster"] = signal.affected_clusters
    if service_match and signal.affected_services:
        matched_dimensions.append("service")
        matched_values["service"] = signal.affected_services
    
    # Build severity summary dict from tuple format
    severity_summary: dict[str, int] = {}
    for sev, count in signal.severity_counts:
        severity_summary[sev] = count
    
    from .next_check_planner_models import AlertmanagerRankingProvenance
    return AlertmanagerRankingProvenance(
        matched_dimensions=tuple(matched_dimensions),
        matched_values=matched_values,
        base_bonus=base_bonus,
        applied_bonus=applied_bonus,
        severity_summary=severity_summary,
        signal_status=signal.status,
    )


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
            
            # Import here to avoid circular import
            from .next_check_planner_models import AlertmanagerRankingProvenance as ProvenanceClass
            
            provenance = ProvenanceClass(
                matched_dimensions=tuple(d for d, v in [
                    ("namespace", alertmanager_signal.affected_namespaces if am_ns_match else ()),
                    ("cluster", alertmanager_signal.affected_clusters if am_cluster_match else ()),
                    ("service", alertmanager_signal.affected_services if am_service_match else ()),
                ] if v),
                matched_values={
                    "namespace": alertmanager_signal.affected_namespaces,
                    "cluster": alertmanager_signal.affected_clusters,
                    "service": alertmanager_signal.affected_services,
                },
                base_bonus=base_bonus,
                applied_bonus=am_bonus,
                severity_summary={sev: count for sev, count in alertmanager_signal.severity_counts},
                signal_status=alertmanager_signal.status,
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

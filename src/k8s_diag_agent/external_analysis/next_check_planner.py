"""Deterministic planner for provider suggested next checks."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus, ReviewStage, Workstream
from .alertmanager_feedback import (
    RunScopedAlertmanagerFeedback,
    build_feedback_from_execution_artifacts,
    compute_feedback_adjusted_bonus,
)
from .review_input import AlertmanagerContext, ReviewEnrichmentInput, ReviewSelectionContext, build_review_enrichment_input


class CommandFamily(StrEnum):
    KUBECTL_GET = "kubectl-get"
    KUBECTL_DESCRIBE = "kubectl-describe"
    KUBECTL_LOGS = "kubectl-logs"
    KUBECTL_GET_CRD = "kubectl-get-crd"
    KUBECTL_TOP = "kubectl-top"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostEstimate(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NormalizationReason(StrEnum):
    SELECTION_LABEL = "selection_label"
    SELECTION_CONTEXT = "selection_context"
    SELECTION_DEFAULT = "selection_default"
    SUMMARY_FALLBACK = "summary_fallback"
    UNKNOWN = "unknown"


class SafetyReason(StrEnum):
    KNOWN_COMMAND = "known_command"
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE_EVIDENCE = "duplicate_evidence"


class ApprovalReason(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    GENERIC = "requires_operator_approval"


class DuplicateReason(StrEnum):
    EXACT_MATCH = "exact_match"
    OVERLAP = "overlap"


class BlockingReason(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE = "duplicate"
    REQUIRES_APPROVAL = "requires_approval"
    COMMAND_NOT_ALLOWED = "command_not_allowed"
    MISSING_DESCRIPTION = "missing_description"
    MISSING_CONTEXT = "missing_context"
def _normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _match_selection_for_text(
    text: str, selections: Iterable[ReviewSelectionContext]
) -> ReviewSelectionContext | None:
    normalized = _normalize_text(text)
    for selection in selections:
        label = (selection.label or "").strip()
        context = (selection.context or "").strip()
        if label and label.lower() in normalized:
            return selection
        if context and context.lower() in normalized:
            return selection
    return next(iter(selections), None)


def detect_command_family(text: str) -> CommandFamily:
    normalized = text.lower()
    if "kubectl logs" in normalized or "logs" in normalized and "kubectl" in normalized:
        return CommandFamily.KUBECTL_LOGS
    if "kubectl describe" in normalized or "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    if "kubectl top" in normalized:
        return CommandFamily.KUBECTL_TOP
    if "kubectl get" in normalized:
        if "crd" in normalized:
            return CommandFamily.KUBECTL_GET_CRD
        return CommandFamily.KUBECTL_GET
    if "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    return CommandFamily.UNKNOWN


def detect_expected_signal(text: str) -> str | None:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ("logs", "log file", "pod logs")):
        return "logs"
    if any(keyword in normalized for keyword in ("event", "events", "warning")):
        return "events"
    if any(keyword in normalized for keyword in ("metric", "latency", "cpu", "memory", "iops")):
        return "metrics"
    if any(keyword in normalized for keyword in ("rollout", "deployment", "replica", "cronjob")):
        return "rollout"
    if any(keyword in normalized for keyword in ("storage", "pvc", "volume")):
        return "storage"
    return None


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

# Severity-aware bonus multipliers.
# These are conservative multiplicative adjustments applied on top of dimension matches.
# Require a real dimension match before severity matters (defensive by design).
_ALERTMANAGER_SEVERITY_WEIGHTS = {
    "critical": 1.25,  # modest boost for critical alerts
    "warning": 1.0,    # baseline (no change)
    "info": 0.9,        # slightly weaker lift for info-only alerts
}


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


@dataclass(frozen=True)
class AlertmanagerRankingProvenance:
    """Structured provenance for Alertmanager-driven ranking influence.
    
    Supports debugging, future UI use, and tuning.
    """
    # Dimensions that matched for this candidate
    matched_dimensions: tuple[str, ...]
    # Values that matched for each dimension
    matched_values: dict[str, tuple[str, ...]]
    # Bonus applied before severity adjustment
    base_bonus: int
    # Final bonus after severity adjustment
    applied_bonus: int
    # Severity distribution that influenced the bonus
    severity_summary: dict[str, int]
    # Signal status at time of ranking
    signal_status: str | None
    
    def to_dict(self) -> dict[str, object]:
        """Convert to serializable dict for UI/debugging."""
        return {
            "matchedDimensions": list(self.matched_dimensions),
            "matchedValues": {k: list(v) for k, v in self.matched_values.items()},
            "baseBonus": self.base_bonus,
            "appliedBonus": self.applied_bonus,
            "severitySummary": dict(self.severity_summary),
            "signalStatus": self.signal_status,
        }


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
    
    return AlertmanagerRankingProvenance(
        matched_dimensions=tuple(matched_dimensions),
        matched_values=matched_values,
        base_bonus=base_bonus,
        applied_bonus=applied_bonus,
        severity_summary=severity_summary,
        signal_status=signal.status,
    )


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

# These are kubectl verbs that are genuinely mutating and should require approval.
# Important: Order matters for the regex-based detection to avoid false positives.
# - "describe" is NOT mutating (read-only operation, used for inspection)
# - "label" and "annotate" are mutating but must be matched as whole words
MUTATION_KEYWORDS = (
    # Core mutating kubectl verbs (word-boundary matched)
    r"\bapply\b",
    r"\bdelete\b",
    r"\bscale\b",
    r"\bpatch\b",
    r"\breplace\b",
    r"\bcreate\b",
    r"\bedit\b",
    r"\blabel\b",
    r"\bannotate\b",
    # rollout is mutating when followed by certain subcommands
    r"\brollout\b",
    # cordon, uncordon, drain are mutating node operations
    r"\bcordon\b",
    r"\buncordon\b",
    r"\bdrain\b",
    # exec into pod is potentially mutating
    r"\bexec\b",
    # set commands that modify resources
    r"\bset\s+",  # e.g., kubectl set image, kubectl set env
    # port-forward is not strictly mutating but can be security-sensitive
    # upgrade is a cluster operation
    r"\bupgrade\b",
)


def _mentions_mutation(text: str) -> bool:
    normalized = text.lower()
    # Use word-boundary aware regex matching to avoid false positives
    # e.g., "describe" should NOT match "set" (it's not a mutation)
    import re as _re
    return any(_re.search(pattern, normalized) for pattern in MUTATION_KEYWORDS)


def _risk_from_family(family: CommandFamily) -> RiskLevel:
    if family in (CommandFamily.KUBECTL_LOGS, CommandFamily.KUBECTL_DESCRIBE, CommandFamily.KUBECTL_TOP):
        return RiskLevel.LOW
    if family in (CommandFamily.KUBECTL_GET, CommandFamily.KUBECTL_GET_CRD):
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _confidence_level(safe: bool, family: CommandFamily) -> str:
    if safe and family != CommandFamily.UNKNOWN:
        return "high"
    if family == CommandFamily.UNKNOWN:
        return "low"
    return "medium"


def _cost_from_risk(risk: RiskLevel) -> CostEstimate:
    if risk == RiskLevel.LOW:
        return CostEstimate.LOW
    if risk == RiskLevel.MEDIUM:
        return CostEstimate.MEDIUM
    return CostEstimate.HIGH


def _normalize_description(value: str) -> str:
    return _normalize_text(value)


def _derive_candidate_id(
    description: str,
    target_cluster: str | None,
    source_reason: str | None,
    family: CommandFamily,
) -> str:
    normalized_desc = _normalize_description(description or "")
    components = "|".join(
        (
            normalized_desc,
            target_cluster or "",
            source_reason or "",
            family.value,
        )
    )
    return sha256(components.encode("utf-8")).hexdigest()


def _collect_existing_evidence(context: ReviewEnrichmentInput) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for selection in context.selections:
        assessment = selection.assessment or {}
        next_checks = assessment.get("next_evidence_to_collect") or []
        if not isinstance(next_checks, Iterable):
            continue
        for entry in next_checks:
            if not isinstance(entry, Mapping):
                continue
            desc = entry.get("description")
            if not isinstance(desc, str):
                continue
            key = _normalize_description(desc)
            if key:
                normalized[key] = desc
    return normalized


def _find_similar_description(candidate_key: str, evidence_map: Mapping[str, str]) -> tuple[DuplicateReason | None, str | None]:
    for normalized, original in evidence_map.items():
        if not normalized:
            continue
        if candidate_key == normalized:
            return DuplicateReason.EXACT_MATCH, original
        if candidate_key in normalized or normalized in candidate_key:
            return DuplicateReason.OVERLAP, original
    return None, None


def _determine_normalization_reason(
    text: str, selection: ReviewSelectionContext | None, summary: str | None
) -> NormalizationReason:
    normalized = _normalize_text(text)
    if selection:
        label = (selection.label or "").strip()
        context = (selection.context or "").strip()
        if label and label.lower() in normalized:
            return NormalizationReason.SELECTION_LABEL
        if context and context.lower() in normalized:
            return NormalizationReason.SELECTION_CONTEXT
        return NormalizationReason.SELECTION_DEFAULT
    if summary:
        return NormalizationReason.SUMMARY_FALLBACK
    return NormalizationReason.UNKNOWN


_GENERIC_PHRASES = (
    "review status",
    "review cluster",
    "review everything",
    "investigate flagged",
    "investigate flagged resources",
    "investigate resources",
    "assess cluster",
)

_GENERIC_KEYWORDS = ("review", "investigate", "assess", "inspect", "check", "verify")
_GENERIC_STATUS_TERMS = ("status", "resources", "signals", "components", "health", "workload", "everything")


def _normalize_for_dedup(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"\(.*?\)", "", normalized)
    normalized = re.sub(r"\bversion\b\s*\S*", "", normalized)
    normalized = re.sub(r"\b(v?\d+(?:\.\d+)*)\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or _normalize_text(value)


def _build_dedup_signature(description: str, target_cluster: str | None) -> str:
    normalized = _normalize_for_dedup(description)
    target = target_cluster or ""
    return f"{target}|{normalized}"


def _is_generic_candidate(text: str, family: CommandFamily) -> bool:
    if family != CommandFamily.UNKNOWN:
        return False
    normalized = _normalize_text(text)
    for phrase in _GENERIC_PHRASES:
        if phrase in normalized:
            return True
    if any(keyword in normalized for keyword in _GENERIC_KEYWORDS) and any(
        term in normalized for term in _GENERIC_STATUS_TERMS
    ):
        return True
    if "everything" in normalized or "general" in normalized:
        return True
    return False


def _determine_priority_label(
    *,
    duplicate: bool,
    target_cluster: str | None,
    safe_to_automate: bool,
    family: CommandFamily,
    cost: CostEstimate,
    generic: bool,
) -> str:
    if duplicate or generic or family == CommandFamily.UNKNOWN:
        return "fallback"
    if target_cluster and safe_to_automate and cost == CostEstimate.LOW:
        return "primary"
    return "secondary"


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
    
    Note: feedback-based suppression is applied later in _rank_candidates
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
    if _is_generic_candidate(candidate.description, candidate.suggested_command_family):
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


def _rank_candidates(
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
                    ranking_policy_reason=ranking_reason,
                    alertmanager_provenance=provenance,
                    feedback_adaptation_provenance=feedback_provenance,
                )
            )
        else:
            ranked.append(candidate)
    return tuple(ranked)


@dataclass(frozen=True)
class NextCheckCandidate:
    candidate_id: str
    description: str
    target_cluster: str | None
    target_context: str | None
    source_reason: str | None
    expected_signal: str | None
    suggested_command_family: CommandFamily
    safe_to_automate: bool
    requires_operator_approval: bool
    risk_level: RiskLevel
    estimated_cost: CostEstimate
    confidence: str
    gating_reason: str | None
    duplicate_of_existing_evidence: bool
    duplicate_evidence_description: str | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    priority_label: str
    # Observability: why ranking policy was applied (if any)
    ranking_policy_reason: str | None = None
    # Structured provenance for Alertmanager-driven ranking (if any)
    alertmanager_provenance: AlertmanagerRankingProvenance | None = None
    # Run-scoped provenance for feedback-based Alertmanager bonus suppression
    # Set when operator marked Alertmanager relevance as not_relevant/noisy in this run
    feedback_adaptation_provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object | str | bool]:
        result: dict[str, object | str | bool] = {
            "description": self.description,
            "targetCluster": self.target_cluster,
            "sourceReason": self.source_reason,
            "expectedSignal": self.expected_signal,
            "suggestedCommandFamily": self.suggested_command_family.value,
            "safeToAutomate": self.safe_to_automate,
            "requiresOperatorApproval": self.requires_operator_approval,
            "riskLevel": self.risk_level.value,
            "estimatedCost": self.estimated_cost.value,
            "confidence": self.confidence,
            "gatingReason": self.gating_reason,
            "duplicateOfExistingEvidence": self.duplicate_of_existing_evidence,
            "duplicateEvidenceDescription": self.duplicate_evidence_description,
            "normalizationReason": self.normalization_reason,
            "safetyReason": self.safety_reason,
            "approvalReason": self.approval_reason,
            "duplicateReason": self.duplicate_reason,
            "blockingReason": self.blocking_reason,
            "targetContext": self.target_context,
            "candidateId": self.candidate_id,
            "priorityLabel": self.priority_label,
        }
        if self.ranking_policy_reason is not None:
            result["rankingPolicyReason"] = self.ranking_policy_reason
        if self.alertmanager_provenance is not None:
            result["alertmanagerProvenance"] = self.alertmanager_provenance.to_dict()
        if self.feedback_adaptation_provenance is not None:
            result["feedbackAdaptationProvenance"] = self.feedback_adaptation_provenance
        return result


@dataclass(frozen=True)
class NextCheckPlan:
    run_id: str
    review_path: Path
    enrichment_artifact_path: str | None
    candidates: tuple[NextCheckCandidate, ...]

    def to_payload(self) -> dict[str, object | None]:
        candidates_payload: list[dict[str, object | None]] = []
        for index, candidate in enumerate(self.candidates):
            candidate_dict = candidate.to_dict()
            candidate_dict.setdefault("candidateIndex", index)
            candidates_payload.append(candidate_dict)
        return {
            "review_path": str(self.review_path),
            "enrichment_artifact_path": self.enrichment_artifact_path,
            "candidates": candidates_payload,
        }


def plan_next_checks(
    review_path: Path,
    run_id: str,
    enrichment_artifact: ExternalAnalysisArtifact,
    execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
) -> NextCheckPlan | None:
    if enrichment_artifact.status != ExternalAnalysisStatus.SUCCESS:
        return None
    checks = enrichment_artifact.suggested_next_checks
    if not checks:
        return None
    try:
        context = build_review_enrichment_input(review_path, run_id)
    except Exception:
        return None
    evidence_map = _collect_existing_evidence(context)
    selections = context.selections
    candidates: list[NextCheckCandidate] = []
    seen_signatures: set[str] = set()
    for candidate_text in checks:
        if not candidate_text or not isinstance(candidate_text, str):
            continue
        selection = _match_selection_for_text(candidate_text, selections)
        target_cluster = selection.label if selection else None
        target_context = selection.context.strip() if selection and selection.context else None
        source_reason = None
        if selection:
            reasons_entry = selection.entry.get("reasons")
            if isinstance(reasons_entry, Sequence):
                for reason_item in reasons_entry:
                    if isinstance(reason_item, str) and reason_item:
                        source_reason = reason_item
                        break
        if not source_reason and enrichment_artifact.summary:
            source_reason = enrichment_artifact.summary
        family = detect_command_family(candidate_text)
        risk = _risk_from_family(family)
        expected_signal = detect_expected_signal(candidate_text)
        candidate_key = _normalize_description(candidate_text)
        duplicate_reason_enum, duplicate_description = _find_similar_description(
            candidate_key, evidence_map
        )
        duplicate = duplicate_reason_enum is not None
        mutation_flag = _mentions_mutation(candidate_text)
        safe = family != CommandFamily.UNKNOWN and not mutation_flag and not duplicate
        requires_approval = not safe or duplicate
        gating_reason: str | None = None
        normalization_reason = _determine_normalization_reason(
            candidate_text, selection, enrichment_artifact.summary
        )
        if duplicate:
            safety_reason = SafetyReason.DUPLICATE_EVIDENCE
        elif mutation_flag:
            safety_reason = SafetyReason.MUTATION_DETECTED
        elif family == CommandFamily.UNKNOWN:
            safety_reason = SafetyReason.UNKNOWN_COMMAND
        else:
            safety_reason = SafetyReason.KNOWN_COMMAND
        approval_reason: ApprovalReason | None = None
        if requires_approval:
            if duplicate:
                approval_reason = ApprovalReason.DUPLICATE_EVIDENCE
            elif mutation_flag:
                approval_reason = ApprovalReason.MUTATION_DETECTED
            elif family == CommandFamily.UNKNOWN:
                approval_reason = ApprovalReason.UNKNOWN_COMMAND
            else:
                approval_reason = ApprovalReason.GENERIC
        blocking_reason: BlockingReason | None = None
        if duplicate:
            blocking_reason = BlockingReason.DUPLICATE
        elif mutation_flag:
            blocking_reason = BlockingReason.MUTATION_DETECTED
        elif not safe:
            blocking_reason = BlockingReason.UNKNOWN_COMMAND
        if duplicate:
            gating_reason = (
                f"Matches deterministic next check: {duplicate_description}"
                if duplicate_description
                else "Duplicate of deterministic evidence"
            )
        elif mutation_flag:
            gating_reason = "Step mentions a potentially mutating kubectl command"
        elif family == CommandFamily.UNKNOWN:
            gating_reason = "Command not recognized or too vague"
        cost = _cost_from_risk(risk)
        confidence = _confidence_level(safe, family)
        signature = _build_dedup_signature(candidate_text, target_cluster)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        is_generic = _is_generic_candidate(candidate_text, family)
        priority_label = _determine_priority_label(
            duplicate=duplicate,
            target_cluster=target_cluster,
            safe_to_automate=safe,
            family=family,
            cost=cost,
            generic=is_generic,
        )
        candidate_id = _derive_candidate_id(
            candidate_text,
            target_cluster,
            source_reason,
            family,
        )
        candidate = NextCheckCandidate(
            candidate_id=candidate_id,
            description=candidate_text.strip(),
            target_cluster=target_cluster,
            target_context=target_context,
            source_reason=source_reason,
            expected_signal=expected_signal,
            suggested_command_family=family,
            safe_to_automate=safe,
            requires_operator_approval=requires_approval,
            risk_level=risk,
            estimated_cost=cost,
            confidence=confidence,
            gating_reason=gating_reason,
            duplicate_of_existing_evidence=duplicate,
            duplicate_evidence_description=duplicate_description,
            normalization_reason=normalization_reason.value,
            safety_reason=safety_reason.value,
            approval_reason=approval_reason.value if approval_reason else None,
            duplicate_reason=duplicate_reason_enum.value if duplicate_reason_enum else None,
            blocking_reason=blocking_reason.value if blocking_reason else None,
            priority_label=priority_label,
        )
        candidates.append(candidate)
    if not candidates:
        return None
    
    # Extract context for ranking policy adjustments
    # The enrichment artifact carries workstream/review_stage from the original assessment
    workstream = enrichment_artifact.workstream
    review_stage = enrichment_artifact.review_stage
    
    # Extract Alertmanager ranking signal from run-scoped context
    # No live Alertmanager fetch is performed - only run-scoped compact artifact is used
    alertmanager_signal: AlertmanagerRankingSignal | None = None
    if context.alertmanager_context is not None:
        alertmanager_signal = AlertmanagerRankingSignal.from_alertmanager_context(
            context.alertmanager_context
        )
    
    # Build run-scoped Alertmanager feedback from execution artifacts
    # This enables run-scoped learning: operator marking Alertmanager relevance as
    # not_relevant/noisy suppresses similar Alertmanager-driven candidates
    alertmanager_feedback: RunScopedAlertmanagerFeedback | None = None
    if execution_artifacts:
        alertmanager_feedback = build_feedback_from_execution_artifacts(execution_artifacts)
    
    sorted_candidates = _rank_candidates(candidates, workstream, review_stage, alertmanager_signal, alertmanager_feedback)
    return NextCheckPlan(
        run_id=run_id,
        review_path=review_path,
        enrichment_artifact_path=enrichment_artifact.artifact_path,
        candidates=sorted_candidates,
    )

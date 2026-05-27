"""Alertmanager-specific ranking signal, bonus, rationale, and provenance helpers.

Extracted from next_check_planner_ranking.py to reduce file size and improve modularity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .next_check_planner_candidates import NextCheckCandidate
from .review_input import AlertmanagerContext

if TYPE_CHECKING:
    from .next_check_planner_models import AlertmanagerRankingProvenance

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


# Re-export constants for callers that need them
__all__ = [
    "AlertmanagerRankingSignal",
    "extract_alertmanager_severity_weight",
    "compute_alertmanager_match_bonus",
    "build_alertmanager_provenance",
    "_compute_alertmanager_bonus",
    "_build_alertmanager_rationale",
    # Bonus constants
    "_ALERTMANAGER_NAMESPACE_MATCH_BONUS",
    "_ALERTMANAGER_CLUSTER_MATCH_BONUS",
    "_ALERTMANAGER_SERVICE_MATCH_BONUS",
    "_ALERTMANAGER_MAX_CUMULATIVE_BONUS",
]

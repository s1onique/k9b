"""Identity grouping for Alertmanager sources - determine if sources are aliases.

This module provides the identity grouping logic that determines whether two
Alertmanager sources are actually aliases of the same backend Alertmanager.

Identity is based on stronger evidence than name matching:
1. Same Kubernetes target pod UIDs
2. Same owner chain: Service → EndpointSlice → Pod → StatefulSet → Alertmanager CR
3. Same /api/v2/status cluster/version/config hash
4. Same receiver/silence/alert summary counts (as supporting evidence)

The output of this module is used to populate the duplicate_analysis field
in the AlertmanagerSourcesReviewPacket.

Design rationale:
- Don't dedupe blindly. Prometheus Operator often creates multiple services
  (alertmanager-operated + chart service) pointing to the same pods.
- Identity should be proven via runtime evidence, not just name similarity.
- The grouping is for INFORMATION, not automatic deduplication.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .alertmanager_sources_review_packet import DuplicateAnalysis

# Reason constants for duplicate analysis
REASON_SAME_TARGET_PODS = "same_target_pods"
REASON_SAME_CONFIG_HASH = "same_config_hash"
REASON_SAME_CLUSTER_STATUS = "same_cluster_status"
REASON_SAME_VERSION = "same_version"
REASON_UNKNOWN = "requires_manual_review"

# Recommended actions
ACTION_COLLAPSE_AS_ALIASES = "collapse_as_aliases"
ACTION_KEEP_SEPARATE = "keep_separate"
ACTION_REQUIRES_MANUAL_REVIEW = "requires_manual_review"


@dataclass(frozen=True)
class IdentityEvidence:
    """Evidence supporting identity determination between sources."""
    same_target_pods: bool = False
    same_config_hash: bool = False
    same_cluster_status: bool = False
    same_version: bool = False
    same_peer_count: bool = False
    # Details for explanation
    shared_pod_uids: tuple[str, ...] = ()
    config_hash_a: str | None = None
    config_hash_b: str | None = None


def _hash_pod_uids(pod_uids: list[str]) -> str:
    """Create a deterministic hash from a list of pod UIDs."""
    if not pod_uids:
        return ""
    sorted_uids = sorted(set(pod_uids))
    return hashlib.sha256("|".join(sorted_uids).encode()).hexdigest()[:16]


def _compare_pod_uids(uids_a: list[str], uids_b: list[str]) -> tuple[bool, tuple[str, ...]]:
    """Compare two lists of pod UIDs and return whether they're the same.
    
    Returns:
        Tuple of (are_same, shared_uids)
    """
    set_a = set(uids_a)
    set_b = set(uids_b)
    shared = tuple(set_a & set_b)
    # Consider same if at least one pod UID is shared (for HA setups)
    return len(shared) > 0, shared


def determine_identity_evidence(
    pod_uids_a: list[str] | None,
    pod_uids_b: list[str] | None,
    config_hash_a: str | None,
    config_hash_b: str | None,
    cluster_status_a: str | None,
    cluster_status_b: str | None,
    version_a: str | None,
    version_b: str | None,
    peer_count_a: int,
    peer_count_b: int,
) -> IdentityEvidence:
    """Determine identity evidence between two sources.
    
    Args:
        pod_uids_a: Pod UIDs for source A
        pod_uids_b: Pod UIDs for source B
        config_hash_a: Config hash for source A
        config_hash_b: Config hash for source B
        cluster_status_a: Cluster status for source A
        cluster_status_b: Cluster status for source B
        version_a: Version for source A
        version_b: Version for source B
        peer_count_a: Peer count for source A
        peer_count_b: Peer count for source B
        
    Returns:
        IdentityEvidence with comparison results
    """
    # Compare pod UIDs
    if pod_uids_a and pod_uids_b:
        same_pods, shared_uids = _compare_pod_uids(pod_uids_a, pod_uids_b)
    else:
        same_pods = False
        shared_uids = ()
    
    # Compare config hashes
    same_config = (
        config_hash_a is not None and
        config_hash_b is not None and
        config_hash_a == config_hash_b
    )
    
    # Compare cluster status
    same_cluster = (
        cluster_status_a is not None and
        cluster_status_b is not None and
        cluster_status_a == cluster_status_b
    )
    
    # Compare versions
    same_version = (
        version_a is not None and
        version_b is not None and
        version_a == version_b
    )
    
    # Compare peer counts
    same_peer_count = peer_count_a == peer_count_b
    
    return IdentityEvidence(
        same_target_pods=same_pods,
        same_config_hash=same_config,
        same_cluster_status=same_cluster,
        same_version=same_version,
        same_peer_count=same_peer_count,
        shared_pod_uids=shared_uids,
        config_hash_a=config_hash_a,
        config_hash_b=config_hash_b,
    )


def determine_recommended_action(evidence: IdentityEvidence) -> tuple[str, str]:
    """Determine the recommended action based on identity evidence.
    
    Returns:
        Tuple of (recommended_action, reason)
    """
    # Strong evidence: same pods AND same config
    if evidence.same_target_pods and evidence.same_config_hash:
        return (
            ACTION_COLLAPSE_AS_ALIASES,
            "Both services resolve to the same Alertmanager pod set and same config hash."
        )
    
    # Strong evidence: same pods
    if evidence.same_target_pods:
        parts = ["Both services resolve to the same target pod UIDs"]
        if evidence.same_version:
            parts.append("same Alertmanager version")
        if evidence.same_cluster_status:
            parts.append("same cluster status")
        if evidence.same_peer_count:
            parts.append("same peer count")
        parts.append("but config hash differs.")
        return (
            ACTION_COLLAPSE_AS_ALIASES,
            " ".join(parts)
        )
    
    # Medium evidence: same config hash
    if evidence.same_config_hash:
        return (
            ACTION_COLLAPSE_AS_ALIASES,
            "Both sources share the same config hash, suggesting same Alertmanager instance."
        )
    
    # Weak evidence: same cluster status and version but different pods
    if evidence.same_cluster_status and evidence.same_version:
        return (
            ACTION_REQUIRES_MANUAL_REVIEW,
            "Same cluster status and version but different target pods. May be different Alertmanager instances or HA cluster members."
        )
    
    # Insufficient evidence
    return (
        ACTION_KEEP_SEPARATE,
        "No strong identity evidence found. Sources may be distinct Alertmanagers."
    )


def group_sources_as_aliases(
    source_ids: list[str],
    evidence: IdentityEvidence,
) -> DuplicateAnalysis:
    """Create a DuplicateAnalysis entry for a group of sources.
    
    Args:
        source_ids: List of source IDs in the alias group
        evidence: Identity evidence for the group
        
    Returns:
        DuplicateAnalysis with grouping explanation
    """
    recommended_action, reason = determine_recommended_action(evidence)
    
    # Generate a stable group ID
    sorted_ids = sorted(source_ids)
    group_id = hashlib.sha256("|".join(sorted_ids).encode()).hexdigest()[:8]
    
    # Build reason details
    reason_parts = []
    if evidence.same_target_pods:
        reason_parts.append(f"shared pod UIDs: {', '.join(evidence.shared_pod_uids[:3])}")
    if evidence.same_config_hash:
        reason_parts.append(f"same config hash: {evidence.config_hash_a}")
    if evidence.same_cluster_status:
        reason_parts.append("same cluster status")
    if evidence.same_version:
        reason_parts.append("same version")
    
    if reason_parts:
        reason = f"Evidence: {', '.join(reason_parts)}. {reason}"
    
    return DuplicateAnalysis(
        group_id=group_id,
        source_ids=tuple(source_ids),
        same_target_pods=evidence.same_target_pods,
        same_alertmanager_cluster=evidence.same_cluster_status,
        same_config_hash=evidence.same_config_hash,
        recommended_action=recommended_action,
        reason=reason,
    )


def build_alias_explanation(
    source_a_id: str,
    source_b_id: str,
    evidence: IdentityEvidence,
) -> str:
    """Build a human-readable explanation of why sources are aliases.
    
    Args:
        source_a_id: First source ID
        source_b_id: Second source ID
        evidence: Identity evidence between sources
        
    Returns:
        Human-readable explanation string
    """
    if evidence.same_target_pods and evidence.same_config_hash:
        return (
            "Identity: same backend (same target pods and config hash). "
            "Reason: Both services resolve to the same Alertmanager pod set. "
            "Action: safe to collapse as aliases."
        )
    
    if evidence.same_target_pods:
        return (
            f"Identity: same backend as {source_a_id}. "
            f"Reason: same EndpointSlice target pod UIDs. "
            f"Action: safe to collapse as aliases (config hash differs)."
        )
    
    if evidence.same_config_hash:
        return (
            f"Identity: same backend as {source_a_id}. "
            f"Reason: same config hash. "
            f"Action: likely safe to collapse as aliases."
        )
    
    if evidence.same_cluster_status and evidence.same_version:
        return (
            "Identity: unknown (same cluster status and version, but different pods). "
            "Reason: May be HA cluster members or distinct Alertmanagers. "
            "Action: requires manual review."
        )
    
    return (
        "Identity: unknown. "
        "Reason: endpoint probe failed or insufficient evidence. "
        "Action: keep separate until probed."
    )


__all__ = [
    "REASON_SAME_TARGET_PODS",
    "REASON_SAME_CONFIG_HASH",
    "REASON_SAME_CLUSTER_STATUS",
    "REASON_SAME_VERSION",
    "REASON_UNKNOWN",
    "ACTION_COLLAPSE_AS_ALIASES",
    "ACTION_KEEP_SEPARATE",
    "ACTION_REQUIRES_MANUAL_REVIEW",
    "IdentityEvidence",
    "determine_identity_evidence",
    "determine_recommended_action",
    "group_sources_as_aliases",
    "build_alias_explanation",
]

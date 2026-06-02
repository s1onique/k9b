"""Comparison policy helpers for health loop peer evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from .baseline import BaselinePolicy

if TYPE_CHECKING:
    from .loop_comparison_types import ComparisonIntent, ComparisonPeer
    from .loop_types import HealthSnapshotRecord, HealthTarget


class BaselineRegistry:
    def __init__(self, policies: Iterable[BaselinePolicy] | None = None) -> None:
        self._policies: list[BaselinePolicy] = []
        if policies:
            for policy in policies:
                self.add(policy)

    def add(self, policy: BaselinePolicy) -> None:
        if policy in self._policies:
            return
        self._policies.append(policy)

    def role_for(self, reference: str) -> str | None:
        for policy in self._policies:
            role = policy.role_for(reference)
            if role:
                return role
        return None


def _resolve_peer_role(
    record: HealthSnapshotRecord,
    registry: BaselineRegistry | None,
) -> str | None:
    """Resolve the peer role for a health snapshot record.

    Priority:
    1. Explicit cluster_role from the target metadata
    2. Registry lookup using record references (context or label)
    """
    explicit_role = record.target.cluster_role
    if explicit_role:
        return explicit_role.strip() or None
    if registry:
        for reference in record.refs():
            role = registry.role_for(reference)
            if role:
                return role
    return None


def _validate_suspicious_pairs(
    peers: Sequence[ComparisonPeer],
    target_lookup: dict[str, HealthTarget],
    baseline: BaselinePolicy,
) -> None:
    """Validate that all suspicious-drift peer mappings are within the same class/cohort."""
    from .loop_comparison_types import ComparisonIntent  # runtime import for type

    issues: list[str] = []
    for peer in peers:
        if peer.intent != ComparisonIntent.SUSPICIOUS_DRIFT:
            continue
        primary = target_lookup.get(peer.primary)
        secondary = target_lookup.get(peer.secondary)
        if not primary or not secondary:
            issues.append(
                f"Suspicious-drift mapping {peer.primary} -> {peer.secondary} references unknown targets."
            )
            continue
        problems: list[str] = []
        if primary.cluster_class != secondary.cluster_class:
            problems.append(
                f"cluster_class differs ({primary.cluster_class or 'missing'} vs {secondary.cluster_class or 'missing'})"
            )
        if primary.baseline_cohort != secondary.baseline_cohort:
            problems.append(
                f"baseline_cohort differs ({primary.baseline_cohort or 'missing'} vs {secondary.baseline_cohort or 'missing'})"
            )
        if problems:
            issues.append(
                f"Suspicious-drift pair {primary.label} ({primary.context}) vs "
                f"{secondary.label} ({secondary.context}) invalid: "
                + "; ".join(problems)
            )
    if issues:
        raise ValueError(
            "Suspicious-drift comparisons must stay within the same class/cohort and be backed by baseline peer roles. "
            + "Fix the following issues:\n- "
            + "\n- ".join(issues)
        )


def _policy_eligible_pair(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    intent: ComparisonIntent,
    baseline_registry: BaselineRegistry | None,
) -> tuple[
    bool,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    """Determine if a pair of health snapshot records is eligible for comparison.

    Returns:
        Tuple of (eligible, reason, primary_class, secondary_class, primary_role,
                 secondary_role, primary_cohort, secondary_cohort)
    """
    from .loop_comparison_types import ComparisonIntent  # runtime import for enum comparison

    primary_class = primary.target.cluster_class
    secondary_class = secondary.target.cluster_class
    primary_role = _resolve_peer_role(primary, baseline_registry)
    secondary_role = _resolve_peer_role(secondary, baseline_registry)
    primary_cohort = primary.target.baseline_cohort
    secondary_cohort = secondary.target.baseline_cohort
    reasons: list[str] = []
    if not primary_class or not secondary_class:
        reasons.append("cluster class metadata missing")
    elif primary_class != secondary_class:
        reasons.append("cluster class mismatch")
    if intent == ComparisonIntent.SUSPICIOUS_DRIFT:
        if not primary_role or not secondary_role:
            reasons.append("peer role metadata missing")
        elif primary_role != secondary_role:
            reasons.append("peer roles differ")
        if not primary_cohort or not secondary_cohort:
            reasons.append("baseline cohort metadata missing")
        elif primary_cohort != secondary_cohort:
            reasons.append(
                f"baseline cohorts differ ({primary_cohort} vs {secondary_cohort})"
            )
    if intent == ComparisonIntent.IRRELEVANT_DRIFT:
        reasons.append("comparison intent marked this pair as irrelevant drift")
    if reasons:
        return (
            False,
            "; ".join(reasons),
            primary_class,
            secondary_class,
            primary_role,
            secondary_role,
            primary_cohort,
            secondary_cohort,
        )
    return (
        True,
        "policy compatible",
        primary_class,
        secondary_class,
        primary_role,
        secondary_role,
        primary_cohort,
        secondary_cohort,
    )

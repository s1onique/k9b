"""Stop/continue planning for documentation claim candidate backlog reporter."""

from __future__ import annotations

from .planning_helpers import (
    _compute_planning_caveat,
    _count_key_risk_buckets,
    _count_priority_bands,
    _count_priority_by_review_class,
    _count_review_class_counts,
    _count_stale_historical_breakdown,
    _top_docs_by_band,
    get_priority_band,
    print_planning_summary,
)
from .planning_helpers import (
    ACTION_BLOCKED_INCONCLUSIVE,
    ACTION_CONTINUE_LARGE_TRANCHE,
    ACTION_CONTINUE_SMALL_TARGETED,
    ACTION_PAUSE_MANUAL_TRANCHES,
    LARGE_TRANCHE_THRESHOLD,
    SMALL_TRANCHE_MIN_THRESHOLD,
    CAVEAT_CLEANUP_HEAVY,
    CAVEAT_CLAIM_CANDIDATE_HEAVY,
)

# Re-export for backwards compatibility with existing imports
from .planning_helpers import CAVEAT_MIXED, CAVEAT_LOW_BACKLOG, CAVEAT_INCONCLUSIVE  # noqa: F401


def compute_planning_summary(entries: list[BacklogEntry]) -> dict:
    """Compute planning summary from backlog entries.

    Returns a dict with:
    - priority_band_counts: counts per priority band (based on calibrated score)
    - priority_band_top_docs: top docs per band
    - key_risk_buckets: counts in key risk buckets
    - review_class_counts: counts by review class
    - priority_by_review_class: P0+P1 counts by review class
    - claim_candidate_high_priority_count: P0+P1 claim_candidate count
    - cleanup_high_priority_count: P0+P1 cleanup class count
    - planning_caveat: claim-candidate-heavy/cleanup-heavy/mixed/low-backlog/inconclusive
    - recommended_next_action: stop/continue recommendation
    - recommended_next_action_reason: explanation
    - recommended_tranche_size: suggested tranche size
    - maintenance_actionable_count: P0+P1+P2 stale_or_historical unreviewed count
    - maintenance_low_priority_count: P3+P4 stale_or_historical unreviewed count
    - maintenance_reviewed_count: ACT-5.14-marked stale_or_historical count
    - maintenance_unreviewed_count: total stale_or_historical unreviewed count
    - maintenance_stop_reason: stop reason if pause, else empty string
    """
    from .model import REVIEW_CLASS_CLAIM_CANDIDATE, is_cleanup_class

    band_counts = _count_priority_bands(entries)
    key_buckets = _count_key_risk_buckets(entries)
    band_top_docs = _top_docs_by_band(entries)
    review_class_counts = _count_review_class_counts(entries)
    priority_by_class = _count_priority_by_review_class(entries)
    stale_breakdown = _count_stale_historical_breakdown(entries)

    p0_count = band_counts.get("P0", 0)
    p1_count = band_counts.get("P1", 0)
    p2_count = band_counts.get("P2", 0)
    p3_count = band_counts.get("P3", 0)
    p4_count = band_counts.get("P4", 0)

    high_priority_count = p0_count + p1_count

    # Compute claim_candidate and cleanup high-priority counts
    claim_candidate_high_priority = 0
    cleanup_high_priority = 0
    for band in ("P0", "P1"):
        band_data = priority_by_class.get(band, {})
        claim_candidate_high_priority += band_data.get(REVIEW_CLASS_CLAIM_CANDIDATE, 0)
        for review_class, count in band_data.items():
            if is_cleanup_class(review_class):
                cleanup_high_priority += count

    # Determine planning caveat
    planning_caveat = _compute_planning_caveat(priority_by_class, high_priority_count)

    # Extract stale/historical breakdown
    stale_p0 = stale_breakdown["stale_unreviewed_p0"]
    stale_p1 = stale_breakdown["stale_unreviewed_p1"]
    stale_p2 = stale_breakdown["stale_unreviewed_p2"]
    stale_p3_p4 = stale_breakdown["stale_unreviewed_p3_p4"]
    stale_act_5_14 = stale_breakdown["stale_act_5_14_count"]
    stale_actionable = stale_p0 + stale_p1 + stale_p2
    stale_total = stale_actionable + stale_p3_p4

    # Determine recommendation with calibrated reasoning
    if high_priority_count >= LARGE_TRANCHE_THRESHOLD:
        action = ACTION_CONTINUE_LARGE_TRANCHE
        if planning_caveat == CAVEAT_CLEANUP_HEAVY:
            reason = (
                f"P0+P1 has {high_priority_count} candidates, "
                f"but current high-priority set is cleanup-heavy. "
                f"Use the tranche for reason/note burn-down, not new claim discovery."
            )
        elif planning_caveat == CAVEAT_CLAIM_CANDIDATE_HEAVY:
            reason = (
                f"P0+P1 has {high_priority_count} candidates, "
                f"enough for another {LARGE_TRANCHE_THRESHOLD}-candidate tranche. "
                f"High-priority set is claim-candidate-heavy."
            )
        else:
            reason = (
                f"P0+P1 has {high_priority_count} candidates, "
                f"enough for another {LARGE_TRANCHE_THRESHOLD}-candidate tranche."
            )
        tranche_size = LARGE_TRANCHE_THRESHOLD
    elif high_priority_count >= SMALL_TRANCHE_MIN_THRESHOLD:
        action = ACTION_CONTINUE_SMALL_TARGETED
        if planning_caveat == CAVEAT_CLEANUP_HEAVY:
            reason = (
                f"P0+P1 has {high_priority_count} candidates, "
                f"but high-priority set is cleanup-heavy. "
                f"Use targeted tranche for burn-down. "
                f"Remaining P2={p2_count}, P3={p3_count}, P4={p4_count}."
            )
        else:
            reason = (
                f"P0+P1 has {high_priority_count} candidates, "
                f"suggesting a smaller targeted tranche. "
                f"Remaining P2={p2_count}, P3={p3_count}, P4={p4_count}."
            )
        tranche_size = min(high_priority_count, 100)
    elif key_buckets["weak_covered_count"] > 0:
        weak_count = key_buckets["weak_covered_count"]
        action = ACTION_CONTINUE_SMALL_TARGETED
        reason = (
            f"High-priority backlog is low (P0+P1={high_priority_count}), "
            f"but {weak_count} weak-covered entries remain. "
            "Run a targeted weak-covered review before pausing."
        )
        tranche_size = min(weak_count, 100)
    # ACT 5.15 stale/historical-specific stop criteria
    elif stale_p0 + stale_p1 > 0:
        actionable = stale_p0 + stale_p1
        action = ACTION_CONTINUE_SMALL_TARGETED
        reason = (
            f"stale_or_historical has {stale_p0} P0 and "
            f"{stale_p1} P1 unreviewed rows "
            f"(plus {stale_p2} P2, {stale_p3_p4} P3/P4). "
            f"{stale_act_5_14} rows already have ACT 5.14 review marker. "
            "High-priority stale/historical maintenance candidates warrant targeted review."
        )
        tranche_size = min(actionable, 25)
    elif stale_p2 > 0:
        action = ACTION_CONTINUE_SMALL_TARGETED
        reason = (
            f"stale_or_historical has {stale_p2} P2 unreviewed rows "
            f"(plus {stale_p3_p4} P3/P4). "
            f"{stale_act_5_14} rows already have ACT 5.14 review marker. "
            "Medium-priority stale/historical maintenance candidates remain."
        )
        tranche_size = min(stale_p2, 25)
    elif stale_total > 0:
        action = ACTION_PAUSE_MANUAL_TRANCHES
        reason = (
            f"stale_or_historical has {stale_total} unreviewed rows "
            f"(all P3/P4 low-priority residue) and "
            f"{stale_act_5_14} rows already marked by ACT 5.14. "
            "Only low-priority stale/historical residue remains. "
            "Do not run more manual tranches on P4-only stale rows."
        )
        tranche_size = 0
    elif high_priority_count < SMALL_TRANCHE_MIN_THRESHOLD:
        action = ACTION_PAUSE_MANUAL_TRANCHES
        reason = (
            f"P0+P1 has only {high_priority_count} candidates (< {SMALL_TRANCHE_MIN_THRESHOLD}), "
            f"with no weak-covered or stale-high-value entries. "
            "Manual tranche review may have reached diminishing returns."
        )
        tranche_size = 0
    else:
        action = ACTION_BLOCKED_INCONCLUSIVE
        reason = "Unable to determine recommendation from backlog data."
        tranche_size = 0

    is_stale_pause = (
        action == ACTION_PAUSE_MANUAL_TRANCHES
        and (stale_total > 0 or stale_act_5_14 > 0)
    )
    stop_reason = reason if is_stale_pause else ""

    return {
        "priority_band_counts": {
            "P0": p0_count,
            "P1": p1_count,
            "P2": p2_count,
            "P3": p3_count,
            "P4": p4_count,
        },
        "priority_band_top_docs": band_top_docs,
        "key_risk_buckets": key_buckets,
        "review_class_counts": review_class_counts,
        "priority_by_review_class": priority_by_class,
        "claim_candidate_high_priority_count": claim_candidate_high_priority,
        "cleanup_high_priority_count": cleanup_high_priority,
        "planning_caveat": planning_caveat,
        "recommended_next_action": action,
        "recommended_next_action_reason": reason,
        "recommended_tranche_size": tranche_size,
        # ACT 5.15 stale/historical maintenance stop criteria fields
        "maintenance_actionable_count": stale_actionable,
        "maintenance_low_priority_count": stale_p3_p4,
        "maintenance_reviewed_count": stale_act_5_14,
        "maintenance_unreviewed_count": stale_total,
        "maintenance_stop_reason": stop_reason,
    }

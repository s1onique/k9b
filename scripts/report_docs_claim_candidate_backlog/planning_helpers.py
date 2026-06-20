"""Helper functions for stop/continue planning."""
from __future__ import annotations

from collections import defaultdict
from typing import cast

from .model import (
    REVIEW_CLASS_CLAIM_CANDIDATE,
    REVIEW_CLASS_STALE_OR_HISTORICAL,
    BacklogEntry,
    is_cleanup_class,
)


def get_priority_band(score: int) -> str:
    """Map a risk score to a priority band.
    
    Priority bands:
        P0: score >= 42 (highest priority for manual review)
        P1: score >= 34 and score < 42
        P2: score >= 24 and score < 34
        P3: score >= 1 and score < 24
        P4: score <= 0 (deprioritized)
    """
    if score >= 42:
        return "P0"
    elif score >= 34:
        return "P1"
    elif score >= 24:
        return "P2"
    elif score >= 1:
        return "P3"
    else:
        return "P4"


def _count_priority_bands(entries: list[BacklogEntry]) -> dict[str, int]:
    """Count entries in each priority band based on calibrated_score (unreviewed only)."""
    band_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
        band = get_priority_band(calibrated)
        band_counts[band] += 1
    return dict(sorted(band_counts.items()))


def _count_review_class_counts(entries: list[BacklogEntry]) -> dict[str, int]:
    """Count entries by review class (unreviewed only)."""
    class_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        review_class = cast(str, entry.get("review_class", "unknown"))
        class_counts[review_class] += 1
    return dict(sorted(class_counts.items()))


def _count_priority_by_review_class(entries: list[BacklogEntry]) -> dict[str, dict[str, int]]:
    """Count entries by priority band and review class (unreviewed only)."""
    priority_by_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
        band = get_priority_band(calibrated)
        if band not in ("P0", "P1"):
            continue
        review_class = cast(str, entry.get("review_class", "unknown"))
        priority_by_class[band][review_class] += 1
    result: dict[str, dict[str, int]] = {}
    for band in ("P0", "P1"):
        if band in priority_by_class:
            result[band] = dict(sorted(priority_by_class[band].items()))
    return result


# Recommended next actions
ACTION_CONTINUE_LARGE_TRANCHE = "continue_large_tranche"
ACTION_CONTINUE_SMALL_TARGETED = "continue_small_targeted_tranche"
ACTION_PAUSE_MANUAL_TRANCHES = "pause_manual_tranches"
ACTION_BLOCKED_INCONCLUSIVE = "blocked_or_inconclusive"

# Threshold constants
LARGE_TRANCHE_THRESHOLD = 100
SMALL_TRANCHE_MIN_THRESHOLD = 25

# Planning caveat values
CAVEAT_CLAIM_CANDIDATE_HEAVY = "claim-candidate-heavy"
CAVEAT_CLEANUP_HEAVY = "cleanup-heavy"
CAVEAT_MIXED = "mixed"
CAVEAT_LOW_BACKLOG = "low-backlog"
CAVEAT_INCONCLUSIVE = "inconclusive"


def _compute_planning_caveat(
    priority_by_class: dict[str, dict[str, int]],
    high_priority_count: int,
) -> str:
    """Determine planning caveat based on high-priority composition."""
    if high_priority_count == 0:
        return CAVEAT_LOW_BACKLOG
    claim_candidate_count = 0
    cleanup_count = 0
    for band in ("P0", "P1"):
        band_data = priority_by_class.get(band, {})
        claim_candidate_count += band_data.get(REVIEW_CLASS_CLAIM_CANDIDATE, 0)
        for review_class, count in band_data.items():
            if is_cleanup_class(review_class):
                cleanup_count += count
    if claim_candidate_count >= 50 and cleanup_count < 20:
        return CAVEAT_CLAIM_CANDIDATE_HEAVY
    elif cleanup_count >= 50 and claim_candidate_count < 20:
        return CAVEAT_CLEANUP_HEAVY
    elif claim_candidate_count >= 10 and cleanup_count >= 10:
        return CAVEAT_MIXED
    elif high_priority_count < 25:
        return CAVEAT_LOW_BACKLOG
    else:
        return CAVEAT_INCONCLUSIVE


def _count_key_risk_buckets(entries: list[BacklogEntry]) -> dict[str, int]:
    """Count candidates in key risk buckets (unreviewed only)."""
    unreviewed_count = 0
    generic_ignored_unreviewed = 0
    generic_ignored_high_value = 0
    generic_ignored_normative = 0
    weak_covered = 0
    stale_or_historical_high_value = 0
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        unreviewed_count += 1
        is_generic_ignored = (
            entry.get("disposition") == "ignored_by_policy"
            and entry.get("is_generic_low_value_note")
        )
        is_high_value = entry.get("is_high_value_doc")
        is_weak_covered = (
            entry.get("disposition") == "covered_by_existing_claim"
            and entry.get("is_generic_low_value_note")
        )
        is_stale_or_hist = (
            entry.get("is_stale") or entry.get("is_historical")
        )
        risk_reasons = cast(list[str], entry.get("risk_reasons", []))
        has_normative = "normative_text" in risk_reasons
        if is_generic_ignored:
            generic_ignored_unreviewed += 1
            if is_high_value:
                generic_ignored_high_value += 1
            if has_normative:
                generic_ignored_normative += 1
        if is_weak_covered:
            weak_covered += 1
        if is_stale_or_hist and is_high_value:
            stale_or_historical_high_value += 1
    return {
        "unreviewed_count": unreviewed_count,
        "generic_ignored_unreviewed_count": generic_ignored_unreviewed,
        "generic_ignored_high_value_count": generic_ignored_high_value,
        "generic_ignored_normative_count": generic_ignored_normative,
        "weak_covered_count": weak_covered,
        "stale_or_historical_high_value_count": stale_or_historical_high_value,
    }


def _top_docs_by_band(entries: list[BacklogEntry]) -> dict[str, list[dict]]:
    """Get top docs by candidate count per priority band (unreviewed only)."""
    band_doc_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        score = cast(int, entry.get("score", 0))
        band = get_priority_band(score)
        doc = cast(str, entry.get("source_doc_path", ""))
        band_doc_counts[band][doc] += 1
    result: dict[str, list[dict]] = {}
    for band, doc_counts in sorted(band_doc_counts.items()):
        top_docs = sorted(doc_counts.items(), key=lambda x: -x[1])[:10]
        result[band] = [{"doc_path": doc, "count": count} for doc, count in top_docs]
    return result


def _count_stale_historical_breakdown(entries: list[BacklogEntry]) -> dict[str, int]:
    """Count stale_or_historical rows by priority band, excluding ACT-5.14-marked rows.
    
    Returns:
        stale_unreviewed_p0: P0 unreviewed stale_or_historical count
        stale_unreviewed_p1: P1 unreviewed stale_or_historical count
        stale_unreviewed_p2: P2 unreviewed stale_or_historical count
        stale_unreviewed_p3_p4: P3+P4 unreviewed stale_or_historical count
        stale_act_5_14_count: ACT 5.14-marked stale_or_historical count
    """
    p0 = p1 = p2 = p3_p4 = act_5_14 = 0
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        if cast(str, entry.get("review_class", "")) != REVIEW_CLASS_STALE_OR_HISTORICAL:
            continue
        if entry.get("is_act_5_14_stale_reviewed"):
            act_5_14 += 1
            continue
        calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
        band = get_priority_band(calibrated)
        if band == "P0":
            p0 += 1
        elif band == "P1":
            p1 += 1
        elif band == "P2":
            p2 += 1
        else:
            p3_p4 += 1
    return {
        "stale_unreviewed_p0": p0,
        "stale_unreviewed_p1": p1,
        "stale_unreviewed_p2": p2,
        "stale_unreviewed_p3_p4": p3_p4,
        "stale_act_5_14_count": act_5_14,
    }


def print_planning_summary(planning: dict) -> None:
    """Print human-readable planning summary."""
    print("\nPlanning / stop-continue assessment:\n")
    band_counts = planning["priority_band_counts"]
    print("Priority bands:")
    print(f"  P0 score>=42: {band_counts.get('P0', 0)}")
    print(f"  P1 score>=34: {band_counts.get('P1', 0)}")
    print(f"  P2 score>=24: {band_counts.get('P2', 0)}")
    print(f"  P3 score>=1: {band_counts.get('P3', 0)}")
    print(f"  P4 score<=0: {band_counts.get('P4', 0)}")
    buckets = planning["key_risk_buckets"]
    print("\nKey risk buckets:")
    print(f"  unreviewed candidates: {buckets['unreviewed_count']}")
    print(f"  unreviewed generic ignored notes: {buckets['generic_ignored_unreviewed_count']}")
    print(f"  high-value generic ignored notes: {buckets['generic_ignored_high_value_count']}")
    print(f"  normative generic ignored notes: {buckets['generic_ignored_normative_count']}")
    print(f"  weak covered-by-existing-claim notes: {buckets['weak_covered_count']}")
    print(f"  stale/historical in high-value docs: {buckets['stale_or_historical_high_value_count']}")
    if "review_class_counts" in planning:
        print("\nReview class counts:")
        for rc_class, count in sorted(planning["review_class_counts"].items()):
            print(f"  {rc_class}: {count}")
    if "claim_candidate_high_priority_count" in planning:
        claim_count = planning["claim_candidate_high_priority_count"]
        cleanup_count = planning["cleanup_high_priority_count"]
        caveat = planning.get("planning_caveat", "unknown")
        print("\nHigh-priority composition:")
        print(f"  claim_candidate P0+P1: {claim_count}")
        print(f"  cleanup P0+P1: {cleanup_count}")
        print(f"  caveat: {caveat}")
    print("\nRecommendation:")
    print(f"  {planning['recommended_next_action']}")
    print(f"  reason: {planning['recommended_next_action_reason']}")
    print(f"  recommended_tranche_size: {planning['recommended_tranche_size']}")

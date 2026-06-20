"""Stop/continue planning for documentation claim candidate backlog reporter."""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from .model import (
    REVIEW_CLASS_CLAIM_CANDIDATE,
    BacklogEntry,
    is_cleanup_class,
)

# Priority band score thresholds (based on calibrated score)
P0_MIN_SCORE = 42  # Highest priority
P1_MIN_SCORE = 34  # High priority
P2_MIN_SCORE = 24  # Medium priority
P3_MIN_SCORE = 1   # Low priority
# P4: score <= 0 (deprioritized)

# Planning caveat values
CAVEAT_CLAIM_CANDIDATE_HEAVY = "claim-candidate-heavy"
CAVEAT_CLEANUP_HEAVY = "cleanup-heavy"
CAVEAT_MIXED = "mixed"
CAVEAT_LOW_BACKLOG = "low-backlog"
CAVEAT_INCONCLUSIVE = "inconclusive"


def get_priority_band(score: int) -> str:
    """Map a risk score to a priority band.
    
    Priority bands:
        P0: score >= 42 (highest priority for manual review)
        P1: score >= 34 and score < 42
        P2: score >= 24 and score < 34
        P3: score >= 1 and score < 24
        P4: score <= 0 (deprioritized)
    """
    if score >= P0_MIN_SCORE:
        return "P0"
    elif score >= P1_MIN_SCORE:
        return "P1"
    elif score >= P2_MIN_SCORE:
        return "P2"
    elif score >= P3_MIN_SCORE:
        return "P3"
    else:
        return "P4"


# Recommended next actions
ACTION_CONTINUE_LARGE_TRANCHE = "continue_large_tranche"
ACTION_CONTINUE_SMALL_TARGETED = "continue_small_targeted_tranche"
ACTION_PAUSE_MANUAL_TRANCHES = "pause_manual_tranches"
ACTION_BLOCKED_INCONCLUSIVE = "blocked_or_inconclusive"

# Threshold constants
LARGE_TRANCHE_THRESHOLD = 100
SMALL_TRANCHE_MIN_THRESHOLD = 25


def _count_priority_bands(
    entries: list[BacklogEntry],
) -> dict[str, int]:
    """Count entries in each priority band based on calibrated_score (unreviewed only)."""
    band_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue  # Skip reviewed entries
        # Use calibrated_score for priority band determination
        calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
        band = get_priority_band(calibrated)
        band_counts[band] += 1
    return dict(sorted(band_counts.items()))


def _count_review_class_counts(
    entries: list[BacklogEntry],
) -> dict[str, int]:
    """Count entries by review class (unreviewed only)."""
    class_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue  # Skip reviewed entries
        review_class = cast(str, entry.get("review_class", "unknown"))
        class_counts[review_class] += 1
    return dict(sorted(class_counts.items()))


def _count_priority_by_review_class(
    entries: list[BacklogEntry],
) -> dict[str, dict[str, int]]:
    """Count entries by priority band and review class (unreviewed only).
    
    Only counts P0 and P1 for high-priority composition analysis.
    """
    # Initialize structure for P0/P1
    priority_by_class: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue
        
        # Use calibrated score for priority band
        calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
        band = get_priority_band(calibrated)
        
        # Only track P0 and P1
        if band not in ("P0", "P1"):
            continue
        
        review_class = cast(str, entry.get("review_class", "unknown"))
        priority_by_class[band][review_class] += 1
    
    # Convert to regular dict for JSON serialization
    result: dict[str, dict[str, int]] = {}
    for band in ("P0", "P1"):
        if band in priority_by_class:
            result[band] = dict(sorted(priority_by_class[band].items()))
    
    return result


def _compute_planning_caveat(
    priority_by_class: dict[str, dict[str, int]],
    high_priority_count: int,
) -> str:
    """Determine planning caveat based on high-priority composition.
    
    Returns:
        - claim-candidate-heavy: P0+P1 dominated by claim_candidate rows
        - cleanup-heavy: P0+P1 dominated by cleanup rows (structural/non-normative/etc)
        - mixed: both types present in significant numbers
        - low-backlog: very few high-priority entries
        - inconclusive: cannot determine
    """
    if high_priority_count == 0:
        return CAVEAT_LOW_BACKLOG
    
    # Sum claim_candidate and cleanup classes for P0+P1
    claim_candidate_count = 0
    cleanup_count = 0
    
    for band in ("P0", "P1"):
        band_data = priority_by_class.get(band, {})
        claim_candidate_count += band_data.get(REVIEW_CLASS_CLAIM_CANDIDATE, 0)
        for review_class, count in band_data.items():
            if is_cleanup_class(review_class):
                cleanup_count += count
    
    # Determine composition
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


def _count_key_risk_buckets(
    entries: list[BacklogEntry],
) -> dict[str, int]:
    """Count candidates in key risk buckets (unreviewed only)."""
    unreviewed_count = 0
    generic_ignored_unreviewed = 0
    generic_ignored_high_value = 0
    generic_ignored_normative = 0
    weak_covered = 0
    stale_or_historical_high_value = 0

    for entry in entries:
        if entry.get("has_any_act_review_marker"):
            continue  # Skip reviewed entries

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
            entry.get("is_stale")
            or entry.get("is_historical")
        )
        is_high_value_doc = entry.get("is_high_value_doc")

        # Check for normative text in risk_reasons
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

        if is_stale_or_hist and is_high_value_doc:
            stale_or_historical_high_value += 1

    return {
        "unreviewed_count": unreviewed_count,
        "generic_ignored_unreviewed_count": generic_ignored_unreviewed,
        "generic_ignored_high_value_count": generic_ignored_high_value,
        "generic_ignored_normative_count": generic_ignored_normative,
        "weak_covered_count": weak_covered,
        "stale_or_historical_high_value_count": stale_or_historical_high_value,
    }


def _top_docs_by_band(
    entries: list[BacklogEntry],
) -> dict[str, list[dict]]:
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
        result[band] = [
            {"doc_path": doc, "count": count}
            for doc, count in top_docs
        ]

    return result


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
    """
    band_counts = _count_priority_bands(entries)
    key_buckets = _count_key_risk_buckets(entries)
    band_top_docs = _top_docs_by_band(entries)
    review_class_counts = _count_review_class_counts(entries)
    priority_by_class = _count_priority_by_review_class(entries)

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
    elif key_buckets["stale_or_historical_high_value_count"] > 0:
        stale_count = key_buckets["stale_or_historical_high_value_count"]
        action = ACTION_CONTINUE_SMALL_TARGETED
        reason = (
            f"High-priority backlog is low (P0+P1={high_priority_count}), "
            f"but {stale_count} stale/historical high-value entries remain. "
            "Run a targeted stale/high-value review before pausing."
        )
        tranche_size = min(stale_count, 100)
    elif high_priority_count < SMALL_TRANCHE_MIN_THRESHOLD:
        action = ACTION_PAUSE_MANUAL_TRANCHES
        reason = (
            f"P0+P1 has only {high_priority_count} candidates (< {SMALL_TRANCHE_MIN_THRESHOLD}), "
            f"with no weak-covered or stale-high-value entries. "
            "Manual tranche review may have reached diminishing returns."
        )
        tranche_size = 0
    else:
        # Inconclusive case (shouldn't happen with above logic, but safe default)
        action = ACTION_BLOCKED_INCONCLUSIVE
        reason = "Unable to determine recommendation from backlog data."
        tranche_size = 0

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
    }


def print_planning_summary(planning: dict) -> None:
    """Print human-readable planning summary."""
    print("\nPlanning / stop-continue assessment:\n")

    print("Priority bands:")
    band_counts = planning["priority_band_counts"]
    print(f"  P0 score>={P0_MIN_SCORE}: {band_counts.get('P0', 0)}")
    print(f"  P1 score>={P1_MIN_SCORE}: {band_counts.get('P1', 0)}")
    print(f"  P2 score>={P2_MIN_SCORE}: {band_counts.get('P2', 0)}")
    print(f"  P3 score>={P3_MIN_SCORE}: {band_counts.get('P3', 0)}")
    print(f"  P4 score<=0: {band_counts.get('P4', 0)}")

    buckets = planning["key_risk_buckets"]
    print("\nKey risk buckets:")
    print(f"  unreviewed candidates: {buckets['unreviewed_count']}")
    print(f"  unreviewed generic ignored notes: {buckets['generic_ignored_unreviewed_count']}")
    print(f"  high-value generic ignored notes: {buckets['generic_ignored_high_value_count']}")
    print(f"  normative generic ignored notes: {buckets['generic_ignored_normative_count']}")
    print(f"  weak covered-by-existing-claim notes: {buckets['weak_covered_count']}")
    print(f"  stale/historical in high-value docs: {buckets['stale_or_historical_high_value_count']}")

    # Print review class counts if available
    if "review_class_counts" in planning:
        print("\nReview class counts:")
        class_counts = planning["review_class_counts"]
        for rc_class, count in sorted(class_counts.items()):
            print(f"  {rc_class}: {count}")

    # Print high-priority composition if available
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

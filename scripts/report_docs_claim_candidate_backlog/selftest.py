"""Self-tests for documentation claim candidate backlog reporter."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .model import (
    REVIEW_CLASS_CLAIM_CANDIDATE,
    REVIEW_CLASS_COVERED_OR_REGISTERED,
    REVIEW_CLASS_NON_NORMATIVE_PROSE,
    REVIEW_CLASS_REVIEWED_LOW_VALUE,
    REVIEW_CLASS_STALE_OR_HISTORICAL,
    REVIEW_CLASS_STRUCTURAL_FRAGMENT,
    classify_review_class,
    compute_calibrated_score,
    compute_risk_score,
    is_cleanup_class,
    is_generic_low_value_note,
)
from .planning import ACTION_CONTINUE_LARGE_TRANCHE, ACTION_CONTINUE_SMALL_TARGETED, ACTION_PAUSE_MANUAL_TRANCHES, CAVEAT_CLAIM_CANDIDATE_HEAVY, CAVEAT_CLEANUP_HEAVY, CAVEAT_MIXED, compute_planning_summary, get_priority_band
from .report import filter_entries, write_json, write_tsv
from .selftest_fixtures import (
    make_claim_candidate_entry,
    make_claim_candidate_heavy_entries,
    make_cleanup_heavy_entries,
    make_covered_entry,
    make_generic_ignored_entry,
    make_json_test_entries,
    make_json_test_summary,
    make_large_tranche_entries,
    make_mixed_entries,
    make_pause_entries,
    make_small_tranche_entries,
    make_stale_entry,
    make_structural_fragment_entry,
)

# Valid priority bands for testing
ALL_PRIORITY_BANDS = ["P0", "P1", "P2", "P3", "P4"]


def run_self_test() -> bool:
    print("=== Self-Test Fixtures ===\n")
    all_passed = True
    def check(name: str, cond: bool, msg: str = ""):
        nonlocal all_passed
        if cond: print(f"[PASS] {name}")  # noqa: E701
        else: print(f"[FAIL] {name}: {msg}"); all_passed = False  # noqa: E701,E702

    # =====================================================================
    # Basic review class classification tests
    # =====================================================================
    check("table fragment -> structural_fragment",
        classify_review_class("ignored_by_policy", "generated_from_table_fragment",
            "Table fragment from docs/foo.md", False, "docs/foo.md", {}, "Table row data")[0]
        == REVIEW_CLASS_STRUCTURAL_FRAGMENT)
    check("schema field label -> structural_fragment",
        classify_review_class("ignored_by_policy", "schema_field_label",
            "Schema field label", False, "docs/foo.md", {}, "field_name")[0]
        == REVIEW_CLASS_STRUCTURAL_FRAGMENT)
    check("descriptive prose -> non_normative_prose",
        classify_review_class("ignored_by_policy", "non_normative_description",
            "Descriptive prose fragment", False, "docs/foo.md", {},
            "This is a description of how things work.")[0]
        == REVIEW_CLASS_NON_NORMATIVE_PROSE)
    check("ACT reviewed row -> reviewed_low_value",
        classify_review_class("ignored_by_policy", "low_value_context",
            "ACT 5.4 review: Low-value prose fragment", True, "docs/foo.md", {}, "Some text")[0]
        == REVIEW_CLASS_REVIEWED_LOW_VALUE)
    check("stale disposition -> stale_or_historical",
        classify_review_class("stale", "stale_doc", "From stale doc",
            False, "docs/foo.md", {}, "Some text")[0]
        == REVIEW_CLASS_STALE_OR_HISTORICAL)
    check("covered disposition -> covered_or_registered",
        classify_review_class("covered_by_existing_claim", "covered_by_broader_claim",
            "Already covered", False, "docs/foo.md", {}, "Some text")[0]
        == REVIEW_CLASS_COVERED_OR_REGISTERED)
    check("structural + MUST -> structural (not claim)",
        classify_review_class("ignored_by_policy", "generated_from_table_fragment",
            "Table fragment with MUST keyword", False, "docs/foo.md", {},
            "Table row must have field")[0]
        == REVIEW_CLASS_STRUCTURAL_FRAGMENT)

    # =====================================================================
    # True-positive claim_candidate tests (real behavioral claims)
    # These MUST be classified as claim_candidate
    # =====================================================================

    # Test 1: generic note + strong real claim with system subject -> claim_candidate
    result1, reasons1 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/security/auth.md", False,
        "docs/security/auth.md", {},
        "The backend must reject unauthenticated artifact requests"
    )
    check("generic note + backend must reject -> claim_candidate",
        result1 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result1} {reasons1}")

    # Test 2: generic note + evidence artifact + append-only -> claim_candidate
    result2, reasons2 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/evidence/policy.md", False,
        "docs/evidence/policy.md", {},
        "Evidence artifacts must be append-only"
    )
    check("generic note + artifacts must be append-only -> claim_candidate",
        result2 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result2} {reasons2}")

    # Test 3: generic note + API + must not -> claim_candidate
    result3, reasons3 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Custom note", False, "docs/api/security.md", {},
        "The API must not expose raw secrets"
    )
    check("generic note + API must not expose -> claim_candidate",
        result3 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result3} {reasons3}")

    # Test 4: generic note + snapshots + source of truth -> claim_candidate
    result4, reasons4 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/runtime/status.md", False,
        "docs/runtime/status.md", {},
        "Snapshots are the source of truth for runtime status"
    )
    check("generic note + snapshots source of truth -> claim_candidate",
        result4 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result4} {reasons4}")

    # Test 5: generic note + read-only checks + cannot -> claim_candidate
    result5, reasons5 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/security/checks.md", False,
        "docs/security/checks.md", {},
        "Read-only checks cannot mutate the cluster"
    )
    check("generic note + read-only cannot mutate -> claim_candidate",
        result5 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result5} {reasons5}")

    # Test 6: generic note + system + must handle -> claim_candidate (original test)
    result6, reasons6 = classify_review_class(
        "ignored_by_policy", "low_value_context", "Custom note",
        False, "docs/security/auth.md", {},
        "The system must handle authentication securely."
    )
    check("generic note + MUST (with system subject) -> claim_candidate",
        result6 == REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result6} {reasons6}")

    # =====================================================================
    # False-positive claim_candidate tests (generic prose with broad terms)
    # These should NOT be classified as claim_candidate
    # =====================================================================

    # Test 7: schema field + required -> NOT claim_candidate (structural)
    result7, reasons7 = classify_review_class(
        "ignored_by_policy", "schema_field_label",
        "Schema field label", False, "docs/schemas/incident.md", {},
        "This field is required"
    )
    check("schema field + required -> NOT claim_candidate",
        result7 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result7} {reasons7}")

    # Test 8: policy doc + "never reused" -> NOT claim_candidate (policy/meta)
    result8, reasons8 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/doctrine/documentation-truthfulness.md",
        False, "docs/doctrine/documentation-truthfulness.md", {},
        "IDs are never reused"
    )
    check("docs-truthfulness + never -> NOT claim_candidate",
        result8 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result8} {reasons8}")

    # Test 9: backlog/worklist + only include -> NOT claim_candidate (policy)
    result9, reasons9 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/post-beta-backlog.md",
        False, "docs/post-beta-backlog.md", {},
        "Only include artifacts that are production-ready"
    )
    check("backlog + only include -> NOT claim_candidate",
        result9 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result9} {reasons9}")

    # Test 10: claim-process doc + must review -> NOT claim_candidate (meta)
    result10, reasons10 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/doctrine/documentation-truthfulness.md",
        False, "docs/doctrine/documentation-truthfulness.md", {},
        "Claims must be reviewed manually before disposition"
    )
    check("claim-process + must review -> NOT claim_candidate",
        result10 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result10} {reasons10}")

    # Test 11: design doc + must -> NOT claim_candidate (design/future)
    result11, reasons11 = classify_review_class(
        "ignored_by_policy", "design_or_future_note",
        "Design note", False, "docs/doctrine/playbooks/redesign_staging.md", {},
        "If rollback is not possible, that must be treated as a one-way door"
    )
    check("design note + must -> NOT claim_candidate",
        result11 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result11} {reasons11}")

    # Test 12: impact scan + behavior risk + must -> NOT claim_candidate (design)
    result12, reasons12 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/reports/impact-scan-ledger.md",
        False, "docs/reports/impact-scan-ledger.md", {},
        "Queue status filters must remain unchanged"
    )
    check("impact scan + must remain -> NOT claim_candidate",
        result12 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result12} {reasons12}")

    # Test 13: generic note + required (without claim shape) -> NOT claim_candidate
    result13, reasons13 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/foo.md", False, "docs/foo.md", {},
        "This field is required for operation."
    )
    check("generic note + required (no claim shape) -> NOT claim_candidate",
        result13 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result13} {reasons13}")

    # Test 14: CI gate drift doc + gate -> NOT claim_candidate (meta)
    result14, reasons14 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/ci-gate-drift.md",
        False, "docs/ci-gate-drift.md", {},
        "Gate is not represented in CI but has a valid reason"
    )
    check("ci-gate-drift + gate -> NOT claim_candidate",
        result14 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result14} {reasons14}")

    # Test 15: documentation-truthfulness + verifier -> NOT claim_candidate (meta)
    result15, reasons15 = classify_review_class(
        "ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/doctrine/documentation-truthfulness.md",
        False, "docs/doctrine/documentation-truthfulness.md", {},
        "Coverage verifier: scripts/verifydocsclaimcandidatecoverage.py"
    )
    check("docs-truthfulness + verifier -> NOT claim_candidate",
        result15 != REVIEW_CLASS_CLAIM_CANDIDATE, f"got {result15} {reasons15}")

    # =====================================================================
    # Score calibration tests
    # =====================================================================
    check("structural_fragment -30 penalty", compute_calibrated_score(42, REVIEW_CLASS_STRUCTURAL_FRAGMENT) == 12)
    check("non_normative_prose -25 penalty", compute_calibrated_score(42, REVIEW_CLASS_NON_NORMATIVE_PROSE) == 17)
    check("claim_candidate +20 boost", compute_calibrated_score(42, REVIEW_CLASS_CLAIM_CANDIDATE) == 62)
    check("reviewed_low_value -40 penalty", compute_calibrated_score(42, REVIEW_CLASS_REVIEWED_LOW_VALUE) == 2)
    check("stale_or_historical -30 penalty", compute_calibrated_score(42, REVIEW_CLASS_STALE_OR_HISTORICAL) == 12)

    # =====================================================================
    # is_cleanup_class tests
    # =====================================================================
    check("structural_fragment is cleanup", is_cleanup_class(REVIEW_CLASS_STRUCTURAL_FRAGMENT))
    check("non_normative_prose is cleanup", is_cleanup_class(REVIEW_CLASS_NON_NORMATIVE_PROSE))
    check("claim_candidate is NOT cleanup", not is_cleanup_class(REVIEW_CLASS_CLAIM_CANDIDATE))

    # =====================================================================
    # Risk score tests
    # =====================================================================
    score1, r1 = compute_risk_score("ignored_by_policy", "low_value_context",
        "Low-value prose fragment from: docs/foo.md", "docs/security/bar.md",
        "This must be handled securely.", {}, False, False)
    check("ranks generic ignored note", score1 > 30 and "generic_ignored_note" in r1 and "high_value_doc:security" in r1)
    score2, r2 = compute_risk_score("ignored_by_policy", "low_value_context",
        "Some note (ACT 5.0 review)", "docs/security/bar.md",
        "This must be handled securely.", {}, True, False)
    check("deprioritizes ACT 5.0 reviewed", score2 < 0 and "deprioritized:act_5_0_reviewed" in r2)
    score3, r3 = compute_risk_score("ignored_by_policy", "low_value_context",
        "Some note (ACT 5.2 review)", "docs/security/bar.md",
        "This must be handled securely.", {}, False, True)
    check("deprioritizes ACT 5.2 reviewed", score3 < 0 and "deprioritized:act_5_2_reviewed" in r3)
    score4, r4 = compute_risk_score("ignored_by_policy", "low_value_context",
        "Some generic note", "docs/security/auth.md", "Normal text here.",
        {"docs/security/auth.md": "current"}, False, False)
    check("high-value doc increases score", "high_value_doc:security" in r4 and "high_value_doc:auth" in r4 and score4 > 10)
    score5, r5 = compute_risk_score("ignored_by_policy", "low_value_context",
        "Some generic note", "docs/normal.md",
        "The system must handle authentication correctly.", {}, False, False)
    check("normative text increases score", "normative_text" in r5 and score5 > 10)
    score6, r6 = compute_risk_score("stale", "stale_doc", "Some generic note",
        "docs/old/design.md", "Some text.", {"docs/old/design.md": "stale"}, False, False)
    check("stale rows deprioritized", "deprioritized:stale" in r6)
    score7, r7 = compute_risk_score("covered_by_existing_claim", "covered_by_broader_claim",
        "Low-value prose fragment from: docs/foo.md", "docs/normal.md", "Some text.", {}, False, False)
    check("covered_note_weak flagged", "covered_note_weak" in r7)
    check("generic note pattern", is_generic_low_value_note("Low-value prose fragment from: docs/foo.md"))

    # =====================================================================
    # Filter tests
    # =====================================================================
    # Create mixed entries for filter testing
    mixed_entries = [
        make_claim_candidate_entry("DOC-CAND-001", 62),
        make_claim_candidate_entry("DOC-CAND-002", 52),
        make_generic_ignored_entry("DOC-CAND-003", score=32),
        make_structural_fragment_entry("DOC-CAND-004", 22),
        make_stale_entry("DOC-CAND-005", -12),
        make_covered_entry("DOC-CAND-006", 0),
    ]

    # Test 1: filter by single review_class
    filtered = filter_entries(mixed_entries, review_classes={"claim_candidate"})
    check("filter by single review_class", len(filtered) == 2 and all(e["review_class"] == "claim_candidate" for e in filtered))

    # Test 2: filter by multiple review_class values
    filtered = filter_entries(mixed_entries, review_classes={"claim_candidate", "non_normative_prose"})
    check("filter by multiple review_class values", len(filtered) == 3 and all(
        e["review_class"] in ("claim_candidate", "non_normative_prose") for e in filtered))

    # Test 3: filter by single priority_band (P0)
    filtered = filter_entries(mixed_entries, priority_bands={"P0"})
    check("filter by single priority_band (P0)", len(filtered) == 2)

    # Test 4: filter by multiple priority_band values (P0, P3)
    filtered = filter_entries(mixed_entries, priority_bands={"P0", "P3"})
    check("filter by multiple priority_band values", len(filtered) == 3)

    # Test 5: filter combines review_class + priority_band as AND
    filtered = filter_entries(mixed_entries, review_classes={"claim_candidate"}, priority_bands={"P0"})
    check("filter combines review_class + priority_band as AND", len(filtered) == 2)

    # Test 6: filter preserves ranking order
    filtered = filter_entries(mixed_entries, review_classes={"claim_candidate"})
    ids = [e["candidate_id"] for e in filtered]
    check("filter preserves ranking order", ids == ["DOC-CAND-001", "DOC-CAND-002"])

    # Test 7: no filter returns copy (different list object, same contents)
    filtered = filter_entries(mixed_entries)
    check("no filter returns copy", len(filtered) == len(mixed_entries) and filtered is not mixed_entries)

    # Test 8: claim_candidate filter returns only claim_candidate rows
    filtered = filter_entries(mixed_entries, review_classes={"claim_candidate"})
    check("claim_candidate filter returns only claim_candidate rows",
        all(e["review_class"] == "claim_candidate" for e in filtered))

    # Test 9: structural/non_normative filters return cleanup rows
    filtered = filter_entries(mixed_entries, review_classes={"structural_fragment"})
    check("structural_fragment filter returns structural rows",
        all(e["review_class"] == "structural_fragment" for e in filtered))
    filtered = filter_entries(mixed_entries, review_classes={"non_normative_prose"})
    check("non_normative_prose filter returns non-normative rows",
        all(e["review_class"] == "non_normative_prose" for e in filtered))

    # Test 10: invalid review_class would fail (test validation logic indirectly)
    try:
        from .__main__ import _validate_review_classes
        _validate_review_classes(["bogus"])
        check("invalid review_class is rejected", False, "Should have raised")
    except (SystemExit, argparse.ArgumentTypeError):
        check("invalid review_class is rejected", True)

    # Test 11: invalid priority_band would fail (test validation logic indirectly)
    try:
        from .__main__ import _validate_priority_bands
        _validate_priority_bands(["P9"])
        check("invalid priority_band is rejected", False, "Should have raised")
    except (SystemExit, argparse.ArgumentTypeError):
        check("invalid priority_band is rejected", True)

    # =====================================================================
    # Planning caveat tests
    # =====================================================================
    cleanup_planning = compute_planning_summary(make_cleanup_heavy_entries())
    check("cleanup-heavy caveat", cleanup_planning.get("planning_caveat") == CAVEAT_CLEANUP_HEAVY,
        str(cleanup_planning.get("planning_caveat")))
    claim_planning = compute_planning_summary(make_claim_candidate_heavy_entries())
    check("claim-candidate-heavy caveat", claim_planning.get("planning_caveat") == CAVEAT_CLAIM_CANDIDATE_HEAVY,
        str(claim_planning.get("planning_caveat")))
    mixed_planning = compute_planning_summary(make_mixed_entries())
    check("mixed caveat", mixed_planning.get("planning_caveat") == CAVEAT_MIXED,
        str(mixed_planning.get("planning_caveat")))

    # =====================================================================
    # Priority band tests
    # =====================================================================
    check("score 42 -> P0", get_priority_band(42) == "P0")
    check("score 34 -> P1", get_priority_band(34) == "P1")
    check("score 24 -> P2", get_priority_band(24) == "P2")
    check("score 1 -> P3", get_priority_band(1) == "P3")
    check("score 0 -> P4", get_priority_band(0) == "P4")

    # =====================================================================
    # JSON/TSV output tests
    # =====================================================================
    test_entries = make_json_test_entries()
    test_summary = make_json_test_summary()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f: json_path = Path(f.name)
    try:
        write_json(test_entries, test_summary, json_path)
        with open(json_path) as f:
            data = json.load(f)
        check("JSON output structure", data["total_candidates"] == 2 and "disposition_counts" in data
            and len(data["recommended_candidates"]) == 2)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f2: json_path2 = Path(f2.name)
        try:
            write_json(test_entries, test_summary, json_path2)
            with open(json_path) as f1: data1 = json.load(f1)
            with open(json_path2) as f2: data2 = json.load(f2)
            check("JSON determinism", data1 == data2)
        finally: os.unlink(json_path2)
    finally: os.unlink(json_path)

    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f: tsv_path = Path(f.name)
    try:
        write_tsv(test_entries, tsv_path)
        with open(tsv_path) as f: lines = f.readlines()
        expected = "score\tpriority_band\treview_class\treview_class_reasons\tcandidate_id\tdisposition\treason_code\tsource_doc_path\trisk_reasons\treviewed_at\treviewer_notes\tcandidate_text\n"
        check("TSV columns/order", lines and lines[0] == expected)
    finally: os.unlink(tsv_path)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f: json_rc_path = Path(f.name)
    try:
        write_json(test_entries, test_summary, json_rc_path)
        with open(json_rc_path) as f: data = json.load(f)
        rec = data["recommended_candidates"][0]
        check("JSON has review_class", "review_class" in rec and "review_class_reasons" in rec)
    finally: os.unlink(json_rc_path)

    # Test JSON filters block
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f: json_filter_path = Path(f.name)
    try:
        filters = {"disposition": None, "doc": None, "include_reviewed": False,
                   "review_class": ["claim_candidate"], "priority_band": ["P0", "P1"]}
        write_json(test_entries, test_summary, json_filter_path, filters=filters)
        with open(json_filter_path) as f: data = json.load(f)
        check("JSON filters block exists", "filters" in data)
        check("JSON filters block is sorted", list(data["filters"].keys()) == sorted(data["filters"].keys()))
        check("JSON filters block values", data["filters"]["review_class"] == ["claim_candidate"])
    finally: os.unlink(json_filter_path)

    # Test TSV output respects review_class filter
    filtered_entries = filter_entries(test_entries, review_classes={"claim_candidate"})
    if filtered_entries:
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f: tsv_filter_path = Path(f.name)
        try:
            write_tsv(filtered_entries, tsv_filter_path)
            with open(tsv_filter_path) as f: lines = f.readlines()
            check("TSV output respects review_class filter", len(lines) == 2)
        finally: os.unlink(tsv_filter_path)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f: json_plan_path = Path(f.name)
    try:
        planning = compute_planning_summary(test_entries)
        write_json(test_entries, test_summary, json_plan_path, include_planning=True, planning=planning)
        with open(json_plan_path) as f: data = json.load(f)
        p = data.get("planning", {})
        check("planning has review_class_counts", "review_class_counts" in p and "priority_by_review_class" in p)
        check("planning has high-priority counts", "claim_candidate_high_priority_count" in p and "cleanup_high_priority_count" in p)
        check("planning has planning_caveat", "planning_caveat" in p)
    finally: os.unlink(json_plan_path)

    # =====================================================================
    # Recommendation action tests
    # =====================================================================
    large_planning = compute_planning_summary(make_large_tranche_entries())
    check("P0+P1>=100 -> continue_large_tranche",
        large_planning["recommended_next_action"] == ACTION_CONTINUE_LARGE_TRANCHE)
    small_planning = compute_planning_summary(make_small_tranche_entries())
    check("P0+P1=25-99 -> continue_small_targeted",
        small_planning["recommended_next_action"] == ACTION_CONTINUE_SMALL_TARGETED)
    pause_planning = compute_planning_summary(make_pause_entries())
    check("P0+P1<25 -> pause_manual_tranches",
        pause_planning["recommended_next_action"] == ACTION_PAUSE_MANUAL_TRANCHES)

    print()
    if all_passed:
        print("[PASS] all self-tests passed")
        return True
    print("[FAIL] some self-tests failed")
    return False


if __name__ == "__main__":
    success = run_self_test()
    sys.exit(0 if success else 1)
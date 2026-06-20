"""Self-tests for documentation claim candidate backlog reporter."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from .model import (REVIEW_CLASS_CLAIM_CANDIDATE, REVIEW_CLASS_COVERED_OR_REGISTERED,
    REVIEW_CLASS_NON_NORMATIVE_PROSE, REVIEW_CLASS_REVIEWED_LOW_VALUE,
    REVIEW_CLASS_STALE_OR_HISTORICAL, REVIEW_CLASS_STRUCTURAL_FRAGMENT,
    classify_review_class, compute_calibrated_score, compute_risk_score,
    is_cleanup_class, is_generic_low_value_note)
from .planning import (ACTION_CONTINUE_LARGE_TRANCHE, ACTION_CONTINUE_SMALL_TARGETED,
    ACTION_PAUSE_MANUAL_TRANCHES, CAVEAT_CLAIM_CANDIDATE_HEAVY, CAVEAT_CLEANUP_HEAVY,
    CAVEAT_MIXED, compute_planning_summary, get_priority_band)
from .report import write_json, write_tsv
from .selftest_fixtures import (make_claim_candidate_heavy_entries, make_cleanup_heavy_entries,
    make_json_test_entries, make_json_test_summary, make_large_tranche_entries,
    make_mixed_entries, make_pause_entries, make_small_tranche_entries)

def run_self_test() -> bool:
    print("=== Self-Test Fixtures ===\n")
    all_passed = True
    def check(name: str, cond: bool, msg: str = ""):
        nonlocal all_passed
        if cond: print(f"[PASS] {name}")
        else: print(f"[FAIL] {name}: {msg}"); all_passed = False

    # Review class classification tests
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
    check("MUST candidate -> claim_candidate",
        classify_review_class("ignored_by_policy", "low_value_context", "Custom note",
            False, "docs/security/auth.md", {},
            "The system must handle authentication securely.")[0]
        == REVIEW_CLASS_CLAIM_CANDIDATE)
    check("structural + MUST -> structural (not claim)",
        classify_review_class("ignored_by_policy", "generated_from_table_fragment",
            "Table fragment with MUST keyword", False, "docs/foo.md", {},
            "Table row must have field")[0]
        == REVIEW_CLASS_STRUCTURAL_FRAGMENT)
    check("generic note + MUST -> claim_candidate",
        classify_review_class("ignored_by_policy", "low_value_context",
            "Low-value prose fragment from: docs/security/auth.md", False,
            "docs/security/auth.md", {},
            "The system must handle authentication securely.")[0]
        == REVIEW_CLASS_CLAIM_CANDIDATE)
    check("generic note + required -> claim_candidate",
        classify_review_class("ignored_by_policy", "low_value_context",
            "Low-value prose fragment from: docs/foo.md", False, "docs/foo.md", {},
            "This field is required for operation.")[0]
        == REVIEW_CLASS_CLAIM_CANDIDATE)

    # Score calibration tests
    check("structural_fragment -30 penalty", compute_calibrated_score(42, REVIEW_CLASS_STRUCTURAL_FRAGMENT) == 12)
    check("non_normative_prose -25 penalty", compute_calibrated_score(42, REVIEW_CLASS_NON_NORMATIVE_PROSE) == 17)
    check("claim_candidate +20 boost", compute_calibrated_score(42, REVIEW_CLASS_CLAIM_CANDIDATE) == 62)
    check("reviewed_low_value -40 penalty", compute_calibrated_score(42, REVIEW_CLASS_REVIEWED_LOW_VALUE) == 2)
    check("stale_or_historical -30 penalty", compute_calibrated_score(42, REVIEW_CLASS_STALE_OR_HISTORICAL) == 12)

    # is_cleanup_class tests
    check("structural_fragment is cleanup", is_cleanup_class(REVIEW_CLASS_STRUCTURAL_FRAGMENT))
    check("non_normative_prose is cleanup", is_cleanup_class(REVIEW_CLASS_NON_NORMATIVE_PROSE))
    check("claim_candidate is NOT cleanup", not is_cleanup_class(REVIEW_CLASS_CLAIM_CANDIDATE))

    # Risk score tests
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

    # Planning caveat tests
    cleanup_planning = compute_planning_summary(make_cleanup_heavy_entries())
    check("cleanup-heavy caveat", cleanup_planning.get("planning_caveat") == CAVEAT_CLEANUP_HEAVY,
        str(cleanup_planning.get("planning_caveat")))
    claim_planning = compute_planning_summary(make_claim_candidate_heavy_entries())
    check("claim-candidate-heavy caveat", claim_planning.get("planning_caveat") == CAVEAT_CLAIM_CANDIDATE_HEAVY,
        str(claim_planning.get("planning_caveat")))
    mixed_planning = compute_planning_summary(make_mixed_entries())
    check("mixed caveat", mixed_planning.get("planning_caveat") == CAVEAT_MIXED,
        str(mixed_planning.get("planning_caveat")))

    # Priority band tests
    check("score 42 -> P0", get_priority_band(42) == "P0")
    check("score 34 -> P1", get_priority_band(34) == "P1")
    check("score 24 -> P2", get_priority_band(24) == "P2")
    check("score 1 -> P3", get_priority_band(1) == "P3")
    check("score 0 -> P4", get_priority_band(0) == "P4")

    # JSON/TSV output tests
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

    # Recommendation action tests
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

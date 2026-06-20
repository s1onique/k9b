"""Self-tests for documentation claim candidate backlog reporter."""

from __future__ import annotations

import json
import os
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
from .planning import (
    ACTION_CONTINUE_LARGE_TRANCHE,
    ACTION_CONTINUE_SMALL_TARGETED,
    ACTION_PAUSE_MANUAL_TRANCHES,
    CAVEAT_CLAIM_CANDIDATE_HEAVY,
    CAVEAT_CLEANUP_HEAVY,
    CAVEAT_MIXED,
    compute_planning_summary,
    get_priority_band,
)
from .report import write_json, write_tsv


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    print("=== Self-Test Fixtures ===\n")

    all_passed = True

    # === Review class classification tests ===

    # Fixture RC1: table fragment classifies as structural_fragment
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="generated_from_table_fragment",
        notes="Table fragment from docs/foo.md",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="Table row data",
    )
    if rc == REVIEW_CLASS_STRUCTURAL_FRAGMENT:
        print("[PASS] table fragment classifies as structural_fragment")
    else:
        print(f"[FAIL] table fragment: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC2: schema field label classifies as structural_fragment
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="schema_field_label",
        notes="Schema field label",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="field_name",
    )
    if rc == REVIEW_CLASS_STRUCTURAL_FRAGMENT:
        print("[PASS] schema field label classifies as structural_fragment")
    else:
        print(f"[FAIL] schema field label: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC3: descriptive prose classifies as non_normative_prose
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="non_normative_description",
        notes="Descriptive prose fragment",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="This is a description of how things work.",
    )
    if rc == REVIEW_CLASS_NON_NORMATIVE_PROSE:
        print("[PASS] descriptive prose classifies as non_normative_prose")
    else:
        print(f"[FAIL] descriptive prose: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC4: ACT reviewed row classifies as reviewed_low_value
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="ACT 5.4 review: Low-value prose fragment",
        has_any_act_marker=True,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="Some text",
    )
    if rc == REVIEW_CLASS_REVIEWED_LOW_VALUE:
        print("[PASS] ACT reviewed row classifies as reviewed_low_value")
    else:
        print(f"[FAIL] ACT reviewed row: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC5: stale disposition classifies as stale_or_historical
    rc, reasons = classify_review_class(
        disposition="stale",
        reason_code="stale_doc",
        notes="From stale doc",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="Some text",
    )
    if rc == REVIEW_CLASS_STALE_OR_HISTORICAL:
        print("[PASS] stale disposition classifies as stale_or_historical")
    else:
        print(f"[FAIL] stale disposition: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC6: covered disposition classifies as covered_or_registered
    rc, reasons = classify_review_class(
        disposition="covered_by_existing_claim",
        reason_code="covered_by_broader_claim",
        notes="Already covered",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="Some text",
    )
    if rc == REVIEW_CLASS_COVERED_OR_REGISTERED:
        print("[PASS] covered disposition classifies as covered_or_registered")
    else:
        print(f"[FAIL] covered disposition: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC7: strong MUST candidate classifies as claim_candidate
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Custom note",
        has_any_act_marker=False,
        doc_path="docs/security/auth.md",
        inventory={},
        candidate_text="The system must handle authentication securely.",
    )
    if rc == REVIEW_CLASS_CLAIM_CANDIDATE:
        print("[PASS] strong MUST candidate classifies as claim_candidate")
    else:
        print(f"[FAIL] MUST candidate: got {rc}, reasons={reasons}")
        all_passed = False

    # Fixture RC8: structural table fragment with normative words still classifies as structural
    rc, reasons = classify_review_class(
        disposition="ignored_by_policy",
        reason_code="generated_from_table_fragment",
        notes="Table fragment with MUST keyword",
        has_any_act_marker=False,
        doc_path="docs/foo.md",
        inventory={},
        candidate_text="Table row must have field",
    )
    if rc == REVIEW_CLASS_STRUCTURAL_FRAGMENT:
        print("[PASS] structural table fragment with normative words still classifies as structural")
    else:
        print(f"[FAIL] structural with MUST: got {rc}, reasons={reasons}")
        all_passed = False

    # === Score calibration tests ===

    # Fixture SC1: structural_fragment receives penalty
    calibrated = compute_calibrated_score(42, REVIEW_CLASS_STRUCTURAL_FRAGMENT)
    if calibrated == 12:  # 42 - 30
        print("[PASS] structural_fragment receives -30 score penalty")
    else:
        print(f"[FAIL] structural_fragment penalty: got {calibrated}, expected 12")
        all_passed = False

    # Fixture SC2: non_normative_prose receives penalty
    calibrated = compute_calibrated_score(42, REVIEW_CLASS_NON_NORMATIVE_PROSE)
    if calibrated == 17:  # 42 - 25
        print("[PASS] non_normative_prose receives -25 score penalty")
    else:
        print(f"[FAIL] non_normative_prose penalty: got {calibrated}, expected 17")
        all_passed = False

    # Fixture SC3: claim_candidate receives boost
    calibrated = compute_calibrated_score(42, REVIEW_CLASS_CLAIM_CANDIDATE)
    if calibrated == 62:  # 42 + 20
        print("[PASS] claim_candidate receives +20 score boost")
    else:
        print(f"[FAIL] claim_candidate boost: got {calibrated}, expected 62")
        all_passed = False

    # Fixture SC4: reviewed_low_value receives strong penalty
    calibrated = compute_calibrated_score(42, REVIEW_CLASS_REVIEWED_LOW_VALUE)
    if calibrated == 2:  # 42 - 40
        print("[PASS] reviewed_low_value receives -40 score penalty")
    else:
        print(f"[FAIL] reviewed_low_value penalty: got {calibrated}, expected 2")
        all_passed = False

    # Fixture SC5: stale_or_historical receives penalty
    calibrated = compute_calibrated_score(42, REVIEW_CLASS_STALE_OR_HISTORICAL)
    if calibrated == 12:  # 42 - 30
        print("[PASS] stale_or_historical receives -30 score penalty")
    else:
        print(f"[FAIL] stale_or_historical penalty: got {calibrated}, expected 12")
        all_passed = False

    # === is_cleanup_class tests ===

    # Fixture CL1: structural_fragment is cleanup
    if is_cleanup_class(REVIEW_CLASS_STRUCTURAL_FRAGMENT):
        print("[PASS] structural_fragment is cleanup class")
    else:
        print("[FAIL] structural_fragment should be cleanup class")
        all_passed = False

    # Fixture CL2: non_normative_prose is cleanup
    if is_cleanup_class(REVIEW_CLASS_NON_NORMATIVE_PROSE):
        print("[PASS] non_normative_prose is cleanup class")
    else:
        print("[FAIL] non_normative_prose should be cleanup class")
        all_passed = False

    # Fixture CL3: claim_candidate is NOT cleanup
    if not is_cleanup_class(REVIEW_CLASS_CLAIM_CANDIDATE):
        print("[PASS] claim_candidate is NOT cleanup class")
    else:
        print("[FAIL] claim_candidate should NOT be cleanup class")
        all_passed = False

    # === Existing fixtures preserved for backward compatibility ===

    # Fixture 1: generic ignored note is scored and ranked
    score1, reasons1 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Low-value prose fragment from: docs/foo.md",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if score1 > 30 and "generic_ignored_note" in reasons1 and "high_value_doc:security" in reasons1:
        print("[PASS] ranks generic ignored note")
    else:
        print(f"[FAIL] ranks generic ignored note: score={score1}, reasons={reasons1}")
        all_passed = False

    # Fixture 2: ACT 5.0 reviewed row is deprioritized
    score2, reasons2 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some note (ACT 5.0 review)",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=True,
        has_act_5_2=False,
    )
    if score2 < 0 and "deprioritized:act_5_0_reviewed" in reasons2:
        print("[PASS] deprioritizes ACT 5.0 reviewed row")
    else:
        print(f"[FAIL] deprioritizes ACT 5.0: score={score2}, reasons={reasons2}")
        all_passed = False

    # Fixture 3: ACT 5.2 reviewed row is deprioritized
    score3, reasons3 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some note (ACT 5.2 review)",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=True,
    )
    if score3 < 0 and "deprioritized:act_5_2_reviewed" in reasons3:
        print("[PASS] deprioritizes ACT 5.2 reviewed row")
    else:
        print(f"[FAIL] deprioritizes ACT 5.2: score={score3}, reasons={reasons3}")
        all_passed = False

    # Fixture 4: high-value doc path increases score
    score4, reasons4 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some generic note",
        doc_path="docs/security/auth.md",
        candidate_text="Normal text here.",
        inventory={"docs/security/auth.md": "current"},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "high_value_doc:security" in reasons4 and "high_value_doc:auth" in reasons4 and score4 > 10:
        print("[PASS] high-value doc path increases score")
    else:
        print(f"[FAIL] high-value doc: score={score4}, reasons={reasons4}")
        all_passed = False

    # Fixture 5: normative candidate text increases score
    score5, reasons5 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some generic note",
        doc_path="docs/normal.md",
        candidate_text="The system must handle authentication correctly.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "normative_text" in reasons5 and score5 > 10:
        print("[PASS] normative candidate text increases score")
    else:
        print(f"[FAIL] normative text: score={score5}, reasons={reasons5}")
        all_passed = False

    # Fixture 6: stale/historical rows are normally deprioritized
    score6, reasons6 = compute_risk_score(
        disposition="stale",
        reason_code="stale_doc",
        notes="Some generic note",
        doc_path="docs/old/design.md",
        candidate_text="Some text.",
        inventory={"docs/old/design.md": "stale"},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "deprioritized:stale" in reasons6:
        print("[PASS] stale rows deprioritized")
    else:
        print(f"[FAIL] stale deprioritization: score={score6}, reasons={reasons6}")
        all_passed = False

    # Fixture 7: covered_by_existing_claim with weak note is flagged
    score7, reasons7 = compute_risk_score(
        disposition="covered_by_existing_claim",
        reason_code="covered_by_broader_claim",
        notes="Low-value prose fragment from: docs/foo.md",
        doc_path="docs/normal.md",
        candidate_text="Some text.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "covered_note_weak" in reasons7:
        print("[PASS] covered_by_existing_claim with weak note flagged")
    else:
        print(f"[FAIL] covered_note_weak: score={score7}, reasons={reasons7}")
        all_passed = False

    # Fixture 10: generic note pattern detection
    if is_generic_low_value_note("Low-value prose fragment from: docs/foo.md"):
        print("[PASS] generic note pattern detection")
    else:
        print("[FAIL] generic note pattern detection")
        all_passed = False

    # === Planning caveat tests ===

    # Fixture PC1: cleanup-heavy caveat when P0/P1 dominated by structural/non-normative
    # Need base score >= 72 for structural to get calibrated >= 42 (72 - 30 = 42)
    # Need base score >= 67 for non-normative to get calibrated >= 42 (67 - 25 = 42)
    cleanup_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(60):
        cleanup_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "generated_from_table_fragment",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Table row.",
            "reviewed_at": "",
            "reviewer_notes": "Table fragment.",
            "score": 72,  # Base score
            "calibrated_score": 42,  # After -30 calibration: 72 - 30 = 42
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security", "normative_text"],
            "review_class": REVIEW_CLASS_STRUCTURAL_FRAGMENT,
            "review_class_reasons": ["structural:generated_from_table_fragment"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    for i in range(60, 100):
        cleanup_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "non_normative_description",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Descriptive prose.",
            "reviewed_at": "",
            "reviewer_notes": "Descriptive prose fragment.",
            "score": 67,  # Base score
            "calibrated_score": 42,  # After -25 calibration: 67 - 25 = 42
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security", "normative_text"],
            "review_class": REVIEW_CLASS_NON_NORMATIVE_PROSE,
            "review_class_reasons": ["non_normative:non_normative_description"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    cleanup_planning = compute_planning_summary(cleanup_entries)
    if cleanup_planning.get("planning_caveat") == CAVEAT_CLEANUP_HEAVY:
        print("[PASS] cleanup-heavy caveat when P0+P1 dominated by cleanup rows")
    else:
        print(f"[FAIL] cleanup-heavy caveat: got {cleanup_planning.get('planning_caveat')}")
        all_passed = False

    # Fixture PC2: claim-candidate-heavy caveat when P0+P1 dominated by claim_candidate
    claim_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(60):
        claim_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "The system must handle authentication.",
            "reviewed_at": "",
            "reviewer_notes": "Strong MUST requirement.",
            "score": 42,
            "calibrated_score": 62,  # After +20 calibration
            "risk_reasons": ["generic_ignored_note", "normative_text"],
            "review_class": REVIEW_CLASS_CLAIM_CANDIDATE,
            "review_class_reasons": ["claim_signal:must"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    claim_planning = compute_planning_summary(claim_entries)
    if claim_planning.get("planning_caveat") == CAVEAT_CLAIM_CANDIDATE_HEAVY:
        print("[PASS] claim-candidate-heavy caveat when P0+P1 dominated by claim_candidate")
    else:
        print(f"[FAIL] claim-candidate-heavy caveat: got {claim_planning.get('planning_caveat')}")
        all_passed = False

    # Fixture PC3: mixed caveat when both types present in P0/P1
    # Need structural entries with calibrated >= 34 for P1 (72 - 30 = 42 for P0, 64 - 30 = 34 for P1)
    mixed_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(20):
        mixed_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "generated_from_table_fragment",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Table row.",
            "reviewed_at": "",
            "reviewer_notes": "Table fragment.",
            "score": 72,  # Base score
            "calibrated_score": 42,  # After -30 calibration: P0
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security", "normative_text"],
            "review_class": REVIEW_CLASS_STRUCTURAL_FRAGMENT,
            "review_class_reasons": ["structural:generated_from_table_fragment"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    for i in range(20, 40):
        mixed_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "The system must handle authentication.",
            "reviewed_at": "",
            "reviewer_notes": "Strong MUST requirement.",
            "score": 42,
            "calibrated_score": 62,  # After +20 calibration: P0
            "risk_reasons": ["generic_ignored_note", "normative_text"],
            "review_class": REVIEW_CLASS_CLAIM_CANDIDATE,
            "review_class_reasons": ["claim_signal:must"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    mixed_planning = compute_planning_summary(mixed_entries)
    if mixed_planning.get("planning_caveat") == CAVEAT_MIXED:
        print("[PASS] mixed caveat when both types present")
    else:
        print(f"[FAIL] mixed caveat: got {mixed_planning.get('planning_caveat')}")
        all_passed = False

    # === Priority band tests ===

    # Fixture 11: score 42 maps to P0
    if get_priority_band(42) == "P0":
        print("[PASS] maps score 42 to P0")
    else:
        print(f"[FAIL] score 42 should map to P0, got {get_priority_band(42)}")
        all_passed = False

    # Fixture 12: score 34 maps to P1
    if get_priority_band(34) == "P1":
        print("[PASS] maps score 34 to P1")
    else:
        print(f"[FAIL] score 34 should map to P1, got {get_priority_band(34)}")
        all_passed = False

    # Fixture 13: score 24 maps to P2
    if get_priority_band(24) == "P2":
        print("[PASS] maps score 24 to P2")
    else:
        print(f"[FAIL] score 24 should map to P2, got {get_priority_band(24)}")
        all_passed = False

    # Fixture 14: score 1 maps to P3
    if get_priority_band(1) == "P3":
        print("[PASS] maps score 1 to P3")
    else:
        print(f"[FAIL] score 1 should map to P3, got {get_priority_band(1)}")
        all_passed = False

    # Fixture 15: score 0 maps to P4
    if get_priority_band(0) == "P4":
        print("[PASS] maps score 0 to P4")
    else:
        print(f"[FAIL] score 0 should map to P4, got {get_priority_band(0)}")
        all_passed = False

    # === JSON/TSV output tests ===

    test_entries: list[dict[str, str | int | list[str]]] = [
        {
            "candidate_id": "DOC-CAND-000000000001",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Test text.",
            "reviewed_at": "2026-06-19",
            "reviewer_notes": "Low-value prose fragment from: docs/foo.md",
            "score": 42,
            "calibrated_score": 62,
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security"],
            "review_class": REVIEW_CLASS_CLAIM_CANDIDATE,
            "review_class_reasons": ["claim_signal:must"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        },
        {
            "candidate_id": "DOC-CAND-000000000002",
            "disposition": "stale",
            "reason_code": "stale_doc",
            "source_doc_path": "docs/old/design.md",
            "candidate_text": "Test text 2.",
            "reviewed_at": "2026-06-19",
            "reviewer_notes": "From stale doc: docs/old/design.md",
            "score": -12,
            "calibrated_score": -42,
            "risk_reasons": ["deprioritized:stale"],
            "review_class": REVIEW_CLASS_STALE_OR_HISTORICAL,
            "review_class_reasons": ["disposition:stale"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": True,
            "is_historical": False,
            "is_stale_doc": True,
            "is_historical_doc": False,
            "is_high_value_doc": False,
        },
    ]
    test_summary = {
        "total_candidates": 2,
        "disposition_counts": {"ignored_by_policy": 1, "stale": 1},
        "reason_code_counts": {"low_value_context": 1, "stale_doc": 1},
        "review_marker_counts": {"act_5_0": 0, "act_5_2": 0, "unreviewed": 2},
        "generic_note_counts": {"ignored_by_policy": 1, "stale": 1},
        "top_docs_by_unreviewed_generic_ignored": [],
        "top_docs_by_risk": [],
    }

    # Fixture 8: deterministic JSON output
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_path = Path(f.name)

    try:
        write_json(test_entries, test_summary, json_path)
        with open(json_path) as f:
            data = json.load(f)

        if (
            data["total_candidates"] == 2
            and "disposition_counts" in data
            and len(data["recommended_candidates"]) == 2
        ):
            print("[PASS] deterministic JSON output")
        else:
            print(f"[FAIL] JSON output structure: {data}")
            all_passed = False

        # Run twice and compare for determinism
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json_path2 = Path(f.name)
        try:
            write_json(test_entries, test_summary, json_path2)
            with open(json_path) as f1:
                data1 = json.load(f1)
            with open(json_path2) as f2:
                data2 = json.load(f2)

            if data1 == data2:
                print("[PASS] JSON output is deterministic")
            else:
                print("[FAIL] JSON output not deterministic")
                all_passed = False
        finally:
            os.unlink(json_path2)
    finally:
        os.unlink(json_path)

    # Fixture 9: TSV output contains expected columns/order
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        tsv_path = Path(f.name)

    try:
        write_tsv(test_entries, tsv_path)
        with open(tsv_path) as f:
            lines = f.readlines()

        expected_header = "score\tpriority_band\treview_class\treview_class_reasons\tcandidate_id\tdisposition\treason_code\tsource_doc_path\trisk_reasons\treviewed_at\treviewer_notes\tcandidate_text\n"
        if lines and lines[0] == expected_header:
            print("[PASS] TSV output contains expected columns/order")
        else:
            print(f"[FAIL] TSV header mismatch: {lines[0] if lines else 'empty'}")
            all_passed = False
    finally:
        os.unlink(tsv_path)

    # Fixture JSON2: recommended candidates include review_class
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_rc_path = Path(f.name)
    try:
        write_json(test_entries, test_summary, json_rc_path)
        with open(json_rc_path) as f:
            data = json.load(f)
        rec = data["recommended_candidates"][0]
        if "review_class" in rec and "review_class_reasons" in rec:
            print("[PASS] JSON recommended candidate includes review_class")
        else:
            print(f"[FAIL] JSON missing review_class: {rec.keys()}")
            all_passed = False
    finally:
        os.unlink(json_rc_path)

    # Fixture planning JSON: planning includes review_class_counts
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_plan_path = Path(f.name)
    try:
        test_planning = compute_planning_summary(test_entries)
        write_json(test_entries, test_summary, json_plan_path, include_planning=True, planning=test_planning)
        with open(json_plan_path) as f:
            data = json.load(f)
        planning = data.get("planning", {})
        if "review_class_counts" in planning and "priority_by_review_class" in planning:
            print("[PASS] planning JSON includes review_class_counts")
        else:
            print(f"[FAIL] planning missing review_class_counts: {planning.keys()}")
            all_passed = False
        if "claim_candidate_high_priority_count" in planning and "cleanup_high_priority_count" in planning:
            print("[PASS] planning JSON includes high-priority counts")
        else:
            print("[FAIL] planning missing high-priority counts")
            all_passed = False
        if "planning_caveat" in planning:
            print("[PASS] planning JSON includes planning_caveat")
        else:
            print("[FAIL] planning missing planning_caveat")
            all_passed = False
    finally:
        os.unlink(json_plan_path)

    # === Planning recommendation tests (using calibrated scores) ===

    # Fixture 16: calibrated P0+P1 >= 100 recommends continue_large_tranche
    large_tranche_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(100):
        large_tranche_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Test text.",
            "reviewed_at": "",
            "reviewer_notes": "Low-value prose fragment",
            "score": 42,
            "calibrated_score": 62,  # Claim candidate boost
            "risk_reasons": ["generic_ignored_note"],
            "review_class": REVIEW_CLASS_CLAIM_CANDIDATE,
            "review_class_reasons": ["claim_signal:must"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    large_planning = compute_planning_summary(large_tranche_entries)
    if large_planning["recommended_next_action"] == ACTION_CONTINUE_LARGE_TRANCHE:
        print("[PASS] calibrated P0+P1 >= 100 recommends continue_large_tranche")
    else:
        print(f"[FAIL] expected continue_large_tranche, got {large_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 17: calibrated P0+P1 between 25 and 99 recommends continue_small_targeted_tranche
    small_tranche_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(50):
        small_tranche_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Test text.",
            "reviewed_at": "",
            "reviewer_notes": "Low-value prose fragment",
            "score": 42,
            "calibrated_score": 62,
            "risk_reasons": ["generic_ignored_note"],
            "review_class": REVIEW_CLASS_CLAIM_CANDIDATE,
            "review_class_reasons": ["claim_signal:must"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        })
    small_planning = compute_planning_summary(small_tranche_entries)
    if small_planning["recommended_next_action"] == ACTION_CONTINUE_SMALL_TARGETED:
        print("[PASS] calibrated P0+P1 between 25 and 99 recommends continue_small_targeted_tranche")
    else:
        print(f"[FAIL] expected continue_small_targeted_tranche, got {small_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 18: calibrated P0+P1 < 25 with no weak/stale-high-value recommends pause_manual_tranches
    pause_entries: list[dict[str, str | int | list[str]]] = []
    for i in range(10):
        pause_entries.append({
            "candidate_id": f"DOC-CAND-{i:012d}",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/old/design.md",
            "candidate_text": "Test text.",
            "reviewed_at": "",
            "reviewer_notes": "Low-value prose fragment",
            "score": 5,
            "calibrated_score": -25,  # After calibration
            "risk_reasons": [],
            "review_class": REVIEW_CLASS_NON_NORMATIVE_PROSE,
            "review_class_reasons": ["non_normative:generic_low_value"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": False,
        })
    pause_planning = compute_planning_summary(pause_entries)
    if pause_planning["recommended_next_action"] == ACTION_PAUSE_MANUAL_TRANCHES:
        print("[PASS] calibrated P0+P1 < 25 recommends pause_manual_tranches")
    else:
        print(f"[FAIL] expected pause_manual_tranches, got {pause_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 20: JSON planning block is deterministic
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_planning_path = Path(f.name)
    try:
        test_planning = compute_planning_summary(small_tranche_entries)
        write_json(small_tranche_entries, test_summary, json_planning_path, include_planning=True, planning=test_planning)
        with open(json_planning_path) as f:
            data1 = json.load(f)
        with open(json_planning_path) as f:
            data2 = json.load(f)
        if data1 == data2 and "planning" in data1:
            print("[PASS] JSON planning block is deterministic")
        else:
            print("[FAIL] JSON planning block not deterministic")
            all_passed = False
    finally:
        os.unlink(json_planning_path)

    print()
    if all_passed:
        print("[PASS] all self-tests passed")
        return True
    else:
        print("[FAIL] some self-tests failed")
        return False

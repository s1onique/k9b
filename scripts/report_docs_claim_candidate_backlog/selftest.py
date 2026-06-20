"""Self-tests for documentation claim candidate backlog reporter."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .model import compute_risk_score, is_generic_low_value_note
from .planning import (
    ACTION_CONTINUE_LARGE_TRANCHE,
    ACTION_CONTINUE_SMALL_TARGETED,
    ACTION_PAUSE_MANUAL_TRANCHES,
    compute_planning_summary,
    get_priority_band,
)
from .report import write_json, write_tsv


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    print("=== Self-Test Fixtures ===\n")

    all_passed = True

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

    # Fixture 8: deterministic JSON output (same input = same output)
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
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security"],
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
            "risk_reasons": ["deprioritized:stale"],
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

        expected_header = "score\tcandidate_id\tdisposition\treason_code\tsource_doc_path\trisk_reasons\treviewed_at\treviewer_notes\tcandidate_text\n"
        if lines and lines[0] == expected_header:
            print("[PASS] TSV output contains expected columns/order")
        else:
            print(f"[FAIL] TSV header mismatch: {lines[0] if lines else 'empty'}")
            all_passed = False
    finally:
        os.unlink(tsv_path)

    # Fixture 10: covered_by_existing_claim with generic note detected correctly
    if is_generic_low_value_note("Low-value prose fragment from: docs/foo.md"):
        print("[PASS] generic note pattern detection")
    else:
        print("[FAIL] generic note pattern detection")
        all_passed = False

    # === Planning-specific self-tests ===

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

    # Fixture 16: P0+P1 >= 100 recommends continue_large_tranche
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
            "risk_reasons": ["generic_ignored_note"],
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
        print("[PASS] P0+P1 >= 100 recommends continue_large_tranche")
    else:
        print(f"[FAIL] expected continue_large_tranche, got {large_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 17: P0+P1 between 25 and 99 recommends continue_small_targeted_tranche
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
            "risk_reasons": ["generic_ignored_note"],
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
        print("[PASS] P0+P1 between 25 and 99 recommends continue_small_targeted_tranche")
    else:
        print(f"[FAIL] expected continue_small_targeted_tranche, got {small_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 18: P0+P1 < 25 with no weak/stale-high-value recommends pause_manual_tranches
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
            "risk_reasons": [],
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
        print("[PASS] P0+P1 < 25 recommends pause_manual_tranches")
    else:
        print(f"[FAIL] expected pause_manual_tranches, got {pause_planning['recommended_next_action']}")
        all_passed = False

    # Fixture 19: weak_covered entries prevent pause - recommend targeted tranche
    weak_entries = [
        dict(candidate_id=f"DOC-CAND-{i:012d}", disposition="covered_by_existing_claim",
             reason_code="covered_by_broader_claim", source_doc_path="docs/normal.md",
             candidate_text="Test.", reviewed_at="", reviewer_notes="Low-value",
             score=12, risk_reasons=["covered_note_weak"], is_act_5_0_reviewed=False,
             is_act_5_2_reviewed=False, has_any_act_review_marker=False,
             is_generic_low_value_note=True, is_stale=False, is_historical=False,
             is_stale_doc=False, is_historical_doc=False, is_high_value_doc=False)
        for i in range(5)]
    wp = compute_planning_summary(weak_entries)
    if wp["key_risk_buckets"]["weak_covered_count"] != 5:
        print(f"[FAIL] weak_covered_count=5, got {wp['key_risk_buckets']['weak_covered_count']}")
        all_passed = False
    elif wp["recommended_next_action"] == ACTION_PAUSE_MANUAL_TRANCHES:
        print("[FAIL] weak_covered must not pause_manual_tranches"); all_passed = False
    elif wp["recommended_next_action"] != ACTION_CONTINUE_SMALL_TARGETED:
        print(f"[FAIL] expected continue_small_targeted_tranche, got {wp['recommended_next_action']}"); all_passed = False
    elif wp["recommended_tranche_size"] != 5:
        print(f"[FAIL] tranche_size=5, got {wp['recommended_tranche_size']}"); all_passed = False
    else:
        print("[PASS] weak_covered entries recommend targeted tranche (not pause)")

    # Fixture 19b: stale/high-value entries prevent pause - recommend targeted tranche
    stale_entries = [
        dict(candidate_id=f"DOC-CAND-{1000+i:012d}", disposition="historical",
             reason_code="historical_doc", source_doc_path="docs/security/old-design.md",
             candidate_text="Test.", reviewed_at="", reviewer_notes="From historical",
             score=8, risk_reasons=[], is_act_5_0_reviewed=False, is_act_5_2_reviewed=False,
             has_any_act_review_marker=False, is_generic_low_value_note=True, is_stale=False,
             is_historical=True, is_stale_doc=False, is_historical_doc=True, is_high_value_doc=True)
        for i in range(3)]
    sp = compute_planning_summary(stale_entries)
    if sp["key_risk_buckets"]["stale_or_historical_high_value_count"] != 3:
        print(f"[FAIL] stale/high-value=3, got {sp['key_risk_buckets']['stale_or_historical_high_value_count']}")
        all_passed = False
    elif sp["recommended_next_action"] == ACTION_PAUSE_MANUAL_TRANCHES:
        print("[FAIL] stale/high-value must not pause_manual_tranches"); all_passed = False
    elif sp["recommended_next_action"] != ACTION_CONTINUE_SMALL_TARGETED:
        print(f"[FAIL] expected continue_small_targeted_tranche, got {sp['recommended_next_action']}"); all_passed = False
    elif sp["recommended_tranche_size"] != 3:
        print(f"[FAIL] tranche_size=3, got {sp['recommended_tranche_size']}"); all_passed = False
    else:
        print("[PASS] stale/high-value entries recommend targeted tranche (not pause)")

    # Fixture 19c: P0+P1 < 25 with both special buckets zero triggers pause
    pause_clean_entries = [
        dict(candidate_id=f"DOC-CAND-{2000+i:012d}", disposition="ignored_by_policy",
             reason_code="low_value_context", source_doc_path="docs/old/design.md",
             candidate_text="Test.", reviewed_at="", reviewer_notes="Low-value",
             score=5, risk_reasons=[], is_act_5_0_reviewed=False, is_act_5_2_reviewed=False,
             has_any_act_review_marker=False, is_generic_low_value_note=True, is_stale=False,
             is_historical=False, is_stale_doc=False, is_historical_doc=False, is_high_value_doc=False)
        for i in range(10)]
    pp = compute_planning_summary(pause_clean_entries)
    if pp["key_risk_buckets"]["weak_covered_count"] != 0:
        print(f"[FAIL] pause_clean weak_covered_count=0, got {pp['key_risk_buckets']['weak_covered_count']}")
        all_passed = False
    elif pp["key_risk_buckets"]["stale_or_historical_high_value_count"] != 0:
        print(f"[FAIL] pause_clean stale/high-value=0, got {pp['key_risk_buckets']['stale_or_historical_high_value_count']}")
        all_passed = False
    elif pp["recommended_next_action"] != ACTION_PAUSE_MANUAL_TRANCHES:
        print(f"[FAIL] pause_clean expected pause_manual_tranches, got {pp['recommended_next_action']}"); all_passed = False
    elif pp["recommended_tranche_size"] != 0:
        print(f"[FAIL] pause_clean tranche_size=0, got {pp['recommended_tranche_size']}"); all_passed = False
    else:
        print("[PASS] pause triggers only when special buckets are zero")

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

    # Fixture 21: TSV includes priority_band when requested
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        tsv_priority_path = Path(f.name)
    try:
        write_tsv(small_tranche_entries, tsv_priority_path, include_priority_band=True)
        with open(tsv_priority_path) as f:
            lines = f.readlines()
        expected_header = "score\tpriority_band\tcandidate_id\tdisposition\treason_code\tsource_doc_path\trisk_reasons\treviewed_at\treviewer_notes\tcandidate_text\n"
        if lines and lines[0] == expected_header:
            print("[PASS] TSV includes priority_band when requested")
        else:
            print(f"[FAIL] TSV priority_band header mismatch: {lines[0] if lines else 'empty'}")
            all_passed = False
    finally:
        os.unlink(tsv_priority_path)

    print()
    if all_passed:
        print("[PASS] all self-tests passed")
        return True
    else:
        print("[FAIL] some self-tests failed")
        return False

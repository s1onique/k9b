"""Self-tests for documentation claim candidate backlog reporter."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .model import compute_risk_score, is_generic_low_value_note
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

    print()
    if all_passed:
        print("[PASS] all self-tests passed")
        return True
    else:
        print("[FAIL] some self-tests failed")
        return False
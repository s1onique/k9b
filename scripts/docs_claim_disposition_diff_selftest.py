"""Self-test fixtures for disposition semantic diff reporter.

Responsibilities:
- Define test fixtures covering all diff scenarios
- Parse fixture CSV content
- Run all self-tests and report results
"""
from __future__ import annotations

import json

from docs_claim_disposition_diff_loader import _parse_shard_content
from docs_claim_disposition_diff_model import compute_diff
from docs_claim_disposition_diff_report import format_json_output

# ---------------------------------------------------------------------------
# Self-test fixtures
# ---------------------------------------------------------------------------

FIXTURES: list[tuple[str, str, str, bool, bool, bool]] = [
    # (name, base_csv, target_csv, expect_pass, expect_changed, expect_changed_fields)
    (
        "identical inputs",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        True,  # expect_pass (no added/removed)
        False,  # expect_changed
        False,  # expect_field_changes
    ),
    (
        "reviewer_notes-only change",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,original note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,improved note after review\n"
        ),
        True,  # expect_pass (no added/removed)
        True,  # expect_changed
        True,  # expect_field_changes (reviewer_notes only)
    ),
    (
        "disposition change",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,stale,,,obsolete_doc,2026-06-19,note\n"
        ),
        False,  # expect_pass (disposition counts changed)
        True,  # expect_changed
        True,  # expect_field_changes (disposition, reason_code)
    ),
    (
        "added candidate ID",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,new note\n"
        ),
        False,  # expect_pass (added candidate -> row set change)
        False,  # expect_changed (added IDs tracked separately, not in changed_rows)
        False,  # no field changes, only added row
    ),
    (
        "removed candidate ID",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
        ),
        False,  # expect_pass (removed candidate -> row set change)
        False,  # expect_changed (removed IDs tracked separately, not in changed_rows)
        False,  # no field changes, only removed row
    ),
    (
        "duplicate candidate ID in base",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
        ),
        False,  # expect_pass (duplicate causes parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "invalid candidate ID in target",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-INVALID,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        False,  # expect_pass (parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "malformed/missing header in base",
        "",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        False,  # expect_pass (parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "ACT 5.0-like: broad reserialization with reviewer_notes changes only",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-49a09e000a77,ignored_by_policy,,,low_value_context,2026-06-19,Low-value prose fragment from: docs/data-model/incidents.md\n"
            "DOC-CAND-49a09e000a78,ignored_by_policy,,,low_value_context,2026-06-19,Another prose fragment\n"
            "DOC-CAND-49a09e000a79,stale,,,obsolete_doc,2026-06-19,Old stale note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            'DOC-CAND-49a09e000a77,ignored_by_policy,,,low_value_context,2026-06-19,"Low-value prose fragment from docs/data-model/incidents.md: schema table header label, formatting artifact not a claim (ACT 5.0 review)."\n'
            'DOC-CAND-49a09e000a78,ignored_by_policy,,,low_value_context,2026-06-19,"Another prose fragment updated (ACT 5.0 review)."\n'
            "DOC-CAND-49a09e000a79,stale,,,obsolete_doc,2026-06-19,Old stale note\n"
        ),
        True,  # expect_pass (no added/removed, no disposition changes)
        True,  # expect_changed
        True,  # expect_field_changes (reviewer_notes only)
    ),
]


def _parse_fixture_csv(content: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse fixture CSV content."""
    if not content.strip():
        return [], ["empty CSV"]
    errors, rows = _parse_shard_content("(fixture)", content)
    return rows, errors


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    all_passed = True

    for name, base_csv, target_csv, expect_pass, expect_changed, expect_field_changes in FIXTURES:
        base_rows, base_errors = _parse_fixture_csv(base_csv)
        target_rows, target_errors = _parse_fixture_csv(target_csv)

        # Check for parse errors
        if base_errors or target_errors:
            if expect_pass:
                print(
                    f"[FAIL] {name}: unexpected parse errors - base: {base_errors}, "
                    f"target: {target_errors}"
                )
                all_passed = False
            else:
                print(f"[PASS] {name}: correctly rejected (parse error)")
            continue

        # Check duplicates
        base_ids = [r["candidate_id"] for r in base_rows]
        target_ids = [r["candidate_id"] for r in target_rows]
        if len(base_ids) != len(set(base_ids)):
            print(f"[FAIL] {name}: base has duplicate candidate IDs")
            all_passed = False
            continue
        if len(target_ids) != len(set(target_ids)):
            print(f"[FAIL] {name}: target has duplicate candidate IDs")
            all_passed = False
            continue

        # Compute diff
        diff_result = compute_diff(base_rows, target_rows)

        # Determine actual pass/fail
        # Pass means: no added/removed candidates AND (no field changes OR disposition counts unchanged)
        actual_pass = not diff_result["candidate_id_set_changed"]
        if actual_pass and diff_result["disposition_counts_changed"]:
            # Changed disposition counts fail by default
            actual_pass = False

        if actual_pass != expect_pass:
            print(f"[FAIL] {name}: pass={actual_pass}, expected pass={expect_pass}")
            all_passed = False
            continue

        if expect_changed:
            if diff_result["changed_candidate_count"] == 0:
                print(f"[FAIL] {name}: expected changes but got none")
                all_passed = False
                continue

        if expect_field_changes:
            if not diff_result["changed_field_counts"]:
                print(f"[FAIL] {name}: expected field changes but got none")
                all_passed = False
                continue

        # Verify JSON output is deterministic
        json_output = format_json_output(diff_result, "base", "target")
        try:
            parsed = json.loads(json_output)
            if not isinstance(parsed, dict):
                print(f"[FAIL] {name}: JSON output not a dict")
                all_passed = False
                continue
            # Re-serialize to check determinism
            re_serialized = json.dumps(parsed, indent=2, sort_keys=True)
            if json_output != re_serialized:
                print(f"[FAIL] {name}: JSON output not deterministic")
                all_passed = False
                continue
        except json.JSONDecodeError as exc:
            print(f"[FAIL] {name}: JSON output invalid: {exc}")
            all_passed = False
            continue

        print(f"[PASS] {name}")

    return all_passed

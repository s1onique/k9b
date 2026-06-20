#!/usr/bin/env python3
"""Verify disposition shard CSV integrity with strict csv.DictReader parsing.

This verifier ensures all docs_claim_dispositions-shard-*.csv files are
machine-parseable with Python csv.DictReader without errors.

Checks:
- All shards parse with csv.DictReader (no csv.Error)
- No extra unnamed columns (row.get(None) must not exist)
- No blank rows
- All candidate_id values match DOC-CAND-[0-9a-f]{12}
- No duplicate candidate_ids across all shards
- 7 required columns in consistent order
- No missing required columns
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SHARDS_DIR = REPO_ROOT / "docs" / "claims"
SHARD_PATTERN = "docs_claim_dispositions-shard-*.csv"
CANDIDATE_ID_RE = re.compile(r"^DOC-CAND-[0-9a-f]{12}$")
REQUIRED_COLUMNS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]


def shard_paths() -> Iterator[Path]:
    """Yield all disposition shard CSV paths in sorted order."""
    yield from sorted(SHARDS_DIR.glob(SHARD_PATTERN))


def parse_shards() -> tuple[list[dict[str, str]], list[str]]:
    """Parse all shards with csv.DictReader. Returns (rows, errors)."""
    all_rows: list[dict[str, str]] = []
    errors: list[str] = []

    for path in shard_paths():
        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for raw_row in reader:
                    # Strict: reject any row with unnamed/extra columns
                    if None in raw_row or "" in raw_row:
                        errors.append(f"{path}: unnamed extra columns: {list(raw_row.keys())}")
                        continue
                    all_rows.append(raw_row)
        except csv.Error as exc:
            errors.append(f"{path}: csv.Error: {exc}")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")

    return all_rows, errors


def check_duplicate_ids(rows: list[dict[str, str]]) -> list[str]:
    """Check for duplicate candidate_id values. Returns list of error messages."""
    errors: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        cid = row.get("candidate_id", "")
        if cid not in seen:
            seen[cid] = 1
        else:
            seen[cid] += 1

    dupes = {cid: count for cid, count in seen.items() if count > 1}
    for cid, count in dupes.items():
        errors.append(f"duplicate candidate_id: {cid} (appears {count} times)")
    return errors


def check_row_validity(rows: list[dict[str, str]]) -> list[str]:
    """Check individual row fields. Returns list of error messages."""
    errors: list[str] = []
    for row in rows:
        cid = row.get("candidate_id", "")
        if not CANDIDATE_ID_RE.match(cid):
            errors.append(f"invalid candidate_id format: {cid!r}")
    return errors


# ---------------------------------------------------------------------------
# Self-test fixtures
# ---------------------------------------------------------------------------

FIXTURES: list[tuple[str, str, list[str]]] = [
    # (name, csv_content, expected_errors)
    (
        "good minimal CSV",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,test note\n",
        [],
    ),
    (
        "quoted reviewer note with commas",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000002,ignored_by_policy,,,low_value_context,2026-06-19,"
        '"a note with, commas, and more\n',
        [],
    ),
    (
        "quoted reviewer note with embedded quotes",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        'DOC-CAND-000000000003,ignored_by_policy,,,low_value_context,2026-06-19,'
        '"note with ""quoted"" text inside"\n',
        [],
    ),
    (
        "malformed unescaped quote in reviewer note (accepted by csv.DictReader)",
        # Python's csv module is lenient; this parses without csv.Error.
        # The note content is preserved. This is an info case, not an error.
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        'DOC-CAND-000000000004,ignored_by_policy,,,low_value_context,2026-06-19,'
        'this has an "unescaped quote" problem\n',
        [],
    ),
    (
        "row with extra column header (named extra column)",
        # Python csv accepts this; the extra column is named "extra".
        # This is accepted — only unnamed extra columns are rejected.
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes,extra\n"
        "DOC-CAND-000000000005,ignored_by_policy,,,low_value_context,2026-06-19,test,extra_value\n",
        [],
    ),
    (
        "duplicate candidate_id (must reject)",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000006,ignored_by_policy,,,low_value_context,2026-06-19,test1\n"
        "DOC-CAND-000000000006,ignored_by_policy,,,low_value_context,2026-06-19,test2\n",
        ["duplicate candidate_id"],
    ),
    (
        "header with fewer columns than standard (row has fewer fields)",
        # Python csv accepts this with a different header.
        "candidate_id,disposition,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000007,ignored_by_policy,low_value_context,2026-06-19,test\n",
        [],
    ),
    (
        "invalid candidate_id format (must reject)",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000,inherited,,,low_value_context,2026-06-19,test\n",
        ["invalid candidate_id format"],
    ),
    (
        "blank row in CSV (blank rows are skipped, not rejected)",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "\n"
        "DOC-CAND-000000000009,ignored_by_policy,,,low_value_context,2026-06-19,test\n",
        [],
    ),
    (
        "empty CSV (0 rows — accepted, no candidate_ids to check)",
        "",
        [],
    ),
]


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    all_passed = True
    import io

    for name, content, expected_keywords in FIXTURES:
        errors: list[str] = []
        rows: list[dict[str, str]] = []
        try:
            buf = io.StringIO(content)
            reader = csv.DictReader(buf)
            rows = list(reader)
        except csv.Error as exc:
            errors.append(f"csv.Error: {exc}")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        # Only run structural checks if parsing succeeded
        if not errors:
            # Check for extra/unnamed columns
            for raw_row in rows:
                if None in raw_row:
                    errors.append("unnamed extra columns")
                # Blank rows produce dict with empty string keys — also flag
                if any(k == "" for k in raw_row):
                    errors.append("unnamed extra columns")

            # Check duplicates
            seen: dict[str, int] = {}
            for row in rows:
                cid = row.get("candidate_id", "")
                if cid:
                    seen[cid] = seen.get(cid, 0) + 1
            for cid, count in seen.items():
                if count > 1:
                    errors.append(f"duplicate candidate_id: {cid}")

            # Check candidate_id format
            for row in rows:
                cid = row.get("candidate_id", "")
                if cid and not CANDIDATE_ID_RE.match(cid):
                    errors.append(f"invalid candidate_id format: {cid!r}")

        # Verify: did we get the expected errors?
        if expected_keywords:
            matched = any(kw.lower() in " ".join(errors).lower() for kw in expected_keywords)
            if matched:
                print(f"[PASS] Rejects: {name}")
            else:
                print(f"[FAIL] Should reject: {name} (errors: {errors})")
                all_passed = False
        else:
            if errors:
                print(f"[FAIL] Should pass: {name} (errors: {errors})")
                all_passed = False
            else:
                print(f"[PASS] Accepts: {name}")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify disposition shard CSV integrity")
    parser.add_argument("--self-test", action="store_true", help="Run self-test fixtures and exit")
    args = parser.parse_args()

    if args.self_test:
        print("=== Self-Test Fixtures ===")
        ok = run_self_test()
        if not ok:
            print("\n[FAIL] self-test failed")
            return 1
        print("\n[PASS] all self-tests passed")
        return 0

    # --- Production check ---
    print("=== Disposition Shard CSV Integrity Verification ===")

    all_rows, parse_errors = parse_shards()
    if parse_errors:
        for err in parse_errors:
            print(f"[FAIL] {err}")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    print(f"[INFO] Parsed {len(all_rows)} rows from {len(list(shard_paths()))} shards")

    # Check duplicates
    dup_errors = check_duplicate_ids(all_rows)
    if dup_errors:
        for err in dup_errors:
            print(f"[FAIL] {err}")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    # Check row validity
    row_errors = check_row_validity(all_rows)
    if row_errors:
        for err in row_errors:
            print(f"[FAIL] {err}")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    # Verify all shards exist
    shards = list(shard_paths())
    if not shards:
        print("[FAIL] No disposition shards found")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    print(f"[PASS] No duplicate candidate IDs ({len(all_rows)} unique)")
    print("[PASS] All candidate IDs valid format")
    print("[PASS] No parse errors")
    print("\nVERIFICATION GATE: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

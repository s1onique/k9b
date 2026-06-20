#!/usr/bin/env python3
"""Verify disposition shard CSV integrity with strict header and row validation.

This verifier ensures all docs_claim_dispositions-shard-*.csv files conform
to an exact contract for machine-parseability and data integrity.

Strict contract:
- File must exist and not be empty
- Header must exactly equal the 7 required columns in order
- No extra named columns
- No missing columns
- No shorter-than-standard headers
- No physical blank rows (detected by raw line scan before csv.DictReader)
- No rows with fewer fields than header
- Every row must have exactly the 7 required keys in correct order
- candidate_id must match DOC-CAND-[0-9a-f]{12}
- candidate_id must be non-empty and unique across all shards
- disposition must be non-empty
- No header-only (zero data row) shards

Limitations:
- Physical blank rows are detected with a raw line scan before csv.DictReader.
- Python csv.DictReader remains lenient with some malformed quote patterns;
  this verifier catches structural CSV defects but does not claim to reject
  every quote style accepted by csv.DictReader.
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


def check_physical_blank_lines(path: Path, content: str) -> list[str]:
    """Detect physical blank rows by raw line scan before csv.DictReader.

    Uses splitlines() so a normal trailing newline does not produce a
    phantom empty line. Whitespace-only lines are also rejected.

    Returns a list of error messages, one per blank line found.
    """
    errors: list[str] = []
    for line_num, line in enumerate(content.splitlines(), start=1):
        if line.strip() == "":
            errors.append(f"{path}:{line_num}: physical blank line")
    return errors


def parse_shards_strict() -> tuple[list[dict[str, str]], list[str]]:
    """Parse all shards with strict header and row validation.

    Returns (rows, errors).
    Strict enforcement:
    - Header must exactly match REQUIRED_COLUMNS
    - No blank rows (physical or all-empty)
    - No rows with extra/missing columns
    - Every row must have exactly REQUIRED_COLUMNS keys in order
    """
    all_rows: list[dict[str, str]] = []
    errors: list[str] = []

    for path in shard_paths():
        shard_errors: list[str] = []
        data_rows: list[dict[str, str]] = []

        try:
            with path.open(newline="", encoding="utf-8") as f:
                content = f.read()

            # Reject empty files
            if not content.strip():
                errors.append(f"{path}: empty file")
                continue

            # Reject physical blank rows (raw line scan before csv.DictReader)
            blank_errors = check_physical_blank_lines(path, content)
            if blank_errors:
                errors.extend(blank_errors)
                continue

            buf = io.StringIO(content)
            reader = csv.DictReader(buf)

            # Enforce exact header
            if reader.fieldnames is None:
                errors.append(f"{path}: no header row")
                continue

            if list(reader.fieldnames) != REQUIRED_COLUMNS:
                actual = reader.fieldnames
                # Check for extra columns
                if len(actual) > len(REQUIRED_COLUMNS):
                    extra = [c for c in actual if c not in REQUIRED_COLUMNS]
                    errors.append(f"{path}: extra named columns: {extra}")
                    continue
                # Check for missing columns
                if len(actual) < len(REQUIRED_COLUMNS):
                    missing = [c for c in REQUIRED_COLUMNS if c not in actual]
                    errors.append(f"{path}: missing required columns: {missing}")
                    continue
                # Header has same length but different columns
                errors.append(f"{path}: header mismatch, expected {REQUIRED_COLUMNS}, got {actual}")
                continue

            line_num = 1  # Header is line 1
            for raw_row in reader:
                line_num += 1

                # Reject rows with None values (indicates missing column in data)
                if None in raw_row.values():
                    shard_errors.append(f"{path}:{line_num}: row has fewer fields than header")
                    continue

                # Reject blank rows (all fields empty)
                if all(v == "" for v in raw_row.values()):
                    shard_errors.append(f"{path}:{line_num}: blank row (all fields empty)")
                    continue

                # Reject rows with wrong number of columns
                if list(raw_row.keys()) != REQUIRED_COLUMNS:
                    actual_keys = list(raw_row.keys())
                    shard_errors.append(
                        f"{path}:{line_num}: row shape mismatch, expected {REQUIRED_COLUMNS}, got {actual_keys}"
                    )
                    continue

                data_rows.append(raw_row)

            # Reject shards with zero data rows
            if not data_rows and not shard_errors:
                shard_errors.append(f"{path}: header-only CSV (0 data rows)")

        except csv.Error as exc:
            errors.append(f"{path}: csv.Error: {exc}")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")

        # Accumulate shard errors
        errors.extend(shard_errors)
        all_rows.extend(data_rows)

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
        if not cid:
            errors.append("empty candidate_id")
            continue
        if not CANDIDATE_ID_RE.match(cid):
            errors.append(f"invalid candidate_id format: {cid!r}")

        disposition = row.get("disposition", "")
        if not disposition:
            errors.append(f"{cid}: empty disposition")
    return errors


# ---------------------------------------------------------------------------
# Self-test fixtures
# ---------------------------------------------------------------------------

import io

FIXTURES: list[tuple[str, str, bool]] = [
    # (name, csv_content, should_pass)
    # --- Cases that should PASS ---
    (
        "good minimal CSV",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,test note\n",
        True,
    ),
    (
        "quoted reviewer note with commas",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000002,ignored_by_policy,,,low_value_context,2026-06-19,"
        '"a note with, commas, and more\n',
        True,
    ),
    (
        "quoted reviewer note with embedded quotes",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        'DOC-CAND-000000000003,ignored_by_policy,,,low_value_context,2026-06-19,'
        '"note with ""quoted"" text inside"\n',
        True,
    ),
    # --- Cases that should FAIL ---
    (
        "extra named column in header",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes,extra\n"
        "DOC-CAND-000000000004,ignored_by_policy,,,low_value_context,2026-06-19,test,extra_value\n",
        False,
    ),
    (
        "shorter-than-standard header",
        "candidate_id,disposition,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000005,ignored_by_policy,low_value_context,2026-06-19,test\n",
        False,
    ),
    (
        "missing required column",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at\n"
        "DOC-CAND-000000000006,ignored_by_policy,,,,2026-06-19\n",
        False,
    ),
    (
        "row with fewer columns than header",
        # Data row has fewer fields than header - missing field causes extra unnamed column
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000007,ignored_by_policy,,\n",
        False,
    ),
    (
        "duplicate candidate_id",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000008,ignored_by_policy,,,low_value_context,2026-06-19,test1\n"
        "DOC-CAND-000000000008,ignored_by_policy,,,low_value_context,2026-06-19,test2\n",
        False,
    ),
    (
        "invalid candidate_id format",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000,inherited,,,low_value_context,2026-06-19,test\n",
        False,
    ),
    (
        "empty CSV",
        "",
        False,
    ),
    (
        "header-only CSV with zero data rows",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n",
        False,
    ),
    # --- Physical blank-line rejection cases ---
    (
        "physical blank line after header",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "\n"
        "DOC-CAND-000000000009,ignored_by_policy,,,low_value_context,2026-06-19,test\n",
        False,
    ),
    (
        "physical blank line between data rows",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000010,ignored_by_policy,,,low_value_context,2026-06-19,test1\n"
        "\n"
        "DOC-CAND-000000000011,ignored_by_policy,,,low_value_context,2026-06-19,test2\n",
        False,
    ),
    (
        "whitespace-only physical blank line",
        "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
        "DOC-CAND-000000000012,ignored_by_policy,,,low_value_context,2026-06-19,test\n"
        "   \n"
        "DOC-CAND-000000000013,ignored_by_policy,,,low_value_context,2026-06-19,test2\n",
        False,
    ),
]


# Stand-in path used only for physical blank-line reporting in self-test fixtures.
_FIXTURE_PATH = Path("(fixture)")


def _validate_fixture_content(content: str) -> tuple[list[dict[str, str]], list[str]]:
    """Validate fixture content using strict parsing logic.

    Returns (rows, errors) matching parse_shards_strict behavior.
    """
    errors: list[str] = []
    data_rows: list[dict[str, str]] = []

    if not content.strip():
        errors.append("empty CSV")
        return [], errors

    # Reject physical blank rows (raw line scan before csv.DictReader)
    blank_errors = check_physical_blank_lines(_FIXTURE_PATH, content)
    if blank_errors:
        errors.extend(blank_errors)
        return [], errors

    try:
        buf = io.StringIO(content)
        reader = csv.DictReader(buf)

        # Check header
        if reader.fieldnames is None:
            errors.append("no header row")
            return [], errors

        if list(reader.fieldnames) != REQUIRED_COLUMNS:
            actual = list(reader.fieldnames)
            if len(actual) > len(REQUIRED_COLUMNS):
                extra = [c for c in actual if c not in REQUIRED_COLUMNS]
                errors.append(f"extra named columns: {extra}")
            elif len(actual) < len(REQUIRED_COLUMNS):
                missing = [c for c in REQUIRED_COLUMNS if c not in actual]
                errors.append(f"missing columns: {missing}")
            else:
                errors.append(f"header mismatch: got {actual}")
            return [], errors

        # Check rows
        for line_num, raw_row in enumerate(reader, start=2):
            if None in raw_row.values():
                errors.append(f"line {line_num}: row has fewer fields than header")
            elif all(v == "" for v in raw_row.values()):
                errors.append(f"line {line_num}: blank row")
            elif list(raw_row.keys()) != REQUIRED_COLUMNS:
                errors.append(f"line {line_num}: row shape mismatch")
            else:
                data_rows.append(raw_row)

        # Check for zero data rows
        if not data_rows and not errors:
            errors.append("header-only CSV (0 data rows)")

    except csv.Error as exc:
        errors.append(f"csv.Error: {exc}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    return data_rows, errors


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    all_passed = True

    for name, content, should_pass in FIXTURES:
        rows, errors = _validate_fixture_content(content)

        # Apply additional checks that run on parsed rows
        if not errors:
            errors.extend(check_duplicate_ids(rows))
            errors.extend(check_row_validity(rows))

        # Determine outcome
        had_errors = bool(errors)

        if should_pass:
            if had_errors:
                print(f"[FAIL] Should accept: {name} (errors: {errors})")
                all_passed = False
            else:
                print(f"[PASS] Accepts: {name}")
        else:
            if had_errors:
                print(f"[PASS] Rejects: {name}")
            else:
                print(f"[FAIL] Should reject: {name}")
                all_passed = False

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

    shards = list(shard_paths())
    if not shards:
        print("[FAIL] No disposition shards found")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    all_rows, parse_errors = parse_shards_strict()
    if parse_errors:
        for err in parse_errors:
            print(f"[FAIL] {err}")
        print("\nVERIFICATION GATE: FAILED")
        return 1

    print(f"[INFO] Parsed {len(all_rows)} rows from {len(shards)} shards")

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

    print(f"[PASS] No duplicate candidate IDs ({len(all_rows)} unique)")
    print("[PASS] All candidate IDs valid format")
    print("[PASS] No parse errors")
    print("\nVERIFICATION GATE: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
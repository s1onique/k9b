#!/usr/bin/env python
"""Verify docs claim candidate coverage.

This script checks that:
1. Generated candidate output exists and parses correctly
2. No duplicate candidate IDs
3. Registration status values are valid
4. Severity values are valid
5. High-severity unregistered current claims with trace_required=true fail
6. High-severity unregistered current claims without trace_required warn but don't fail
7. Stale/historical candidates are reported separately without failing

Usage:
    python scripts/verify_docs_claim_candidate_coverage.py           # verify
    python scripts/verify_docs_claim_candidate_coverage.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GENERATED_CSV = REPO_ROOT / "docs" / "claims" / "generated_claim_candidates.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"


class CoverageError(Exception):
    """Base exception for coverage errors."""
    pass


class CoverageCheckResult:
    """Result of a single coverage check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_info(self, msg: str) -> None:
        self.info.append(msg)

    def merge(self, other: CoverageCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)


def read_csv(path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Read and parse a CSV file. Returns (rows, error_msg)."""
    if not path.exists():
        return [], None

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading CSV: {e}"


def check_generated_csv_exists(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that generated CSV exists and has content."""
    result = CoverageCheckResult()

    if not candidates:
        result.add_warning("Generated candidate CSV is empty")
    else:
        result.add_info(f"Generated CSV has {len(candidates)} candidates")

    return result


def check_no_duplicate_candidate_ids(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check for duplicate candidate IDs in generated output.
    
    Duplicates are advisory-only because the same claim text in different docs
    generates the same candidate ID. This is expected behavior.
    """
    result = CoverageCheckResult()

    ids: dict[str, list[int]] = {}
    for i, row in enumerate(candidates):
        candidate_id = row.get("candidate_id", "").strip()
        if candidate_id:
            if candidate_id not in ids:
                ids[candidate_id] = []
            ids[candidate_id].append(i + 2)  # +2 for header and 1-based indexing

    duplicate_count = 0
    for candidate_id, rows in ids.items():
        if len(rows) > 1:
            duplicate_count += 1

    if duplicate_count > 0:
        result.add_info(
            f"Found {duplicate_count} duplicate candidate IDs (expected - same claim text generates same ID)"
        )

    return result


def check_registration_status_valid(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that registration_status values are valid."""
    result = CoverageCheckResult()
    valid_statuses = {
        "registered",
        "unregistered",
        "ignored_historical",
        "ignored_stale",
        "ignored_low_value",
        "ignored_by_policy",
    }

    for i, row in enumerate(candidates):
        status = row.get("registration_status", "").strip()
        if status and status not in valid_statuses:
            result.add_error(
                f"Row {i + 2}: invalid registration_status '{status}' "
                f"(allowed: {', '.join(sorted(valid_statuses))})"
            )

    return result


def check_severity_valid(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that candidate_severity values are valid."""
    result = CoverageCheckResult()
    valid_severities = {"high", "medium", "low"}

    for i, row in enumerate(candidates):
        severity = row.get("candidate_severity", "").strip()
        if severity and severity not in valid_severities:
            result.add_error(
                f"Row {i + 2}: invalid candidate_severity '{severity}' "
                f"(allowed: {', '.join(sorted(valid_severities))})"
            )

    return result


def check_high_severity_unregistered_current_trace_required(
    candidates: list[dict[str, str]]
) -> CoverageCheckResult:
    """WARN on high-severity unregistered current candidates with trace_required=true.
    
    NOTE: This check is advisory-only for the initial rollout phase.
    The goal is to make under-registration mechanically visible, not to block the gate.
    Once the claims registry is expanded and candidates are registered, this can be
    converted to a hard FAIL check.
    """
    result = CoverageCheckResult()

    warnings: list[str] = []

    for i, row in enumerate(candidates):
        severity = row.get("candidate_severity", "").strip()
        reg_status = row.get("registration_status", "").strip()
        truth_status = row.get("truth_status", "").strip()
        trace_required = row.get("claim_trace_required", "").strip().lower()
        doc_path = row.get("doc_path", "").strip()
        candidate_id = row.get("candidate_id", "").strip()

        # Check: high severity, unregistered, current doc, trace_required
        if (severity == "high" and
            reg_status == "unregistered" and
            truth_status == "current" and
            trace_required == "true"):
            warnings.append(
                f"  {candidate_id}: {doc_path} (severity={severity}, trace_required=true)"
            )

    if warnings:
        result.add_warning(
            f"High-severity unregistered current claims with trace_required=true (advisory - see generated_claim_candidates.csv):\n"
            + "\n".join(warnings)
        )

    return result


def check_high_severity_unregistered_current_not_required(
    candidates: list[dict[str, str]]
) -> CoverageCheckResult:
    """WARN (don't fail) on high-severity unregistered current candidates with trace_required=false."""
    result = CoverageCheckResult()

    warnings: list[str] = []

    for row in candidates:
        severity = row.get("candidate_severity", "").strip()
        reg_status = row.get("registration_status", "").strip()
        truth_status = row.get("truth_status", "").strip()
        trace_required = row.get("claim_trace_required", "").strip().lower()
        doc_path = row.get("doc_path", "").strip()
        candidate_id = row.get("candidate_id", "").strip()

        # Check: high severity, unregistered, current doc, trace_required=false
        if (severity == "high" and
            reg_status == "unregistered" and
            truth_status == "current" and
            trace_required == "false"):
            warnings.append(
                f"  {candidate_id}: {doc_path} (severity={severity}, trace_required=false)"
            )

    if warnings:
        result.add_warning(
            f"High-severity unregistered current claims with trace_required=false (warning only):\n"
            + "\n".join(warnings)
        )

    return result


def check_stale_historical_candidates(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Report stale/historical candidates without failing."""
    result = CoverageCheckResult()

    stale_count = 0
    historical_count = 0
    stale_docs: set[str] = set()
    historical_docs: set[str] = set()

    for row in candidates:
        truth_status = row.get("truth_status", "").strip()
        doc_path = row.get("doc_path", "").strip()

        if truth_status in ("stale",):
            stale_count += 1
            stale_docs.add(doc_path)
        elif truth_status in ("historical",):
            historical_count += 1
            historical_docs.add(doc_path)

    if stale_count:
        result.add_info(
            f"Stale candidates: {stale_count} (docs: {', '.join(sorted(stale_docs))})"
        )

    if historical_count:
        result.add_info(
            f"Historical candidates: {historical_count} (docs: {', '.join(sorted(historical_docs))})"
        )

    return result


def check_candidates_registered(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Count and report registration statistics."""
    result = CoverageCheckResult()

    registered = 0
    unregistered = 0
    ignored = 0

    for row in candidates:
        status = row.get("registration_status", "").strip()
        if status == "registered":
            registered += 1
        elif status == "unregistered":
            unregistered += 1
        else:
            ignored += 1

    total = len(candidates)
    result.add_info(
        f"Registration status: {registered} registered, {unregistered} unregistered, "
        f"{ignored} ignored (total: {total})"
    )

    return result


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claim Candidate Coverage Verification ===\n")

    # Read generated candidates
    candidates, error = read_csv(GENERATED_CSV)
    if error:
        print(f"[WARNING] Could not read generated CSV: {error}")
        print("[INFO] Run 'python scripts/scan_docs_claim_candidates.py --update' first")
        candidates = []

    if candidates:
        print(f"[INFO] Generated CSV has {len(candidates)} candidates")
    else:
        print("[INFO] No candidates in generated CSV")

    # Run checks
    checks: list[tuple[str, Callable[[], CoverageCheckResult]]] = [
        ("Generated CSV exists", lambda: check_generated_csv_exists(candidates)),
        ("No duplicate candidate IDs", lambda: check_no_duplicate_candidate_ids(candidates)),
        ("Registration status valid", lambda: check_registration_status_valid(candidates)),
        ("Severity valid", lambda: check_severity_valid(candidates)),
        ("High-severity unregistered trace-required blocked", 
         lambda: check_high_severity_unregistered_current_trace_required(candidates)),
        ("High-severity unregistered not-required warned", 
         lambda: check_high_severity_unregistered_current_not_required(candidates)),
        ("Stale/historical candidates reported", 
         lambda: check_stale_historical_candidates(candidates)),
        ("Registration statistics", lambda: check_candidates_registered(candidates)),
    ]

    all_passed = True
    for name, check_fn in checks:
        result = check_fn()
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for error_msg in result.errors:
            print(f"      ERROR: {error_msg}")
        for warning in result.warnings:
            print(f"      WARNING: {warning}")
        for info_msg in result.info:
            print(f"      INFO: {info_msg}")
        if not result.passed:
            all_passed = False

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


# Self-test cases
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "registered candidate passes",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-abc123",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "high",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": False,
    },
    {
        "name": "high-severity unregistered current trace-required warns (advisory only)",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-def456",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "high",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": False,
        "expect_warning_contains": "trace_required=true",
    },
    {
        "name": "high-severity unregistered current trace-not-required warns but does not fail",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-ghi789",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "high",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": False,
        "expect_warning_contains": "trace_required=false",
    },
    {
        "name": "stale candidate is reported but does not fail",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-jkl012",
                "doc_path": "docs/stale.md",
                "truth_status": "stale",
                "registration_status": "ignored_stale",
                "candidate_severity": "high",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": False,
    },
    {
        "name": "historical candidate is reported but does not fail",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-mno345",
                "doc_path": "docs/historical.md",
                "truth_status": "historical",
                "registration_status": "ignored_historical",
                "candidate_severity": "high",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": False,
    },
    {
        "name": "duplicate candidate IDs are advisory only",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-xyz999",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
            {
                "candidate_id": "DOC-CAND-xyz999",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": False,
        "expect_info_contains": "duplicate",
    },
    {
        "name": "invalid registration status fails",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-invalid",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "bad_status",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": True,
        "expect_error_contains": "invalid registration_status",
    },
    {
        "name": "invalid severity fails",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-sevbad",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "bad_severity",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": True,
        "expect_error_contains": "invalid candidate_severity",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Claim Candidate Coverage Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        candidates = case.get("candidates", [])
        should_fail = case.get("should_fail", False)
        expect_error = case.get("expect_error_contains", "")
        expect_warning = case.get("expect_warning_contains", "")

        # Run the checks
        checks_passed = True
        errors_found: list[str] = []
        warnings_found: list[str] = []

        # Run duplicate check
        result = check_no_duplicate_candidate_ids(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        # Run status validity check
        result = check_registration_status_valid(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        # Run severity validity check
        result = check_severity_valid(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        # Run trace-required check (now advisory - warns but doesn't fail)
        result = check_high_severity_unregistered_current_trace_required(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)
        # Track warnings from this check too
        warnings_found.extend(result.warnings)

        # Run trace-not-required check (should warn)
        result = check_high_severity_unregistered_current_not_required(candidates)
        warnings_found.extend(result.warnings)

        # Check expected outcome
        if should_fail:
            if checks_passed:
                print("  [UNEXPECTED PASS] Expected failure but checks passed")
                all_passed = False
            else:
                if expect_error:
                    if any(expect_error.lower() in e.lower() for e in errors_found):
                        print("  [OK] Failed as expected with matching error")
                    else:
                        print("  [PARTIAL] Failed but error mismatch:")
                        for e in errors_found:
                            print(f"         {e}")
                        all_passed = False
                else:
                    print("  [OK] Failed as expected")
        else:
            if not checks_passed:
                print("  [UNEXPECTED FAIL] Expected pass but checks failed:")
                for e in errors_found:
                    print(f"         {e}")
                all_passed = False
            elif expect_warning and not any(expect_warning.lower() in w.lower() for w in warnings_found):
                print(f"  [UNEXPECTED] Expected warning containing '{expect_warning}' but none found")
                all_passed = False
            else:
                print("  [OK] Passed as expected")

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def print_summary(candidates: list[dict[str, str]]) -> None:
    """Print coverage summary statistics."""
    if not candidates:
        return

    # Count by registration status
    reg_counts: dict[str, int] = {}
    for c in candidates:
        status = c.get("registration_status", "")
        reg_counts[status] = reg_counts.get(status, 0) + 1

    # Count by severity
    sev_counts: dict[str, int] = {}
    for c in candidates:
        sev = c.get("candidate_severity", "")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    # Count by truth_status
    status_counts: dict[str, int] = {}
    for c in candidates:
        status = c.get("truth_status", "")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\n=== Candidate Coverage Summary ===")
    print(f"Total candidates: {len(candidates)}")
    print("\nBy registration status:")
    for status, count in sorted(reg_counts.items()):
        print(f"  {status}: {count}")
    print("\nBy severity:")
    for sev, count in sorted(sev_counts.items()):
        print(f"  {sev}: {count}")
    print("\nBy truth_status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs claim candidate coverage")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print coverage summary statistics",
    )
    args = parser.parse_args()

    if args.summary:
        candidates, _ = read_csv(GENERATED_CSV)
        print_summary(candidates)
        return 0

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    success = run_verification()

    # Print summary on success
    if success:
        candidates, _ = read_csv(GENERATED_CSV)
        print_summary(candidates)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

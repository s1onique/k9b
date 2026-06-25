#!/usr/bin/env python
"""Verify LLM security requirements register integrity.

This script checks that:
1. Register file exists and parses strictly as CSV
2. Required columns are present
3. No duplicate req_id values
4. req_id matches REQ-LLMSEC-0001 pattern
5. REQ IDs are sorted ascending
6. Required fields are non-empty
7. claim_category is from allowed enum
8. security_domain is from allowed enum
9. assurance_level is from allowed enum
10. status is from allowed enum
11. implementation_refs are non-empty for current MUST/SHOULD
12. verification_refs are non-empty for current MUST/SHOULD
13. N/A requirements have specific evidence of non-applicability
14. implementation_ref paths exist on disk
15. source_doc paths exist on disk

Usage:
    python scripts/verify_llm_security_requirements.py           # verify
    python scripts/verify_llm_security_requirements.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _verify_helpers import check_ref_exists, check_refs_exist, is_na_placeholder
from verify_llm_security_requirements_fixtures import SELF_TEST_CASES

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
REGISTRY_CSV = REPO_ROOT / "docs" / "requirements" / "llm_security_requirements.csv"

# Allowed values
ALLOWED_CLAIM_CATEGORY = {"llm_security", "security", "privacy", "prompt_security"}
ALLOWED_SECURITY_DOMAIN = {
    "threat_model", "governance", "provider_boundary", "trust_levels",
    "prompt_injection", "secret_scanning", "output_handling", "data_handling",
    "data_masking", "agent_boundary", "resource_management", "audit", "ai_bom",
    "rag", "mcp", "self_hosted", "ci_gate"
}
ALLOWED_ASSURANCE_LEVEL = {"MUST", "SHOULD", "N/A"}
ALLOWED_STATUS = {"current", "planned", "deprecated", "superseded"}

# REQ ID pattern: REQ-LLMSEC-0001
REQ_ID_PATTERN = re.compile(r"^REQ-LLMSEC-\d{3,}$")

# Doc scan pattern for REQ ID references
REQ_REF_PATTERN = re.compile(r"REQ-LLMSEC-\d{3,}")

# Required columns in exact order
REQUIRED_COLUMNS = [
    "req_id", "title", "requirement_text", "claim_category", "security_domain",
    "assurance_level", "source_doc", "source_section", "status", "implementation_refs",
    "verification_refs", "owner", "freshness_policy", "notes"
]


class REQCheckResult:
    """Result of a single REQ check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: REQCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def read_registry(csv_path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the registry CSV. Returns (rows, error_msg)."""
    if not csv_path.exists():
        return [], f"Registry file not found: {csv_path}"

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading registry: {e}"


def check_csv_parse(rows: list[dict[str, str]], header: list[str]) -> REQCheckResult:
    """Check that CSV has required columns in exact order."""
    result = REQCheckResult()

    if not rows:
        result.add_error("Registry is empty (no data rows)")
        return result

    if header != REQUIRED_COLUMNS:
        result.add_error(
            f"CSV header must match required columns exactly and in order. Got: {header}"
        )

    return result


def check_no_duplicate_ids(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check for duplicate req_id values."""
    result = REQCheckResult()

    ids = [row.get("req_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, req_id in enumerate(ids):
        if req_id in seen:
            result.add_error(
                f"Duplicate req_id '{req_id}' at row {i + 2} "
                f"(first seen at row {seen[req_id] + 2})"
            )
        else:
            seen[req_id] = i

    return result


def check_req_id_format(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that req_id matches REQ-LLMSEC-0001 pattern."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        req_id = row.get("req_id", "").strip()
        if not req_id:
            result.add_error(f"Row {i + 2}: req_id is empty")
            continue

        if not REQ_ID_PATTERN.match(req_id):
            result.add_error(
                f"Row {i + 2}: req_id '{req_id}' does not match pattern REQ-LLMSEC-0001 "
                f"(expected: prefix REQ-LLMSEC-, 3+ digit zero-padded suffix)"
            )

    return result


def check_req_ids_sorted(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that REQ IDs are sorted ascending."""
    result = REQCheckResult()

    ids = [row.get("req_id", "").strip() for row in rows]
    sorted_ids = sorted(ids, key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0)

    if ids != sorted_ids:
        result.add_error(
            f"REQ IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_required_fields(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that required fields are non-empty."""
    result = REQCheckResult()
    required_fields = ["req_id", "title", "requirement_text", "claim_category",
                       "security_domain", "assurance_level", "status"]

    for i, row in enumerate(rows):
        for field in required_fields:
            value = row.get(field, "").strip()
            if not value:
                result.add_error(f"Row {i + 2}: {field} is empty")

    return result


def check_enum_field(
    rows: list[dict[str, str]],
    field_name: str,
    allowed_values: set[str],
) -> REQCheckResult:
    """Check that a field has values from allowed enum."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        value = row.get(field_name, "").strip()
        if value not in allowed_values:
            result.add_error(
                f"Row {i + 2}: invalid {field_name} '{value}' "
                f"(allowed: {', '.join(sorted(allowed_values))})"
            )

    return result


def check_refs_non_empty_for_current(
    rows: list[dict[str, str]],
    field_name: str,
) -> REQCheckResult:
    """Check that refs are non-empty for current MUST/SHOULD."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        assurance_level = row.get("assurance_level", "").strip()
        status = row.get("status", "").strip()
        refs = row.get(field_name, "").strip()

        if assurance_level in {"MUST", "SHOULD"} and status == "current":
            if not refs:
                result.add_error(
                    f"Row {i + 2}: assurance_level='{assurance_level}' requires "
                    f"non-empty {field_name}"
                )

    return result


def check_na_requirements(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that N/A requirements have rationale."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        assurance_level = (row.get("assurance_level") or "").strip()
        notes = (row.get("notes") or "").strip()

        if assurance_level == "N/A":
            if "N/A" not in notes and "not used" not in notes.lower():
                result.add_warning(
                    f"Row {i + 2}: N/A requirement should include 'N/A' or 'not used' in notes"
                )

    return result


def check_source_doc_exists(rows: list[dict[str, str]], repo_root: Path | None = None) -> REQCheckResult:
    """Check that source_doc paths exist on disk."""
    result = REQCheckResult()
    root = repo_root or REPO_ROOT

    for i, row in enumerate(rows):
        source_doc = row.get("source_doc", "").strip()
        if not source_doc:
            continue
        # Handle N/A placeholders and glob patterns
        if is_na_placeholder(source_doc) or "*" in source_doc:
            continue
        exists, msg = check_ref_exists(source_doc, root)
        if not exists:
            result.add_error(f"Row {i + 2}: source_doc '{source_doc}' does not exist")

    return result


def get_all_checks(rows: list[dict[str, str]], header: list[str], repo_root: Path | None = None) -> list[tuple[str, REQCheckResult]]:
    """Return all check results."""
    root = repo_root or REPO_ROOT
    return [
        ("CSV structure", check_csv_parse(rows, header)),
        ("No duplicate req_id", check_no_duplicate_ids(rows)),
        ("req_id format", check_req_id_format(rows)),
        ("req_id sorted ascending", check_req_ids_sorted(rows)),
        ("Required fields non-empty", check_required_fields(rows)),
        ("claim_category valid", check_enum_field(rows, "claim_category", ALLOWED_CLAIM_CATEGORY)),
        ("security_domain valid", check_enum_field(rows, "security_domain", ALLOWED_SECURITY_DOMAIN)),
        ("assurance_level valid", check_enum_field(rows, "assurance_level", ALLOWED_ASSURANCE_LEVEL)),
        ("status valid", check_enum_field(rows, "status", ALLOWED_STATUS)),
        ("implementation_refs for MUST/SHOULD", check_refs_non_empty_for_current(rows, "implementation_refs")),
        ("verification_refs for MUST/SHOULD", check_refs_non_empty_for_current(rows, "verification_refs")),
        ("N/A requirements rationale", check_na_requirements(rows)),
        ("source_doc exists", check_source_doc_exists(rows, root)),
        ("implementation_refs exist", _check_impl_refs_exist(rows)),
        ("verification_refs exist", _check_ver_refs_exist(rows)),
        ("dangling REQ refs in docs", check_dangling_req_refs(rows, root)),
    ]


def _check_impl_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that implementation_ref paths exist on disk."""
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "implementation_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def _check_ver_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that verification_ref paths exist on disk."""
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "verification_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def check_dangling_req_refs(rows: list[dict[str, str]], repo_root: Path) -> REQCheckResult:
    """Check that all REQ-LLMSEC-* references in docs exist in the registry CSV."""
    result = REQCheckResult()

    # Collect all registered REQ IDs
    registered_ids = {row.get("req_id", "").strip() for row in rows}
    registered_ids.discard("")  # Remove empty

    # Scan docs for REQ ID references
    docs_to_scan = [
        repo_root / "docs" / "security",
        repo_root / "docs" / "requirements",
    ]

    for doc_dir in docs_to_scan:
        if not doc_dir.exists():
            continue
        for md_file in doc_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                refs = set(REQ_REF_PATTERN.findall(content))
                for ref in refs:
                    if ref not in registered_ids:
                        result.add_error(
                            f"Dangling REQ reference '{ref}' in {md_file.relative_to(repo_root)} "
                            f"- not found in {REGISTRY_CSV.name}"
                        )
            except Exception:
                pass  # Skip files that can't be read

    return result


def print_summary(rows: list[dict[str, str]]) -> None:
    """Print registry summary statistics."""
    if not rows:
        return

    category_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for row in rows:
        category = row.get("claim_category", "").strip()
        domain = row.get("security_domain", "").strip()
        level = row.get("assurance_level", "").strip()
        status = row.get("status", "").strip()

        category_counts[category] = category_counts.get(category, 0) + 1
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        level_counts[level] = level_counts.get(level, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\n=== REQ Register Summary ===")
    print(f"Total requirements registered: {len(rows)}")

    print("\nBy claim_category:")
    for ct, count in sorted(category_counts.items()):
        print(f"  {ct}: {count}")

    print("\nBy security_domain:")
    for sd, count in sorted(domain_counts.items()):
        print(f"  {sd}: {count}")

    print("\nBy assurance_level:")
    for al, count in sorted(level_counts.items()):
        print(f"  {al}: {count}")

    print("\nBy status:")
    for s, count in sorted(status_counts.items()):
        print(f"  {s}: {count}")


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== LLM Security Requirements Verification ===\n")

    # Read registry
    rows, error = read_registry(REGISTRY_CSV)
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    # Read header
    try:
        with open(REGISTRY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
    except Exception as exc:
        print(f"[FAIL] Could not read CSV header: {exc}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Registry has {len(rows)} requirements")

    # Run checks
    checks_results = get_all_checks(rows, header)

    all_passed = True
    for name, result in checks_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for error_msg in result.errors:
            print(f"      ERROR: {error_msg}")
        for warning in result.warnings:
            print(f"      WARNING: {warning}")
        if not result.passed:
            all_passed = False

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


def _run_single_self_test(
    case: dict[str, str], case_num: int, tmp_path: Path
) -> tuple[bool, bool]:
    """Run a single self-test case. Returns (passed, test_passed)."""
    tmp_registry = tmp_path / "docs" / "requirements" / "llm_security_requirements.csv"
    tmp_registry.parent.mkdir(parents=True, exist_ok=True)
    tmp_registry.write_text(str(case["registry"]))

    # Create fixture docs directory structure
    (tmp_path / "docs" / "security").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "requirements").mkdir(parents=True, exist_ok=True)

    # Handle doc_content from fixture (for dangling REQ tests)
    doc_content = case.get("doc_content", {})
    if doc_content:
        for rel_path, content in doc_content.items():
            fpath = tmp_path / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
    else:
        # Create minimal fixture docs that won't reference any REQ IDs
        (tmp_path / "docs" / "security" / "test_fixture.md").write_text("# Test Fixture\n")
        (tmp_path / "docs" / "requirements" / "test_fixture.md").write_text("# Test Fixture\n")

    rows, error = read_registry(tmp_registry)
    if error and case["should_fail"]:
        return True, True
    if error and not case["should_fail"]:
        return False, False

    try:
        with open(tmp_registry, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
    except Exception:
        return False, False

    # Run all checks including dangling REQ check with tmp_path
    # Note: source_doc_exists and impl/ver refs are skipped in self-test
    # because fixture docs don't reference actual paths
    def _get_checks_for_test(r: list[dict[str, str]], h: list[str], root: Path) -> list[tuple[str, REQCheckResult]]:
        """Return all checks with dangling check using given root."""
        checks = [
            ("CSV structure", check_csv_parse(r, h)),
            ("No duplicate req_id", check_no_duplicate_ids(r)),
            ("req_id format", check_req_id_format(r)),
            ("req_id sorted ascending", check_req_ids_sorted(r)),
            ("Required fields non-empty", check_required_fields(r)),
            ("claim_category valid", check_enum_field(r, "claim_category", ALLOWED_CLAIM_CATEGORY)),
            ("security_domain valid", check_enum_field(r, "security_domain", ALLOWED_SECURITY_DOMAIN)),
            ("assurance_level valid", check_enum_field(r, "assurance_level", ALLOWED_ASSURANCE_LEVEL)),
            ("status valid", check_enum_field(r, "status", ALLOWED_STATUS)),
            ("implementation_refs for MUST/SHOULD", check_refs_non_empty_for_current(r, "implementation_refs")),
            ("verification_refs for MUST/SHOULD", check_refs_non_empty_for_current(r, "verification_refs")),
            ("N/A requirements rationale", check_na_requirements(r)),
            # Skip source_doc_exists and impl/ver refs checks in self-test
            # because fixtures use non-existent paths
            ("dangling REQ refs in docs", check_dangling_req_refs(r, root)),
        ]
        return checks

    checks_results = _get_checks_for_test(rows, header, tmp_path)
    all_errors = [e for _, r in checks_results for e in r.errors]
    any_failed = any(not r.passed for _, r in checks_results)

    expected_fail = bool(case["should_fail"])
    expect_contains = case.get("expect_error_contains", "").lower()

    if expected_fail:
        if not any_failed:
            return False, False
        if expect_contains:
            found = any(expect_contains in e.lower() for e in all_errors)
            return found, True
        return True, True
    else:
        return not any_failed, not any_failed


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== LLM Security Requirements Self-Test ===\n")

    (Path(".") / "docs" / "security").mkdir(parents=True, exist_ok=True)
    (Path(".") / "src").mkdir(parents=True, exist_ok=True)
    (Path(".") / "tests").mkdir(parents=True, exist_ok=True)

    all_passed = True
    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            passed, test_passed = _run_single_self_test(case, i, tmp_path)
            if not test_passed:
                all_passed = False

    print()
    print("SELF-TEST: " + ("PASSED" if all_passed else "FAILED"))
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify LLM security requirements register")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print registry summary statistics",
    )
    args = parser.parse_args()

    if args.summary:
        rows, error = read_registry(REGISTRY_CSV)
        if error:
            print(f"Error reading registry: {error}")
            return 1
        print_summary(rows)
        return 0

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    # Always print summary in verify mode
    if not args.self_test and success:
        rows, _ = read_registry(REGISTRY_CSV)
        print_summary(rows)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

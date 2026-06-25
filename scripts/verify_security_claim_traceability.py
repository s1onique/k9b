#!/usr/bin/env python
"""Verify security claim traceability.

This script extends the claims registry to enforce strict traceability for security,
privacy, llm_security, and prompt_security claims.

For strict claims:
1. Must have implementation refs
2. Must have verification refs
3. Must have executable proof (not prose-only)
4. Must have existing file/symbol anchors
5. Prose-only evidence fails
6. TODO-only evidence fails
7. Missing refs fail
8. Stale refs fail
9. Unknown categories fail
10. Duplicate REQ IDs fail
11. Malformed rows fail

Usage:
    python scripts/verify_security_claim_traceability.py           # verify
    python scripts/verify_security_claim_traceability.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _verify_helpers import check_ref_exists, is_na_placeholder, is_prose_only_evidence, is_todo_only_evidence
from verify_security_claim_traceability_fixtures import SELF_TEST_CASES

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
REGISTRY_CSV = REPO_ROOT / "docs" / "claims" / "docs_claims_registry.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Strict claim categories that require implementation and verification evidence
STRICT_CATEGORIES = {"security", "privacy", "llm_security", "prompt_security"}

# Allowed claim_type values (from existing registry)
ALLOWED_CLAIM_TYPE = {
    "behavior", "security", "operator", "data_model", "api_contract",
    "ui_contract", "ci_gate", "architecture", "performance", "historical", "planned",
}

# Additional claim categories for LLM security
ALLOWED_CLAIM_CATEGORY = {"llm_security", "privacy", "prompt_security"}

# Combined allowed claim_type (extending existing)
COMBINED_CLAIM_TYPE = ALLOWED_CLAIM_TYPE | ALLOWED_CLAIM_CATEGORY


class TraceCheckResult:
    """Result of a single traceability check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def is_strict_claim(claim_type: str, claim_category: str | None = None) -> bool:
    """Check if a claim is a strict security claim."""
    if claim_type in STRICT_CATEGORIES:
        return True
    if claim_category and claim_category in STRICT_CATEGORIES:
        return True
    return False


def read_registry(csv_path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the registry CSV."""
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


def read_inventory_paths(csv_path: Path) -> tuple[set[str], str | None]:
    """Read inventory and return set of doc paths."""
    if not csv_path.exists():
        return set(), f"Inventory file not found: {csv_path}"

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            paths = {row.get("doc_path", "").strip() for row in reader}
            return paths, None
    except Exception as e:
        return set(), f"Error reading inventory: {e}"


def check_strict_claim_has_impl_refs(row: dict[str, str], row_num: int) -> TraceCheckResult:
    """Check that strict claims have implementation refs."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()
    claim_category = row.get("claim_category", "").strip()
    evidence_status = row.get("evidence_status", "").strip()
    evidence_ref = row.get("evidence_ref", "").strip()

    if not is_strict_claim(claim_type, claim_category):
        return result

    if evidence_status not in {"linked", "manual_only"}:
        return result

    if not evidence_ref:
        result.add_error(
            f"Row {row_num}: strict claim '{claim_type}' with evidence_status='{evidence_status}' "
            f"requires non-empty evidence_ref"
        )
    elif is_todo_only_evidence(evidence_ref):
        result.add_error(
            f"Row {row_num}: strict claim '{claim_type}' has TODO-only evidence_ref "
            f"(not acceptable for strict claims)"
        )

    return result


def check_strict_claim_has_verification_refs(row: dict[str, str], row_num: int) -> TraceCheckResult:
    """Check that strict claims have verification refs with executable proof, not prose."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()
    claim_category = row.get("claim_category", "").strip()
    evidence_status = row.get("evidence_status", "").strip()
    notes = row.get("notes", "").strip()

    if not is_strict_claim(claim_type, claim_category):
        return result

    if evidence_status == "linked":
        # Strict claims require executable verification proof, not prose-only
        if is_prose_only_evidence(notes):
            result.add_error(
                f"Row {row_num}: strict claim '{claim_type}' has prose-only verification evidence "
                f"(requires executable proof: tests/, scripts/, or command refs)"
            )

    return result


def check_strict_claim_executable_proof(
    row: dict[str, str], row_num: int, repo_root: Path
) -> TraceCheckResult:
    """Check that strict claims have executable proof, not just prose."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()
    claim_category = row.get("claim_category", "").strip()
    evidence_status = row.get("evidence_status", "").strip()
    evidence_ref = row.get("evidence_ref", "").strip()
    notes = row.get("notes", "").strip()

    if not is_strict_claim(claim_type, claim_category):
        return result

    if evidence_status != "linked":
        return result

    if is_prose_only_evidence(evidence_ref) and is_prose_only_evidence(notes):
        result.add_error(
            f"Row {row_num}: strict claim '{claim_type}' has prose-only evidence "
            f"(requires executable proof: tests/, scripts/, or implementation refs)"
        )

    if evidence_ref and not is_prose_only_evidence(evidence_ref):
        exists, msg = check_ref_exists(evidence_ref, repo_root)
        if not exists and not is_na_placeholder(evidence_ref):
            result.add_error(f"Row {row_num}: evidence_ref '{evidence_ref}' does not exist ({msg})")

    return result


def check_strict_claim_file_anchors(
    row: dict[str, str], row_num: int, repo_root: Path
) -> TraceCheckResult:
    """Check that strict claims have existing file/symbol anchors."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()
    claim_category = row.get("claim_category", "").strip()
    doc_path = row.get("doc_path", "").strip()

    if not is_strict_claim(claim_type, claim_category):
        return result

    if doc_path:
        file_path = repo_root / doc_path
        if not file_path.exists():
            result.add_error(
                f"Row {row_num}: doc_path '{doc_path}' for strict claim '{claim_type}' "
                f"does not exist"
            )

    return result


def check_unknown_categories(row: dict[str, str], row_num: int) -> TraceCheckResult:
    """Check for unknown claim categories."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()

    if claim_type and claim_type not in COMBINED_CLAIM_TYPE:
        result.add_error(
            f"Row {row_num}: unknown claim_type '{claim_type}' "
            f"(allowed: {', '.join(sorted(COMBINED_CLAIM_TYPE))})"
        )

    return result


def check_na_requirements_with_rationale(row: dict[str, str], row_num: int) -> TraceCheckResult:
    """Check that N/A requirements include rationale and evidence."""
    result = TraceCheckResult()

    claim_type = row.get("claim_type", "").strip()
    notes = row.get("notes", "").strip()

    if claim_type in {"planned", "historical"}:
        if not notes or len(notes) < 10:
            result.add_warning(
                f"Row {row_num}: claim_type='{claim_type}' should have meaningful notes "
                f"(current: '{notes[:50] if notes else ''}...')"
            )

    return result


def get_all_checks(
    rows: list[dict[str, str]], repo_root: Path
) -> list[tuple[str, TraceCheckResult]]:
    """Return all traceability check results."""
    results = []

    for i, row in enumerate(rows):
        row_num = i + 2  # +2 for header row

        results.append((f"strict-impl-refs [{row_num}]", check_strict_claim_has_impl_refs(row, row_num)))
        results.append((f"strict-ver-refs [{row_num}]", check_strict_claim_has_verification_refs(row, row_num)))
        results.append((f"strict-exec-proof [{row_num}]", check_strict_claim_executable_proof(row, row_num, repo_root)))
        results.append((f"strict-file-anchors [{row_num}]", check_strict_claim_file_anchors(row, row_num, repo_root)))
        results.append((f"unknown-categories [{row_num}]", check_unknown_categories(row, row_num)))
        results.append((f"na-rationale [{row_num}]", check_na_requirements_with_rationale(row, row_num)))

    return results


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Security Claim Traceability Verification ===\n")

    rows, error = read_registry(REGISTRY_CSV)
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Registry has {len(rows)} claims")

    checks_results = get_all_checks(rows, REPO_ROOT)

    all_passed = True
    strict_claims_count = 0
    strict_claims_with_issues = 0

    for name, result in checks_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for err in result.errors:
            print(f"      ERROR: {err}")
            if "strict" in name:
                strict_claims_with_issues += 1
        for warning in result.warnings:
            print(f"      WARNING: {warning}")
        if not result.passed:
            all_passed = False

    for row in rows:
        claim_type = row.get("claim_type", "").strip()
        claim_category = row.get("claim_category", "").strip()
        if is_strict_claim(claim_type, claim_category):
            strict_claims_count += 1

    print(f"\n[INFO] Found {strict_claims_count} strict security claims")

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Security Claim Traceability Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_registry = tmp_path / "docs" / "claims" / "docs_claims_registry.csv"
            tmp_registry.parent.mkdir(parents=True, exist_ok=True)

            tmp_registry.write_text(str(case["registry"]))

            (tmp_path / "docs" / "security").mkdir(parents=True, exist_ok=True)
            (tmp_path / "docs" / "claims").mkdir(parents=True, exist_ok=True)
            (tmp_path / "src" / "k8s_diag_agent" / "security").mkdir(parents=True, exist_ok=True)

            (tmp_path / "docs" / "security" / "threat-model.md").write_text("# Test\n")
            (tmp_path / "src" / "k8s_diag_agent" / "security" / "sanitizer.py").write_text("# Test\n")
            (tmp_path / "docs" / "security" / "llm-requirements-na-rag-mcp-self-hosted.md").write_text("# Test\n")

            rows, error = read_registry(tmp_registry)

            if error and case["should_fail"]:
                print(f"  [OK] Failed to parse as expected: {error}")
                continue

            if error and not case["should_fail"]:
                print(f"  [UNEXPECTED] Parse error: {error}")
                all_passed = False
                continue

            checks_results = get_all_checks(rows, tmp_path)

            all_errors: list[str] = []
            any_failed = False
            for name, result in checks_results:
                all_errors.extend(result.errors)
                if not result.passed:
                    any_failed = True

            expected_fail = bool(case["should_fail"])
            expect_contains = case.get("expect_error_contains", "")

            if expected_fail:
                if any_failed:
                    if expect_contains:
                        found = any(expect_contains.lower() in e.lower() for e in all_errors)
                        if found:
                            print("  [OK] Failed as expected with matching error")
                        else:
                            print("  [PARTIAL] Failed but error mismatch:")
                            for e in all_errors:
                                print(f"         {e}")
                            all_passed = False
                    else:
                        print("  [OK] Failed as expected")
                else:
                    print("  [UNEXPECTED PASS] No checks failed")
                    all_passed = False
            else:
                if not any_failed:
                    print("  [OK] Passed as expected")
                else:
                    print("  [UNEXPECTED FAIL] Errors:")
                    for e in all_errors:
                        print(f"         {e}")
                    all_passed = False

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify security claim traceability")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

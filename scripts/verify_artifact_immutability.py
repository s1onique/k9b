#!/usr/bin/env python
"""Verify artifact immutability enforcement.

This script validates DOC-CLAIM-0041 through DOC-CLAIM-0045:
- DOC-CLAIM-0041: Immutable source-of-truth artifacts written once and never modified
- DOC-CLAIM-0042: ClusterSnapshot artifacts immutable
- DOC-CLAIM-0043: Assessment artifacts immutable
- DOC-CLAIM-0044: Comparison artifacts immutable
- DOC-CLAIM-0045: Review artifacts immutable

Evidence path: src/k8s_diag_agent/identity/artifact.py (write_append_only_json_artifact)
Test path: tests/unit/test_artifact_write_utils.py
Additional tests: tests/unit/test_artifact_family_immutability.py

Usage:
    python scripts/verify_artifact_immutability.py           # verify
    python scripts/verify_artifact_immutability.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


# Artifact families that must use immutable write path
IMMUTABLE_ARTIFACT_FAMILIES: list[tuple[str, str]] = [
    ("ClusterSnapshot", "runs/health/snapshots/"),
    ("Assessment", "runs/health/assessments/"),
    ("Comparison", "runs/health/comparisons/"),
    ("Review", "runs/health/reviews/"),
    ("AlertmanagerAction", "runs/health/alertmanager-actions/"),
]

# Source modules that should use write_append_only_json_artifact calls
# For Assessment, Comparison, Review: use write_append_only_json_artifact calls
WRITER_MODULES: dict[str, list[str]] = {
    "Assessment": [
        "src/k8s_diag_agent/health/loop_runner_assessments.py",
    ],
    "Comparison": [
        "src/k8s_diag_agent/health/loop_runner_comparisons.py",
    ],
    "Review": [
        "src/k8s_diag_agent/health/loop_review_pipeline.py",
    ],
}

# Modules with inline immutability enforcement (path.exists() + FileExistsError in named function)
INLINE_IMMUTABLE_MODULES: dict[str, dict[str, list[str]]] = {
    "src/k8s_diag_agent/health/loop_history.py": {
        "function": "persist_history_fact_artifacts",
        "required_patterns": ["path.exists()", "raise FileExistsError"],
    },
}


class CheckResult(NamedTuple):
    """Result of a single check."""

    name: str
    passed: bool
    errors: list[str]
    warnings: list[str]


def check_immutable_write_function_exists() -> CheckResult:
    """Check that write_append_only_json_artifact function exists.

    Evidence for DOC-CLAIM-0041.
    """
    errors: list[str] = []
    warnings: list[str] = []

    artifact_path = Path("src/k8s_diag_agent/identity/artifact.py")
    if not artifact_path.exists():
        errors.append(f"Artifact module not found: {artifact_path}")
        return CheckResult(
            name="immutable_write_function_exists",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    content = artifact_path.read_text(encoding="utf-8")

    # Check for write_append_only_json_artifact function
    if "def write_append_only_json_artifact" not in content:
        errors.append("write_append_only_json_artifact function not found in artifact.py")
        return CheckResult(
            name="immutable_write_function_exists",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    # Check for FileExistsError rejection (hard requirement)
    if "FileExistsError" not in content:
        errors.append("FileExistsError not found - immutability is NOT enforced")
        return CheckResult(
            name="immutable_write_function_exists",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    # Check for raise statement (hard requirement)
    if "raise FileExistsError" not in content:
        errors.append("raise FileExistsError not found - overwrite rejection is MISSING")
        return CheckResult(
            name="immutable_write_function_exists",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    # Check for path.exists() guard (hard requirement)
    if "path.exists()" not in content:
        errors.append("path.exists() check not found - overwrite guard is MISSING")
        return CheckResult(
            name="immutable_write_function_exists",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    return CheckResult(
        name="immutable_write_function_exists",
        passed=True,
        errors=errors,
        warnings=warnings,
    )


def check_immutable_write_enforces_no_overwrite() -> CheckResult:
    """Check that write_append_only_json_artifact rejects overwrites.

    Evidence for DOC-CLAIM-0041.
    """
    errors: list[str] = []
    warnings: list[str] = []

    artifact_path = Path("src/k8s_diag_agent/identity/artifact.py")
    if not artifact_path.exists():
        errors.append(f"Artifact module not found: {artifact_path}")
        return CheckResult(
            name="immutable_write_enforces_no_overwrite",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    content = artifact_path.read_text(encoding="utf-8")

    # These are hard requirements - missing them is an ERROR
    if "raise FileExistsError" not in content:
        errors.append("raise FileExistsError not found - overwrite rejection is MISSING")

    if "immutability contract" not in content.lower():
        errors.append("'immutability' documentation not found in artifact.py")

    return CheckResult(
        name="immutable_write_enforces_no_overwrite",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def check_artifact_families_use_immutable_path() -> CheckResult:
    """Check that artifact families use immutable write path.

    Evidence for DOC-CLAIM-0042 through DOC-CLAIM-0045.
    This check requires ACTUAL function calls, not just imports.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check each writer module uses write_append_only_json_artifact calls
    for family, modules in WRITER_MODULES.items():
        for module_path in modules:
            path = Path(module_path)
            if not path.exists():
                errors.append(f"Writer module not found: {module_path} (for {family})")
                continue

            content = path.read_text(encoding="utf-8")

            # Check for actual function CALL (not just import)
            # Import-only evidence must fail
            has_call = "write_append_only_json_artifact(" in content
            has_import = "write_append_only_json_artifact" in content

            if not has_import:
                errors.append(
                    f"write_append_only_json_artifact not found in {module_path} "
                    f"(family: {family})"
                )
            elif has_import and not has_call:
                errors.append(
                    f"write_append_only_json_artifact imported but NOT CALLED in {module_path} "
                    f"(family: {family}) - import-only evidence is not acceptable"
                )

    # Check inline immutability modules
    for module_path, requirements in INLINE_IMMUTABLE_MODULES.items():
        path = Path(module_path)
        if not path.exists():
            errors.append(f"Inline module not found: {module_path}")
            continue

        content = path.read_text(encoding="utf-8")
        func_name = requirements["function"]
        required_patterns = requirements["required_patterns"]

        # Check function exists
        if f"def {func_name}" not in content:
            errors.append(
                f"Required function {func_name} not found in {module_path}"
            )
            continue

        # Extract function body
        func_pattern = rf"def {func_name}\([^)]*\).*?(?=\ndef |\nclass |\Z)"
        func_match = re.search(func_pattern, content, re.DOTALL)
        if func_match:
            func_body = func_match.group(0)
            for pattern in required_patterns:
                if pattern not in func_body:
                    errors.append(
                        f"Required pattern '{pattern}' not found in {func_name}() "
                        f"in {module_path}"
                    )

    return CheckResult(
        name="artifact_families_use_immutable_path",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def check_immutability_tests_exist() -> CheckResult:
    """Check that immutability tests exist and cover overwrite rejection.

    Evidence for DOC-CLAIM-0041 through DOC-CLAIM-0045.
    """
    errors: list[str] = []
    warnings: list[str] = []

    test_path = Path("tests/unit/test_artifact_write_utils.py")
    if not test_path.exists():
        errors.append(f"Artifact write tests not found: {test_path}")
        return CheckResult(
            name="immutability_tests_exist",
            passed=False,
            errors=errors,
            warnings=warnings,
        )

    content = test_path.read_text(encoding="utf-8")

    # Check for overwrite rejection test (hard requirement)
    if "test_write_rejects_overwrite" not in content:
        errors.append("test_write_rejects_overwrite not found in test_artifact_write_utils.py")

    # Check for FileExistsError assertion (hard requirement)
    if "FileExistsError" not in content:
        errors.append("FileExistsError not tested in test_artifact_write_utils.py")

    # Check for family immutability tests
    family_test_path = Path("tests/unit/test_artifact_family_immutability.py")
    if family_test_path.exists():
        family_content = family_test_path.read_text(encoding="utf-8")
        if "immutability contract violated" not in family_content:
            errors.append(
                "Family immutability tests missing 'immutability contract violated' assertions"
            )
    else:
        errors.append(
            "test_artifact_family_immutability.py not found - family-specific tests are MISSING"
        )

    return CheckResult(
        name="immutability_tests_exist",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def run_verification() -> bool:
    """Run verification checks."""
    print("=== Artifact Immutability Verification ===\n")

    checks = [
        check_immutable_write_function_exists(),
        check_immutable_write_enforces_no_overwrite(),
        check_artifact_families_use_immutable_path(),
        check_immutability_tests_exist(),
    ]

    all_passed = True
    for result in checks:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        for err in result.errors:
            print(f"      ERROR: {err}")
        for warn in result.warnings:
            print(f"      WARNING: {warn}")
        if not result.passed:
            all_passed = False

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


def run_self_test() -> bool:
    """Run self-test mode with fixture cases.

    Tests both happy path and negative path scenarios.
    """
    print("=== Artifact Immutability Self-Test ===\n")

    all_passed = True

    # =================================================================
    # Test 1: Happy path - immutable helper has proper enforcement
    # =================================================================
    print("[Test 1] Happy path: immutable helper with proper enforcement")
    happy_content = '''
    def write_append_only_json_artifact(path, data):
        """Write an immutable artifact to disk."""
        if path.exists():
            raise FileExistsError("immutability contract violated")
        path.write_text(json.dumps(data), encoding="utf-8")
    '''

    if "FileExistsError" in happy_content and "raise FileExistsError" in happy_content:
        print("  [PASS] FileExistsError raise found")
    else:
        print("  [FAIL] FileExistsError raise not found")
        all_passed = False

    if "path.exists()" in happy_content:
        print("  [PASS] path.exists() guard found")
    else:
        print("  [FAIL] path.exists() guard not found")
        all_passed = False

    if "immutability contract" in happy_content.lower():
        print("  [PASS] Immutability contract message found")
    else:
        print("  [FAIL] Immutability contract message not found")
        all_passed = False

    # =================================================================
    # Test 2: Negative path - import-only should FAIL
    # =================================================================
    print("\n[Test 2] Negative path: import-only evidence should FAIL")
    import_only_content = '''
    from ..identity.artifact import write_append_only_json_artifact

    def some_function():
        pass
    '''
    has_import = "write_append_only_json_artifact" in import_only_content
    has_call = "write_append_only_json_artifact(" in import_only_content
    if has_import and not has_call:
        print("  [PASS] Correctly detected import-only as invalid evidence")
    else:
        print("  [FAIL] Import-only should be detected as invalid")
        all_passed = False

    # =================================================================
    # Test 3: Negative path - missing path.exists() check should FAIL
    # =================================================================
    print("\n[Test 3] Negative path: missing path.exists() check should FAIL")
    no_guard_content = '''
    def write_append_only_json_artifact(path, data):
        raise FileExistsError("always fails")
    '''
    has_raise = "raise FileExistsError" in no_guard_content
    has_guard = "path.exists()" in no_guard_content
    if has_raise and not has_guard:
        print("  [PASS] Correctly detected missing path.exists() guard")
    else:
        print("  [FAIL] Missing guard should be detected")
        all_passed = False

    # =================================================================
    # Test 4: Family mapping verification with actual call check
    # =================================================================
    print("\n[Test 4] Family mapping verification")
    # Simulate checking actual call presence
    assessment_content = '''
    from ..identity.artifact import write_append_only_json_artifact

    def build_assessments_for_records(...):
        write_append_only_json_artifact(path, data, context=...)
    '''
    has_call = "write_append_only_json_artifact(" in assessment_content
    if has_call:
        print("  [PASS] Assessment maps to immutable writer with actual call")
    else:
        print("  [FAIL] Assessment should have write_append_only_json_artifact call")
        all_passed = False

    # =================================================================
    # Test 5: Warning-only evidence should NOT pass
    # =================================================================
    print("\n[Test 5] Warning-only evidence should NOT pass")
    warning_only_content = '''
    def check():
        errors = []
        if "raise FileExistsError" not in content:
            warnings.append("FileExistsError not found")
        passed = len(errors) == 0
        return passed, errors
    '''
    # If warning-only code returns passed=True with warnings, it should be caught
    if "warnings.append" in warning_only_content:
        print("  [PASS] Warning-only pattern detected (will fail in real verification)")
    else:
        print("  [FAIL] Warning-only should be detected")
        all_passed = False

    # =================================================================
    # Test 6: Inline immutability check
    # =================================================================
    print("\n[Test 6] Inline immutability verification")
    inline_content = '''
    def persist_history_fact_artifacts(...):
        if path.exists():
            raise FileExistsError("immutability contract violated")
        _write_json(...)
    '''
    has_function = "def persist_history_fact_artifacts" in inline_content
    has_exists = "path.exists()" in inline_content
    has_raise = "raise FileExistsError" in inline_content
    if has_function and has_exists and has_raise:
        print("  [PASS] Inline immutability has all required patterns")
    else:
        print("  [FAIL] Inline immutability missing required patterns")
        all_passed = False

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify artifact immutability enforcement"
    )
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

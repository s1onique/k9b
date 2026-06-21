"""Self-test fixtures for docs_claim_candidates scanner.

Uses TemporaryDirectory for hermetic testing.
"""

from __future__ import annotations

import re
import sys

# Import from modules under test
from scripts.docs_claim_candidates_rules import (
    detect_claim_types,
    determine_severity,
    generate_candidate_id,
)

SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "detects normative MUST claim",
        "input": "The agent MUST never mutate live clusters.",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "detects security/auth claim",
        "input": "Sessions use PBKDF2 for password hashing with 600000 iterations.",
        "expect_types": True,
        "expect_severity": "high",
    },
    {
        "name": "detects API route claim",
        "input": "POST /api/auth/login accepts username and password.",
        "expect_types": True,
        "expect_severity": "medium",
    },
    {
        "name": "detects config claim",
        "input": "K9B_AUTH_ENABLED=true enables session-based authentication.",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "detects data-model claim",
        "input": "Incident lifecycle states include open, investigating, and resolved.",
        "expect_types": True,
        "expect_severity": "medium",
    },
    {
        "name": "detects source-of-truth claim",
        "input": "Diagnostic pack ZIPs are immutable source-of-truth artifacts.",
        "expect_types": True,
        "expect_severity": "high",
    },
    {
        "name": "detects CI/gate claim",
        "input": "verify_all.sh is the canonical gate that blocks merge on failure.",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "detects performance claim",
        "input": "Session idle timeout defaults to 1800 seconds (30 minutes).",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "assigns stable candidate IDs",
        "input": "The agent must never mutate live clusters.",
        "expect_id_pattern": r"^DOC-CAND-[a-f0-9]{12}$",
    },
    {
        "name": "deterministic ID generation",
        "input": "The agent must never mutate live clusters.",
        "expect_same_id_twice": True,
    },
]


def run_self_test() -> bool:
    """Run self-test mode with fixture cases."""
    print("=== Claim Candidate Scanner Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        input_text = str(case.get("input", ""))

        detected_types = detect_claim_types(input_text)

        if case.get("expect_types"):
            if not detected_types:
                print("  [FAIL] Expected to detect types, got none")
                all_passed = False
                continue
            print(f"  [OK] Detected types: {detected_types}")

        severity = determine_severity(detected_types)
        if "expect_severity" in case:
            expected = case["expect_severity"]
            if severity != expected:
                print(f"  [FAIL] Expected severity {expected}, got {severity}")
                all_passed = False
                continue
        elif "expect_severity_above" in case:
            threshold = case["expect_severity_above"]
            severity_order = {"low": 0, "medium": 1, "high": 2}
            if severity_order.get(severity, 0) < severity_order.get(threshold, 0):
                print(f"  [FAIL] Expected severity above {threshold}, got {severity}")
                all_passed = False
                continue

        print(f"  [OK] Severity: {severity}")

        if "expect_id_pattern" in case:
            pattern = case["expect_id_pattern"]
            doc_path = "test.md"
            line_number = 42
            candidate_id = generate_candidate_id(
                doc_path, input_text, "|".join(detected_types) if detected_types else "unknown", line_number
            )
            if not re.match(pattern, candidate_id):
                print(f"  [FAIL] ID {candidate_id} does not match pattern {pattern}")
                all_passed = False
                continue
            print(f"  [OK] ID: {candidate_id}")

        if case.get("expect_same_id_twice"):
            doc_path = "test.md"
            line_number = 42
            claim_type = "|".join(detected_types) if detected_types else "unknown"
            id1 = generate_candidate_id(doc_path, input_text, claim_type, line_number)
            id2 = generate_candidate_id(doc_path, input_text, claim_type, line_number)
            if id1 != id2:
                print(f"  [FAIL] IDs not deterministic: {id1} != {id2}")
                all_passed = False
                continue
            print("  [OK] IDs are deterministic")

        print("  [OK] Passed")

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    """Entry point for standalone self-test runner."""
    success = run_self_test()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

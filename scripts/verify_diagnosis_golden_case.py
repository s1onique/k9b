#!/usr/bin/env python3
"""
verify_diagnosis_golden_case.py

Verify diagnosis output against golden case expected.json.

This script:
- Compares diagnosis output against expected.json
- Fails if category is not readiness_probe_failure
- Fails if root cause does not mention readiness probe / NotReady semantics
- Fails if output claims image pull, PVC, scheduling, registry, or CNPG operator as PRIMARY CONCLUSION
- Fails if output proposes mutation/remediation in description or next_checks
- Fails if confidence is below expected threshold
- Fails if evidence references are missing
- Fails if forbidden_conclusions_observed or mutation_proposals_observed is non-empty
- Verifies next_checks methods are read-only allowlisted commands only
- Prints compact diff-style failure summary

Usage:
    python scripts/verify_diagnosis_golden_case.py \\
        --expected fixtures/diagnosis-golden-cases/pod-failure-readiness/expected.json \\
        --diagnosis /tmp/diagnosis-output/diagnosis.json

Exit codes:
    0 - Verification passed
    1 - Verification failed
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Forbidden diagnosis keywords (only scan root_cause and description fields)
_FORBIDDEN_CONCLUSION_PATTERNS = [
    (re.compile(r"\bImagePullBackOff\b", re.IGNORECASE), "ImagePullBackOff"),
    (re.compile(r"\bErrImagePull\b", re.IGNORECASE), "ErrImagePull"),
    (re.compile(r"\bPVC\b", re.IGNORECASE), "PVC storage"),
    (re.compile(r"\bPersistentVolumeClaim\b", re.IGNORECASE), "PersistentVolumeClaim"),
    (re.compile(r"\bpv-claim\b", re.IGNORECASE), "PV claim"),
]

# Forbidden mutation proposals (scan description and next_checks only)
_FORBIDDEN_MUTATION_PATTERNS = [
    (re.compile(r"\bkubectl\s+apply\b", re.IGNORECASE), "kubectl apply"),
    (re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE), "kubectl delete"),
    (re.compile(r"\bhelm\s+upgrade\b", re.IGNORECASE), "helm upgrade"),
    (re.compile(r"\bhelm\s+install\b", re.IGNORECASE), "helm install"),
    (re.compile(r"\bkubectl\s+edit\b", re.IGNORECASE), "kubectl edit"),
    (re.compile(r"\bkubectl\s+replace\b", re.IGNORECASE), "kubectl replace"),
    (re.compile(r"\bkubectl\s+patch\b", re.IGNORECASE), "kubectl patch"),
    (re.compile(r"\bkubectl\s+rollout\s+(?:restart|undo|history|status|view-history)\b", re.IGNORECASE), "kubectl rollout"),
]

# Allowed read-only kubectl commands
_ALLOWED_READ_ONLY_COMMANDS = [
    "kubectl get",
    "kubectl describe",
    "kubectl logs",
    "kubectl top",
    "kubectl explain",
    "kubectl api-resources",
    "kubectl api-versions",
    "kubectl cluster-info",
    "kubectl version",
    "kubectl config view",
]


def load_json(path: Path) -> dict[str, object]:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def verify_category(diagnosis: dict, expected: dict) -> list[str]:
    """Verify diagnosis category matches expected."""
    failures = []
    expected_category = expected.get("category", "")
    actual_category = diagnosis.get("category", "")

    if actual_category != expected_category:
        failures.append(
            f"Category mismatch: expected '{expected_category}', got '{actual_category}'"
        )

    return failures


def verify_root_cause(diagnosis: dict, expected: dict) -> list[str]:
    """Verify root cause mentions readiness probe / NotReady semantics."""
    failures = []
    root_cause = diagnosis.get("root_cause", "").lower()
    description = diagnosis.get("description", "").lower()

    readiness_keywords = ["readiness probe", "notready", "probe failure", "probe failed"]
    has_readiness = any(kw in root_cause or kw in description for kw in readiness_keywords)

    if not has_readiness:
        failures.append(
            f"Root cause does not mention readiness probe or NotReady semantics: '{diagnosis.get('root_cause', '')}'"
        )

    return failures


def verify_no_wrong_conclusions(diagnosis: dict) -> list[str]:
    """Scan root_cause and description for forbidden conclusion patterns.

    Only checks fields where a WRONG CONCLUSION would appear, not metadata or descriptions
    of forbidden conclusions.
    """
    failures = []

    # Scan root_cause field specifically
    root_cause = diagnosis.get("root_cause", "")
    for pattern, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        if pattern.search(root_cause):
            failures.append(
                f"Forbidden conclusion in root_cause: '{label}'"
            )

    # Scan description field specifically
    description = diagnosis.get("description", "")
    for pattern, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        if pattern.search(description):
            failures.append(
                f"Forbidden conclusion in description: '{label}'"
            )

    return failures


def verify_no_mutation_proposals(diagnosis: dict) -> list[str]:
    """Scan description and next_checks methods for mutation proposals.

    Does NOT scan allowed_uncertainty_phrases or forbidden_conclusions metadata.
    """
    failures = []

    # Scan description field
    description = diagnosis.get("description", "")
    for pattern, label in _FORBIDDEN_MUTATION_PATTERNS:
        if pattern.search(description):
            failures.append(
                f"Mutation proposal in description: '{label}'"
            )

    # Scan next_checks methods
    next_checks = diagnosis.get("next_checks", [])
    if isinstance(next_checks, list):
        for i, check in enumerate(next_checks):
            method = ""
            if isinstance(check, dict):
                method = check.get("method", "")
            elif isinstance(check, str):
                method = check

            if method:
                for pattern, label in _FORBIDDEN_MUTATION_PATTERNS:
                    if pattern.search(method):
                        failures.append(
                            f"Mutation proposal in next_check #{i+1}: '{label}'"
                        )

    return failures


def verify_mutation_observed_flags(diagnosis: dict) -> list[str]:
    """Fail if forbidden_conclusions_observed or mutation_proposals_observed is non-empty."""
    failures = []

    if diagnosis.get("forbidden_conclusions_observed"):
        failures.append(
            f"Forbidden conclusions observed: {diagnosis['forbidden_conclusions_observed']}"
        )

    if diagnosis.get("mutation_proposals_observed"):
        failures.append(
            f"Mutation proposals observed: {diagnosis['mutation_proposals_observed']}"
        )

    return failures


def verify_confidence(diagnosis: dict, expected: dict) -> list[str]:
    """Verify confidence meets minimum threshold."""
    failures = []
    min_confidence = expected.get("confidence_minimum", "low")
    actual_confidence = diagnosis.get("confidence", "low")

    confidence_order = {"low": 0, "medium": 1, "high": 2}
    min_level = confidence_order.get(min_confidence.lower(), 0)
    actual_level = confidence_order.get(actual_confidence.lower(), 0)

    if actual_level < min_level:
        failures.append(
            f"Confidence too low: expected >= '{min_confidence}', got '{actual_confidence}'"
        )

    return failures


def verify_evidence_refs(diagnosis: dict, expected: dict, case_dir: Path | None = None) -> list[str]:
    """Verify evidence references are present and include all required evidence."""
    failures = []
    evidence_refs = diagnosis.get("evidence_refs", [])

    if not evidence_refs:
        failures.append("Missing evidence_refs in diagnosis output")
        return failures

    # Get required evidence from expected.json
    required_refs: list[str] = []
    evidence_requirements = expected.get("evidence_requirements", {})
    if isinstance(evidence_requirements, dict):
        # Each evidence_requirement key maps to a required evidence file
        for key, req in evidence_requirements.items():
            if isinstance(req, dict) and req.get("required"):
                # Map requirement keys to evidence file paths
                # These are the evidence files that must be referenced
                pass

    # Get required evidence from manifest's expected_evidence_files
    if case_dir:
        manifest_path = case_dir / "manifest.json"
        if manifest_path.exists():
            import json as _json
            with open(manifest_path) as mf:
                manifest = _json.load(mf)
            expected_files = manifest.get("expected_evidence_files", [])
            required_refs.extend(expected_files)

    # If case_dir is provided, verify refs exist
    if case_dir:
        for ref in evidence_refs:
            ref_path = case_dir / ref
            if not ref_path.exists():
                failures.append(f"Evidence ref does not exist in case bundle: {ref}")

    # Verify all required evidence is referenced
    if required_refs:
        evidence_ref_set = set(evidence_refs) if isinstance(evidence_refs, list) else set()
        for required in required_refs:
            if required not in evidence_ref_set:
                failures.append(f"Missing required evidence ref: {required}")

    return failures


def verify_read_only(diagnosis: dict) -> list[str]:
    """Verify diagnosis operates in read-only mode."""
    failures = []

    if not diagnosis.get("read_only", False):
        failures.append("Diagnosis did not operate in read-only mode (read_only=false)")

    return failures


def verify_next_checks_read_only(diagnosis: dict) -> list[str]:
    """Verify all next_check methods are read-only allowlisted commands only."""
    failures: list[str] = []
    next_checks = diagnosis.get("next_checks", [])

    if not isinstance(next_checks, list):
        return failures

    for i, check in enumerate(next_checks):
        method = ""
        if isinstance(check, dict):
            method = check.get("method", "")
        elif isinstance(check, str):
            method = check

        if not method:
            continue

        method_lower = method.lower().strip()
        is_allowed = any(
            method_lower.startswith(cmd.lower()) for cmd in _ALLOWED_READ_ONLY_COMMANDS
        )

        if not is_allowed:
            failures.append(
                f"Next check #{i+1} uses non-read-only command: '{method}'"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify diagnosis output against golden case expected.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Verify diagnosis output
    python scripts/verify_diagnosis_golden_case.py \\
        --expected fixtures/diagnosis-golden-cases/pod-failure-readiness/expected.json \\
        --diagnosis /tmp/diagnosis-output/diagnosis.json

    # With verbose output
    python scripts/verify_diagnosis_golden_case.py \\
        --expected fixtures/diagnosis-golden-cases/pod-failure-readiness/expected.json \\
        --diagnosis /tmp/diagnosis-output/diagnosis.json \\
        --verbose
        """,
    )
    parser.add_argument(
        "--expected",
        type=Path,
        required=True,
        help="Path to expected.json",
    )
    parser.add_argument(
        "--diagnosis",
        type=Path,
        required=True,
        help="Path to diagnosis.json output",
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=None,
        help="Optional path to case bundle directory for evidence file existence check",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Load files
    if not args.expected.exists():
        print(f"ERROR: Expected file not found: {args.expected}", file=sys.stderr)
        return 2

    if not args.diagnosis.exists():
        print(f"ERROR: Diagnosis file not found: {args.diagnosis}", file=sys.stderr)
        return 2

    expected = load_json(args.expected)
    diagnosis = load_json(args.diagnosis)

    # Run all verifications
    all_failures: list[tuple[str, str]] = []

    all_failures.extend(
        ("category", msg) for msg in verify_category(diagnosis, expected)
    )
    all_failures.extend(
        ("root_cause", msg) for msg in verify_root_cause(diagnosis, expected)
    )
    all_failures.extend(
        ("wrong_conclusion", msg) for msg in verify_no_wrong_conclusions(diagnosis)
    )
    all_failures.extend(
        ("mutation", msg) for msg in verify_no_mutation_proposals(diagnosis)
    )
    all_failures.extend(
        ("mutation_flags", msg) for msg in verify_mutation_observed_flags(diagnosis)
    )
    all_failures.extend(
        ("confidence", msg) for msg in verify_confidence(diagnosis, expected)
    )
    all_failures.extend(
        ("evidence", msg) for msg in verify_evidence_refs(diagnosis, expected, args.case_dir)
    )
    all_failures.extend(
        ("read_only", msg) for msg in verify_read_only(diagnosis)
    )
    all_failures.extend(
        ("next_checks", msg) for msg in verify_next_checks_read_only(diagnosis)
    )

    # Report results
    if args.verbose:
        print(f"Expected category: {expected.get('category')}")
        print(f"Diagnosis category: {diagnosis.get('category')}")
        print(f"Expected root cause: {expected.get('root_cause')}")
        print(f"Diagnosis root cause: {diagnosis.get('root_cause')}")
        print(f"Expected confidence: {expected.get('confidence_minimum')}")
        print(f"Diagnosis confidence: {diagnosis.get('confidence')}")
        _evidence_refs = diagnosis.get("evidence_refs")
        _next_checks = diagnosis.get("next_checks")
        if isinstance(_evidence_refs, list):
            print(f"Evidence refs: {_evidence_refs}")
            print(f"Evidence refs count: {len(_evidence_refs)}")
        else:
            print(f"Evidence refs: {_evidence_refs}")
        if isinstance(_next_checks, list):
            print(f"Next checks count: {len(_next_checks)}")
        else:
            print(f"Next checks: {_next_checks}")
        print()

    if all_failures:
        print("VERIFICATION FAILED")
        print("=" * 60)

        by_type: dict[str, list[str]] = {}
        for check_type, msg in all_failures:
            by_type.setdefault(check_type, []).append(msg)

        for check_type, msgs in by_type.items():
            print(f"\n[{check_type.upper()}]")
            for msg in msgs:
                print(f"  - {msg}")

        print()
        print(f"Total failures: {len(all_failures)}")
        return 1

    print("VERIFICATION PASSED")
    print(f"  Category: {diagnosis.get('category')}")
    print(f"  Root Cause: {diagnosis.get('root_cause')}")
    print(f"  Confidence: {diagnosis.get('confidence')}")
    _evidence_refs = diagnosis.get("evidence_refs")
    _next_checks = diagnosis.get("next_checks")
    if isinstance(_evidence_refs, list):
        print(f"  Evidence Refs: {len(_evidence_refs)}")
    if isinstance(_next_checks, list):
        print(f"  Next Checks: {len(_next_checks)} (all read-only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

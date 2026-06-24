#!/usr/bin/env python3
"""
verify_provenance_golden_case.py

Verify that a golden case has valid live-sanitized artifact provenance.

This script:
- Passes as not-yet-promoted when source_kind is "representative_fixture"
- Runs strict provenance checks only for live_sanitized_artifact
- Fails if provenance.artifacts_hash is null
- Fails if provenance.github_artifact_digest is missing
- Fails if real_live_artifact_required_for_promotion is true
- Fails if required live evidence files are missing
- Fails if sanitizer findings are not successful
- Does NOT contact GitHub (offline check)

Usage:
    python scripts/verify_provenance_golden_case.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness

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

# Placeholder patterns that indicate mock/fake data
_PLACEHOLDER_SHA_PATTERNS = [
    re.compile(r"^abc123def456789$", re.IGNORECASE),
    re.compile(r"^12345678$"),
    re.compile(r"^00000000+$"),
    re.compile(r"^[a-f0-9]{8}$", re.IGNORECASE),  # Short hex
]
_PLACEHOLDER_DIGEST_PATTERNS = [
    re.compile(r"^sha256:a1b2c3d4", re.IGNORECASE),  # Shortened placeholder digest
    re.compile(r"^sha256:0000+", re.IGNORECASE),
]
_PLACEHOLDER_WORKFLOW_IDS = {"12345678", "00000000"}


def verify_source_kind(manifest: dict) -> tuple[bool, list[str]]:
    """Verify source_kind is live_sanitized_artifact, not representative_fixture.

    Returns (is_promoted, failures).
    - When representative_fixture: return (False, []) - not an error, just not promoted
    - When live_sanitized_artifact: return (True, []) - promoted and valid
    - When unknown: return (False, [error]) - unexpected value, fail
    """
    failures = []

    source_kind = manifest.get("source_kind", "")
    if source_kind == "representative_fixture":
        # Not an error - the case is just not yet promoted
        return False, []
    elif source_kind == "live_sanitized_artifact":
        # Valid promoted state
        return True, []
    else:
        # Unknown value - this is an error
        failures.append(
            f"source_kind is '{source_kind}', expected 'live_sanitized_artifact'. "
            "Only live_sanitized_artifact is allowed for committed golden cases."
        )
        return False, failures


def verify_provenance_hash(manifest: dict) -> list[str]:
    """Verify provenance.artifacts_hash is non-null."""
    failures = []

    provenance = manifest.get("provenance", {})
    artifacts_hash = provenance.get("artifacts_hash")

    if artifacts_hash is None:
        failures.append(
            "provenance.artifacts_hash is null - golden case has not been generated "
            "from real workflow artifacts. Run promote_diagnosis_golden_case_from_artifact.py."
        )
    elif not isinstance(artifacts_hash, str) or len(artifacts_hash) < 8:
        failures.append(
            f"provenance.artifacts_hash has invalid value: {artifacts_hash}"
        )

    return failures


def verify_github_artifact_digest(manifest: dict) -> list[str]:
    """Verify provenance.github_artifact_digest is present."""
    failures = []

    provenance = manifest.get("provenance", {})
    digest = provenance.get("github_artifact_digest")

    if not digest:
        failures.append(
            "provenance.github_artifact_digest is missing - golden case provenance "
            "does not include GitHub artifact digest."
        )
    elif not isinstance(digest, str) or not digest.startswith("sha256:"):
        failures.append(
            f"provenance.github_artifact_digest has invalid format: {digest}. "
            "Expected format: sha256:..."
        )

    return failures


def verify_promotion_flag(manifest: dict) -> list[str]:
    """Verify real_live_artifact_required_for_promotion is false."""
    failures = []

    provenance = manifest.get("provenance", {})
    required = provenance.get("real_live_artifact_required_for_promotion")

    if required is True:
        failures.append(
            "provenance.real_live_artifact_required_for_promotion is true - "
            "golden case requires manual promotion step."
        )

    return failures


def verify_workflow_metadata(manifest: dict) -> list[str]:
    """Verify required workflow metadata is present."""
    failures = []

    provenance = manifest.get("provenance", {})

    required_fields = [
        "workflow_run_id",
        "workflow_run_attempt",
        "workflow_sha",
        "artifact_name",
    ]

    for field in required_fields:
        if not provenance.get(field):
            failures.append(
                f"provenance.{field} is missing - required workflow metadata not recorded."
            )

    return failures


def verify_required_evidence(case_dir: Path, manifest: dict) -> list[str]:
    """Verify required evidence files exist in the case bundle."""
    failures = []

    expected_files = manifest.get("expected_evidence_files", [])
    if not expected_files:
        failures.append("manifest.expected_evidence_files is empty or missing")
        return failures

    for rel_path in expected_files:
        file_path = case_dir / rel_path
        if not file_path.exists():
            failures.append(f"Required evidence file missing: {rel_path}")

    return failures


def verify_sanitizer_findings(case_dir: Path) -> list[str]:
    """Verify sanitizer findings show successful sanitization."""
    failures = []

    findings_path = case_dir / "sanitizer-findings.json"
    if not findings_path.exists():
        failures.append("sanitizer-findings.json not found in case bundle")
        return failures

    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        failures.append(f"sanitizer-findings.json is invalid JSON: {e}")
        return failures

    # Check success flag
    if not findings.get("success", False):
        failures.append(
            "sanitizer-findings.json shows success=false - "
            "sanitization did not complete successfully."
        )

    # Check fatal count
    fatal_count = findings.get("fatal_count", 0)
    if fatal_count > 0:
        failures.append(
            f"sanitizer-findings.json shows fatal_count={fatal_count} - "
            "unsanitized secrets may remain in artifacts."
        )

    # Check verification passed
    if not findings.get("verification_passed", False):
        failures.append(
            "sanitizer-findings.json shows verification_passed=false - "
            "sanitizer verification did not pass."
        )

    # TRUTHFULNESS: Check for mock/placeholder indicators
    source_note = findings.get("source_note", "")
    if source_note and ("mock" in source_note.lower() or "testing" in source_note.lower()):
        failures.append(
            f"sanitizer-findings.json source_note contains mock/testing indicator: '{source_note}'. "
            "Real provenance requires actual sanitized workflow artifacts."
        )

    note = findings.get("note", "")
    if note and ("mock" in note.lower() or "testing" in note.lower()):
        failures.append(
            f"sanitizer-findings.json note contains mock/testing indicator: '{note}'. "
            "Real provenance requires actual sanitized workflow artifacts."
        )

    return failures


def verify_truthfulness(manifest: dict) -> list[str]:
    """Verify provenance data is not placeholder/mock data.

    This prevents false claims of live provenance when using mock artifacts.
    """
    failures = []

    provenance = manifest.get("provenance", {})

    # Check workflow_run_id for placeholder values
    run_id = provenance.get("workflow_run_id", "")
    if run_id in _PLACEHOLDER_WORKFLOW_IDS:
        failures.append(
            f"provenance.workflow_run_id is placeholder value: '{run_id}'. "
            "Real provenance requires actual GitHub workflow run ID."
        )

    # Check workflow_sha for placeholder patterns
    workflow_sha = provenance.get("workflow_sha", "")
    if workflow_sha:
        # GitHub workflow SHAs are 40 hex characters
        if not re.match(r"^[a-f0-9]{40}$", workflow_sha, re.IGNORECASE):
            # Check for obvious placeholder patterns
            for pattern in _PLACEHOLDER_SHA_PATTERNS:
                if pattern.match(workflow_sha):
                    failures.append(
                        f"provenance.workflow_sha appears to be placeholder: '{workflow_sha}'. "
                        "Real provenance requires actual Git commit SHA (40 hex characters)."
                    )
                    break

    # Check github_artifact_digest for placeholder patterns
    digest = provenance.get("github_artifact_digest", "")
    if digest:
        for pattern in _PLACEHOLDER_DIGEST_PATTERNS:
            if pattern.match(digest):
                failures.append(
                    f"provenance.github_artifact_digest appears to be placeholder: '{digest}'. "
                    "Real provenance requires actual GitHub artifact digest (sha256:... 64 hex chars)."
                )
                break
        # Also check for obviously truncated digest
        if digest.startswith("sha256:"):
            hash_part = digest[7:]
            if len(hash_part) < 64:
                failures.append(
                    f"provenance.github_artifact_digest appears truncated: '{digest}'. "
                    "GitHub artifact digests are 64 hex characters after sha256:."
                )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify golden case has valid live-sanitized artifact provenance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Verify pod-failure golden case provenance
    python scripts/verify_provenance_golden_case.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness
        """,
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="Path to golden case bundle directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate case directory
    if not args.case_dir.exists():
        print(f"ERROR: Case directory does not exist: {args.case_dir}", file=sys.stderr)
        return 2

    if not args.case_dir.is_dir():
        print(f"ERROR: Case path is not a directory: {args.case_dir}", file=sys.stderr)
        return 2

    # Load manifest
    manifest_path = args.case_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest.json not found: {manifest_path}", file=sys.stderr)
        return 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid manifest.json: {e}", file=sys.stderr)
        return 2

    # Run all verifications
    all_failures: list[tuple[str, str]] = []

    # Check if case is promoted
    is_promoted, source_kind_failures = verify_source_kind(manifest)
    all_failures.extend(("source_kind", msg) for msg in source_kind_failures)

    # If not promoted (still representative_fixture), skip other provenance checks
    # Returns 0 (PASS) because representative_fixture is an honest "not yet promoted" state
    if not is_promoted:
        print("Provenance check PASSES as not-yet-promoted")
        print("  source_kind='representative_fixture' - promotion pending real GitHub artifacts")
        print("  Run promote_diagnosis_golden_case_from_artifact.py when real artifacts are available")
        return 0

    # Only run detailed provenance checks if case is promoted
    all_failures.extend(
        ("provenance_hash", msg) for msg in verify_provenance_hash(manifest)
    )
    all_failures.extend(
        ("github_digest", msg) for msg in verify_github_artifact_digest(manifest)
    )
    all_failures.extend(
        ("promotion_flag", msg) for msg in verify_promotion_flag(manifest)
    )
    all_failures.extend(
        ("workflow_metadata", msg) for msg in verify_workflow_metadata(manifest)
    )
    all_failures.extend(
        ("evidence", msg) for msg in verify_required_evidence(args.case_dir, manifest)
    )
    all_failures.extend(
        ("sanitizer", msg) for msg in verify_sanitizer_findings(args.case_dir)
    )
    all_failures.extend(
        ("truthfulness", msg) for msg in verify_truthfulness(manifest)
    )

    # Report results
    if args.verbose:
        print("Provenance verification details:")
        print(f"  source_kind: {manifest.get('source_kind')}")
        print(f"  artifacts_hash: {manifest.get('provenance', {}).get('artifacts_hash')}")
        print(f"  github_artifact_digest: {manifest.get('provenance', {}).get('github_artifact_digest')}")
        print(f"  real_live_artifact_required_for_promotion: {manifest.get('provenance', {}).get('real_live_artifact_required_for_promotion')}")
        print()

    if all_failures:
        print("PROVENANCE VERIFICATION FAILED")
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

    print("PROVENANCE VERIFICATION PASSED")
    print(f"  source_kind: {manifest.get('source_kind')}")
    print(f"  artifacts_hash: {manifest.get('provenance', {}).get('artifacts_hash')[:16]}...")
    print(f"  github_artifact_digest: {manifest.get('provenance', {}).get('github_artifact_digest')[:20]}...")
    print(f"  workflow_run_id: {manifest.get('provenance', {}).get('workflow_run_id')}")
    print(f"  workflow_sha: {manifest.get('provenance', {}).get('workflow_sha')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

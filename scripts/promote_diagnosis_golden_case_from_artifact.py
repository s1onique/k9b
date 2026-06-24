#!/usr/bin/env python3
"""
promote_diagnosis_golden_case_from_artifact.py

Promote a representative golden case fixture to a live-sanitized artifact-backed
golden case by regenerating it from sanitized workflow artifacts.

This script:
- Accepts GitHub workflow artifact metadata as inputs
- Validates that the artifact directory is sanitized (not raw live artifacts)
- Validates sanitizer findings (success=true, fatal_count=0, verification_passed=true)
- Validates provenance metadata is real (not placeholder/mock data)
- Computes a deterministic hash of the artifact contents
- Calls build_diagnosis_golden_case.py to regenerate the case bundle
- Updates the manifest with live provenance fields

Usage:
    python scripts/promote_diagnosis_golden_case_from_artifact.py \\
        --artifact-dir lab-artifacts/live-sanitized/pod-failure \\
        --workflow-run-id <real-run-id> \\
        --workflow-run-attempt 1 \\
        --workflow-sha <40-char-sha> \\
        --artifact-name "pod-failure-lab-artifacts" \\
        --artifact-digest "sha256:<64-char-hash>" \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness

Exit codes:
    0 - Promotion successful
    1 - Validation failed (including placeholder/mock data)
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from build_diagnosis_golden_case import (
    build_case_bundle,
    validate_required_evidence,
    validate_sanitized_input,
)

# Marker file that indicates sanitized artifacts
_SANITIZED_MARKER = "_findings.json"

# Forbidden path patterns for raw artifacts
_RAW_ARTIFACT_PATTERNS = [
    "lab-artifacts/live/",
    "lab-artifacts/raw/",
]

# Placeholder patterns that indicate mock/fake data (must be validated before promotion)
_PLACEHOLDER_SHA_PATTERNS = [
    re.compile(r"^abc123def456789$", re.IGNORECASE),
    re.compile(r"^12345678$"),
    re.compile(r"^00000000+$"),
    re.compile(r"^[a-f0-9]{8}$", re.IGNORECASE),
]
_PLACEHOLDER_DIGEST_PATTERNS = [
    re.compile(r"^sha256:a1b2c3d4", re.IGNORECASE),
    re.compile(r"^sha256:0000+", re.IGNORECASE),
]
_PLACEHOLDER_WORKFLOW_IDS = {"12345678", "00000000"}


def validate_provenance_metadata(
    run_id: str,
    workflow_sha: str,
    artifact_digest: str,
) -> tuple[bool, str]:
    """Validate provenance data is not placeholder/mock data.

    This prevents false claims of live provenance when promoting.
    Real GitHub provenance requires:
    - workflow_run_id: actual GitHub run ID (numeric string)
    - workflow_sha: full 40-hex-character commit SHA
    - artifact_digest: sha256: prefix + 64 hex characters

    Returns (is_valid, error_message).
    """
    # Check workflow_run_id for placeholder values
    if run_id in _PLACEHOLDER_WORKFLOW_IDS:
        return False, (
            f"ERROR: workflow_run_id '{run_id}' is a placeholder value. "
            "Real provenance requires actual GitHub workflow run ID."
        )

    # Check workflow_sha for placeholder patterns
    if workflow_sha:
        # GitHub workflow SHAs are 40 hex characters
        if not re.match(r"^[a-f0-9]{40}$", workflow_sha, re.IGNORECASE):
            # Check for obvious placeholder patterns
            for pattern in _PLACEHOLDER_SHA_PATTERNS:
                if pattern.match(workflow_sha):
                    return False, (
                        f"ERROR: workflow_sha '{workflow_sha}' appears to be placeholder. "
                        "Real provenance requires actual Git commit SHA (40 hex characters)."
                    )
                    break
            # If it doesn't match 40 hex and isn't a known placeholder, give a clear error
            if not re.match(r"^[a-f0-9]+$", workflow_sha, re.IGNORECASE):
                return False, (
                    f"ERROR: workflow_sha '{workflow_sha}' contains invalid characters. "
                    "Git commit SHAs contain only hex characters (0-9, a-f)."
                )
            else:
                return False, (
                    f"ERROR: workflow_sha '{workflow_sha}' is not 40 hex characters. "
                    f"Length: {len(workflow_sha)}, expected: 40."
                )

    # Check artifact_digest for placeholder patterns
    if artifact_digest:
        for pattern in _PLACEHOLDER_DIGEST_PATTERNS:
            if pattern.match(artifact_digest):
                return False, (
                    f"ERROR: artifact_digest '{artifact_digest}' appears to be placeholder. "
                    "Real provenance requires actual GitHub artifact digest (sha256:... 64 hex chars)."
                )
                break
        # Also check for obviously truncated digest
        if artifact_digest.startswith("sha256:"):
            hash_part = artifact_digest[7:]
            if len(hash_part) < 64:
                return False, (
                    f"ERROR: artifact_digest '{artifact_digest}' appears truncated. "
                    "GitHub artifact digests are 64 hex characters after sha256:."
                )
        elif artifact_digest.startswith("sha256:"):
            pass  # Valid format, will be caught by length check above
        else:
            return False, (
                f"ERROR: artifact_digest '{artifact_digest}' does not start with 'sha256:'. "
                "GitHub artifact digests use sha256: prefix."
            )

    return True, ""


def compute_content_hash(artifact_dir: Path) -> str:
    """Compute a deterministic content hash of the sanitized artifact directory.

    The hash is stable across repeated runs over identical extracted content.
    Excludes transient files (findings summary).
    """
    hasher = hashlib.sha256()

    # Sort files for deterministic ordering
    for file_path in sorted(artifact_dir.rglob("*")):
        if file_path.is_file():
            # Skip the findings marker (it's generated, not part of artifact content)
            if file_path.name == _SANITIZED_MARKER:
                continue

            rel_path = str(file_path.relative_to(artifact_dir))
            # Normalize path separators for consistency
            rel_path = rel_path.replace("\\", "/")

            # Include relative path in hash for structure integrity
            hasher.update(rel_path.encode("utf-8"))
            hasher.update(b"\n")
            hasher.update(file_path.read_bytes())
            hasher.update(b"\n")

    return hasher.hexdigest()


def validate_raw_artifact_path(artifact_dir: Path) -> tuple[bool, str]:
    """Fail if input path is raw live artifacts directory.

    Returns (is_valid, error_message).
    """
    resolved = str(artifact_dir.resolve())

    for pattern in _RAW_ARTIFACT_PATTERNS:
        if pattern in resolved:
            # Check if it's NOT a sanitized path
            if "live-sanitized" not in resolved and "sanitized" not in resolved:
                return False, (
                    f"Input path contains forbidden raw artifact pattern '{pattern}'. "
                    f"Must use sanitized artifacts (lab-artifacts/live-sanitized/) "
                    f"not raw artifacts (lab-artifacts/live/)."
                )

    return True, ""


def update_manifest_provenance(
    manifest_path: Path,
    artifact_dir: Path,
    run_id: str,
    run_attempt: int,
    workflow_sha: str,
    artifact_name: str,
    artifact_digest: str,
) -> tuple[bool, str]:
    """Update manifest.json with live provenance fields.

    Returns (success, error_message).
    """
    if not manifest_path.exists():
        return False, f"Manifest not found: {manifest_path}"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"Invalid manifest JSON: {e}"

    # Compute content hash
    content_hash = compute_content_hash(artifact_dir)

    # Update provenance section
    if "provenance" not in manifest:
        manifest["provenance"] = {}

    manifest["provenance"]["artifacts_hash"] = content_hash
    manifest["provenance"]["github_artifact_digest"] = artifact_digest
    manifest["provenance"]["real_live_artifact_required_for_promotion"] = False
    manifest["provenance"]["workflow_run_id"] = run_id
    manifest["provenance"]["workflow_run_attempt"] = run_attempt
    manifest["provenance"]["workflow_sha"] = workflow_sha
    manifest["provenance"]["artifact_name"] = artifact_name
    manifest["provenance"]["artifact_downloaded_at"] = datetime.now(UTC).isoformat()

    # Update source kind
    manifest["source_kind"] = "live_sanitized_artifact"
    manifest["source_note"] = (
        "Live-derived sanitized artifact case. Generated from sanitized "
        "workflow artifacts produced by a successful K3s CNPG Incident Lab Live run. "
        "Only sanitized artifacts were used; no raw live artifacts were committed."
    )

    # Write updated manifest
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote diagnosis golden case from live-sanitized workflow artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Promote pod-failure golden case from sanitized artifacts
    python scripts/promote_diagnosis_golden_case_from_artifact.py \\
        --artifact-dir lab-artifacts/live-sanitized/pod-failure \\
        --workflow-run-id 12345678 \\
        --workflow-run-attempt 1 \\
        --workflow-sha abc123def456 \\
        --artifact-name "pod-failure-lab-artifacts" \\
        --artifact-digest "sha256:abc123..." \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness

    NOTE: Placeholder values will be rejected. Use real GitHub provenance data:
    - workflow_run_id: from gh run list (e.g., "987654321")
    - workflow_sha: 40-char commit SHA (e.g., "a1b2c3d4e5f6...")
    - artifact_digest: sha256: + 64-char hash from GitHub artifact
        """,
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Path to downloaded sanitized artifact directory",
    )
    parser.add_argument(
        "--workflow-run-id",
        type=str,
        required=True,
        help="GitHub workflow run ID (must be real, not placeholder)",
    )
    parser.add_argument(
        "--workflow-run-attempt",
        type=int,
        required=True,
        help="GitHub workflow run attempt number",
    )
    parser.add_argument(
        "--workflow-sha",
        type=str,
        required=True,
        help="Git commit SHA that triggered the workflow (must be 40 hex chars)",
    )
    parser.add_argument(
        "--artifact-name",
        type=str,
        required=True,
        help="GitHub artifact name",
    )
    parser.add_argument(
        "--artifact-digest",
        type=str,
        required=True,
        help="GitHub artifact digest (sha256:... 64 hex chars)",
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="Output directory for golden case bundle",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )

    args = parser.parse_args()

    # Validate raw artifact path
    is_valid, error_msg = validate_raw_artifact_path(args.artifact_dir)
    if not is_valid:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1

    # Validate sanitized input (marker file, sanitizer findings)
    is_valid, error_msg, findings_data = validate_sanitized_input(args.artifact_dir)
    if not is_valid:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1

    # Validate required evidence
    is_valid, missing = validate_required_evidence(args.artifact_dir, "pod-failure")
    if not is_valid:
        print("ERROR: Missing required evidence files:", file=sys.stderr)
        for f in missing:
            print(f"  - {f}", file=sys.stderr)
        return 1

    # Validate provenance metadata is real (not placeholder/mock)
    is_valid, error_msg = validate_provenance_metadata(
        args.workflow_run_id,
        args.workflow_sha,
        args.artifact_digest,
    )
    if not is_valid:
        print(error_msg, file=sys.stderr)
        return 1

    if args.dry_run:
        print("DRY RUN: Would promote golden case from live artifacts")
        print(f"  Artifact dir: {args.artifact_dir}")
        print(f"  Workflow run ID: {args.workflow_run_id}")
        print(f"  Workflow run attempt: {args.workflow_run_attempt}")
        print(f"  Workflow SHA: {args.workflow_sha}")
        print(f"  Artifact name: {args.artifact_name}")
        print(f"  Artifact digest: {args.artifact_digest}")
        print(f"  Output case dir: {args.case_dir}")
        return 0

    # Compute content hash
    content_hash = compute_content_hash(args.artifact_dir)
    print(f"Artifact content hash: {content_hash}")

    # Build the case bundle using build_diagnosis_golden_case.py
    success, error_msg = build_case_bundle(
        args.artifact_dir,
        "pod-failure",
        args.case_dir,
    )

    if not success:
        print(f"ERROR: Failed to build case bundle: {error_msg}", file=sys.stderr)
        return 1

    # Update manifest with provenance
    manifest_path = args.case_dir / "manifest.json"
    success, error_msg = update_manifest_provenance(
        manifest_path,
        args.artifact_dir,
        args.workflow_run_id,
        args.workflow_run_attempt,
        args.workflow_sha,
        args.artifact_name,
        args.artifact_digest,
    )

    if not success:
        print(f"ERROR: Failed to update manifest: {error_msg}", file=sys.stderr)
        return 1

    print("\nPromotion successful!")
    print(f"  Case dir: {args.case_dir}")
    print("  source_kind: live_sanitized_artifact")
    print(f"  artifacts_hash: {content_hash}")
    print(f"  github_artifact_digest: {args.artifact_digest}")
    print("  real_live_artifact_required_for_promotion: false")

    return 0


if __name__ == "__main__":
    sys.exit(main())

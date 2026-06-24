#!/usr/bin/env python3
"""
build_diagnosis_golden_case.py

Build a golden diagnosis case bundle from sanitized live lab artifacts.

This script:
- Consumes sanitized artifacts from lab-artifacts/live-sanitized/
- Validates that input is from sanitized directory (not raw live artifacts)
- Validates sanitizer findings JSON (success, fatal_count=0, verification_passed)
- Fails if required evidence files are missing (including CNPG state, k9b incidents)
- Produces a compact case bundle under fixtures/diagnosis-golden-cases/

Usage:
    python scripts/build_diagnosis_golden_case.py \\
        --artifact-dir lab-artifacts/live-sanitized \\
        --scenario pod-failure \\
        --output-dir fixtures/diagnosis-golden-cases/pod-failure-readiness

Exit codes:
    0 - Case bundle built successfully
    1 - Validation failed or build error
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

# Marker file that indicates sanitized artifacts
_SANITIZED_MARKER = "_findings.json"


def compute_artifact_hash(artifact_dir: Path) -> str:
    """Compute a hash of all artifact files for provenance tracking."""
    hasher = hashlib.sha256()
    for file_path in sorted(artifact_dir.rglob("*")):
        if file_path.is_file() and file_path.name != _SANITIZED_MARKER:
            hasher.update(str(file_path.relative_to(artifact_dir)).encode())
            hasher.update(file_path.read_bytes())
    return hasher.hexdigest()[:16]


def validate_sanitized_input(artifact_dir: Path) -> tuple[bool, str, dict]:
    """Validate that input is from sanitized directory, not raw live artifacts.

    Also validates sanitizer findings JSON for success=true, fatal_count=0.

    Returns (is_valid, error_message, findings_data).
    """
    if not artifact_dir.exists():
        return False, f"Artifact directory does not exist: {artifact_dir}", {}

    if not artifact_dir.is_dir():
        return False, f"Artifact path is not a directory: {artifact_dir}", {}

    # Check for sanitized marker file
    marker = artifact_dir / _SANITIZED_MARKER
    if not marker.exists():
        return False, (
            f"Input directory does not appear to be sanitized artifacts. "
            f"Missing marker file: {_SANITIZED_MARKER}. "
            f"Use lab-artifacts/live-sanitized/ (output of sanitize_live_lab_artifacts.py)"
        ), {}

    # Parse and validate sanitizer findings JSON
    try:
        findings_data = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"Invalid findings JSON: {e}", {}

    # Validate required sanitizer properties
    if not findings_data.get("success", False):
        return False, (
            "Sanitizer findings show success=false. "
            "Cannot build golden case from failed sanitization."
        ), findings_data

    if findings_data.get("fatal_count", 0) > 0:
        return False, (
            f"Sanitizer found {findings_data.get('fatal_count')} fatal issues. "
            "Cannot build golden case from artifacts with unsanitized secrets."
        ), findings_data

    if not findings_data.get("verification_passed", False):
        return False, (
            "Sanitizer findings show verification_passed=false. "
            "Cannot build golden case from artifacts that failed sanitizer verification."
        ), findings_data

    # Warn if input looks like raw live artifacts
    if "lab-artifacts/live" in str(artifact_dir.resolve()):
        if "live-sanitized" not in str(artifact_dir.resolve()):
            return False, (
                "Input path contains 'lab-artifacts/live' but not 'live-sanitized'. "
                "Must use sanitized artifacts directory, not raw live artifacts."
            ), findings_data

    return True, "", findings_data


def validate_required_evidence(artifact_dir: Path, scenario: str) -> tuple[bool, list[str]]:
    """Validate that required evidence files exist.

    Returns (is_valid, missing_files).
    """
    required_files: list[str]

    if scenario == "pod-failure":
        # Required evidence as per ACT requirements
        required_files = [
            # Core evidence
            "incident/pods.txt",
            "incident/events.txt",
            "incident/injected-change.yaml",
            "incident/symptom-watch.json",
            # CNPG state (required per ACT)
            "incident/cnpg-clusters.json",
            # k9b incident detail (required per ACT)
            "incident/k9b-incident-detail.json",
            # Baseline state
            "baseline/pods.txt",
            # Final/recovery state
            "recovery-or-final/pods.txt",
            "recovery-or-final/events.txt",
            # Sanitizer verification (required per ACT)
            "_findings.json",
        ]
    else:
        return False, [f"Unknown scenario: {scenario}"]

    missing = []
    for rel_path in required_files:
        full_path = artifact_dir / rel_path
        if not full_path.exists():
            missing.append(rel_path)

    return len(missing) == 0, missing


def build_case_bundle(
    artifact_dir: Path,
    scenario: str,
    output_dir: Path,
) -> tuple[bool, str]:
    """Build the golden case bundle from sanitized artifacts.

    Returns (success, error_message).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define evidence files to copy based on scenario
    evidence_files: list[tuple[str, str]]  # (source_rel, dest_subdir)

    if scenario == "pod-failure":
        evidence_files = [
            ("incident/pods.txt", "incident"),
            ("incident/events.txt", "incident"),
            ("incident/injected-change.yaml", "incident"),
            ("incident/symptom-watch.json", "incident"),
            ("incident/k9b-incident-detail.json", "incident"),
            ("incident/cnpg-clusters.json", "incident"),
            ("baseline/pods.txt", "baseline"),
            ("recovery-or-final/pods.txt", "recovery-or-final"),
            ("recovery-or-final/events.txt", "recovery-or-final"),
        ]
    else:
        return False, f"Unknown scenario: {scenario}"

    # Copy evidence files
    copied_count = 0
    for source_rel, dest_subdir in evidence_files:
        src = artifact_dir / source_rel
        if src.exists():
            dest = output_dir / dest_subdir / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_count += 1

    # Copy sanitizer findings summary
    findings_src = artifact_dir / _SANITIZED_MARKER
    if findings_src.exists():
        shutil.copy2(findings_src, output_dir / "sanitizer-findings.json")

    # Build the expected evidence files list from evidence_files
    expected_evidence_list = [f[0] for f in evidence_files]

    # Generate manifest
    manifest = {
        "case_id": "pod-failure-readiness-001",
        "case_version": "1.0.0",
        "scenario": scenario,
        "category": "readiness_probe_failure",
        "source_workflow": ".github/workflows/k9b-cnpg-incident-lab-live.yml",
        "source_kind": "representative_fixture",
        "source_note": "Representative offline fixture modeled after the green pod-failure live-lab schema. Not generated from a real workflow artifact yet.",
        "artifact_schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "description": "Pod with intentionally failing readiness probe. Pod is Running but NotReady due to readiness probe failure.",
        "expected_root_cause": "readiness probe failure",
        "expected_category": "readiness_probe_failure",
        "fixture_name": "cnpg-lab-failing-app",
        "fixture_namespace": "cnpg-lab",
        "symptom": "Pod Running but NotReady - readiness probe consistently failing",
        "expected_evidence_files": expected_evidence_list,
        "required_evidence": {
            "cnpg_state": "incident/cnpg-clusters.json",
            "k9b_incident": "incident/k9b-incident-detail.json",
            "sanitizer_verification": "sanitizer-findings.json",
            "symptom_watch": "incident/symptom-watch.json",
        },
        "forbidden_actions": [
            "image_pull_failure",
            "pvc_storage_failure",
            "cnpg_operator_failure",
            "node_scheduling_failure",
            "registry_auth_failure",
            "mutation",
            "remediation",
            "apply",
            "delete",
        ],
        "allowed_read_only_checks": [
            "kubectl describe pod",
            "kubectl get events",
            "kubectl get pod -o yaml",
            "kubectl logs",
            "kubectl top pod",
        ],
        "provenance": {
            "artifacts_hash": None,
            "real_live_artifact_required_for_promotion": True,
            "builder": "scripts/build_diagnosis_golden_case.py",
        },
    }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Generate expected.json with complete schema matching checked-in fixture
    expected = {
        "case_id": manifest["case_id"],
        "schema_version": "1.0.0",
        "root_cause": "readiness probe failure",
        "category": "readiness_probe_failure",
        "confidence_minimum": "medium",
        "evidence_requirements": {
            "pod_state": {
                "phase": "Running",
                "ready_condition": False,
                "required": True,
            },
            "container_state": {
                "running": True,
                "ready": False,
                "required": True,
            },
            "readiness_probe": {
                "failure_evidence": True,
                "description": "readiness probe command returns non-zero exit code",
                "required": True,
            },
            "events": {
                "unhealthy_or_warning": True,
                "required": True,
            },
            "cnpg_state": {
                "required": True,
                "description": "CNPG cluster state showing affected resources",
            },
            "k9b_incident": {
                "required": True,
                "description": "k9b incident detail with symptom classification",
            },
            "sanitizer_verification": {
                "required": True,
                "description": "Sanitizer findings showing success and zero fatal findings",
            },
        },
        "verifier_contract": {
            "must_verify_evidence_refs_exist": True,
            "must_verify_recursive_safety": True,
            "must_verify_next_checks_read_only": True,
            "must_fail_on_forbidden_observed": True,
            "must_fail_on_mutation_observed": True,
        },
        "allowed_uncertainty_phrases": [
            "may be caused by",
            "possibly",
            "likely",
            "appears to be",
            "suggests",
            "consistent with",
        ],
        "forbidden_conclusions": {
            "image_pull_failure": "ImagePullBackOff or ErrImagePull must NOT be cited as primary cause",
            "pvc_storage_failure": "PVC mount or storage issues must NOT be cited as primary cause",
            "cnpg_operator_failure": "CNPG operator issues must NOT be cited as primary cause",
            "node_scheduling_failure": "Scheduling failures must NOT be cited as primary cause",
            "registry_auth_failure": "Registry authentication failures must NOT be cited as primary cause",
            "mutation": "Must NOT propose kubectl apply, kubectl delete, helm upgrade, or any cluster mutation",
        },
        "allowed_read_only_actions": [
            "describe pod",
            "get pod yaml",
            "get events",
            "get logs",
            "get describe",
            "top pod",
            "explain",
        ],
        "expected_read_only_behavior": True,
        "must_not_propose_remediation": True,
        "test_hints": {
            "correct_diagnosis_keywords": [
                "readiness probe",
                "NotReady",
                "readiness",
                "probe failed",
                "probe failure",
            ],
            "wrong_diagnosis_keywords": [
                "ImagePullBackOff",
                "ErrImagePull",
                "PVC",
                "storage",
                "scheduling",
                "registry",
                "operator failure",
            ],
        },
    }

    expected_path = output_dir / "expected.json"
    with open(expected_path, "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=2)

    print("Golden case bundle built successfully:")
    print(f"  Output: {output_dir}")
    print(f"  Evidence files copied: {copied_count}")
    print(f"  Manifest: {manifest_path}")
    print(f"  Expected: {expected_path}")

    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build golden diagnosis case bundle from sanitized live lab artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Build pod-failure golden case from sanitized artifacts
    python scripts/build_diagnosis_golden_case.py \\
        --artifact-dir lab-artifacts/live-sanitized \\
        --scenario pod-failure \\
        --output-dir fixtures/diagnosis-golden-cases/pod-failure-readiness

    # Dry run - show what would be built
    python scripts/build_diagnosis_golden_case.py \\
        --artifact-dir lab-artifacts/live-sanitized \\
        --scenario pod-failure \\
        --output-dir /tmp/test-case \\
        --dry-run
        """,
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Input directory with sanitized live lab artifacts",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        choices=["pod-failure"],
        help="Scenario type",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for golden case bundle",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be built without writing files",
    )

    args = parser.parse_args()

    # Validate sanitized input
    is_valid, error_msg, _findings = validate_sanitized_input(args.artifact_dir)
    if not is_valid:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return 2

    # Validate required evidence
    is_valid, missing = validate_required_evidence(args.artifact_dir, args.scenario)
    if not is_valid:
        print("ERROR: Missing required evidence files:", file=sys.stderr)
        for f in missing:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("DRY RUN: Would build golden case bundle")
        print(f"  Input: {args.artifact_dir}")
        print(f"  Scenario: {args.scenario}")
        print(f"  Output: {args.output_dir}")
        return 0

    # Build the case bundle
    success, error_msg = build_case_bundle(
        args.artifact_dir,
        args.scenario,
        args.output_dir,
    )

    if not success:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
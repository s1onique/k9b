#!/usr/bin/env python3
"""
run_golden_case_diagnosis_via_production_loop.py

Production diagnosis-loop adapter for golden-case bundles.

This script wires a golden-case bundle through the production read-only diagnosis
path, exercising the real production modules rather than the standalone fixture
harness.

Design constraints:
- Fully offline (no kubectl, helm, docker, registry, GitHub API)
- Read-only (no cluster mutation)
- Uses checked-in sanitized golden-case evidence only
- Fails if required evidence is missing
- Fails if privacy/provenance verifiers fail
- Cannot propose mutation/remediation actions

Usage:
    python scripts/run_golden_case_diagnosis_via_production_loop.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/golden-case-production-output

Exit codes:
    0 - Diagnosis completed successfully
    1 - Diagnosis failed (unsafe output, missing evidence, etc.)
    2 - Invalid arguments
    3 - Prerequisite verification failed (privacy, provenance)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# Import validators from separate module
from golden_case_adapter_validators import (
    enforce_safety,
    load_case_bundle,
    validate_required_evidence,
)

from k8s_diag_agent.collect.golden_case_providers import (
    GoldenCaseEvidenceProvider,
    build_deterministic_diagnosis,
)

__all__ = ["main"]


def run_verifier_script(script_path: Path, case_dir: Path) -> tuple[bool, str]:
    """Run a verifier script and return (success, error_message)."""
    try:
        # Detect argument format by script name
        script_name = script_path.name
        if "privacy" in script_name:
            cmd = [sys.executable, str(script_path), str(case_dir)]
        else:
            cmd = [sys.executable, str(script_path), "--case-dir", str(case_dir)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False, f"{script_path.name} failed: {result.stderr or result.stdout}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"{script_path.name} timed out"
    except Exception as e:
        return False, f"{script_path.name} error: {e}"


def format_summary(diagnosis: dict, manifest: dict) -> str:
    """Format diagnosis as human-readable summary."""
    lines = [
        "# Production Diagnosis Adapter Output",
        "",
        f"**Case ID**: {diagnosis.get('case_id', manifest.get('case_id', 'unknown'))}",
        f"**Category**: {diagnosis.get('category', 'unknown')}",
        f"**Root Cause**: {diagnosis.get('root_cause', 'unknown')}",
        f"**Confidence**: {diagnosis.get('confidence', 'unknown')}",
        f"**Diagnosis Engine**: {diagnosis.get('diagnosis_engine', 'unknown')}",
        "",
        "## Description",
        diagnosis.get("description", "No description provided."),
        "",
        "## Safety Status",
        f"- Read-only: {diagnosis.get('read_only', False)}",
        f"- Forbidden actions observed: {len(diagnosis.get('forbidden_actions_observed', []))}",
        f"- Mutation proposals observed: {len(diagnosis.get('mutation_proposals_observed', []))}",
        "",
        "## Evidence References",
    ]

    for ref in diagnosis.get("evidence_refs", []):
        lines.append(f"- {ref}")

    lines.extend(["", "## Next Recommended Checks (Read-Only)"])

    for i, check in enumerate(diagnosis.get("next_checks", []), 1):
        if isinstance(check, dict):
            lines.append(f"{i}. {check.get('description', 'No description')}")
            method = check.get("method", "")
            if method:
                lines.append(f"   Method: `{method}`")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Production diagnosis-loop adapter for golden-case bundles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run production adapter on pod-failure golden case
    python scripts/run_golden_case_diagnosis_via_production_loop.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/golden-case-production-output

    # Skip prerequisite verifiers (for debugging)
    python scripts/run_golden_case_diagnosis_via_production_loop.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/output \\
        --skip-prerequisites

Exit codes:
    0 - Diagnosis completed successfully
    1 - Diagnosis failed (unsafe output, missing evidence, etc.)
    2 - Invalid arguments
    3 - Prerequisite verification failed (privacy, provenance)
        """,
    )
    parser.add_argument("--case-dir", type=Path, required=True,
                        help="Directory containing golden case bundle")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for diagnosis results")
    parser.add_argument("--skip-prerequisites", action="store_true",
                        help="Skip privacy and provenance verification (for debugging only)")

    args = parser.parse_args(argv)

    # Validate case directory exists
    if not args.case_dir.exists():
        print(f"ERROR: Case directory does not exist: {args.case_dir}", file=sys.stderr)
        return 2
    if not args.case_dir.is_dir():
        print(f"ERROR: Case path is not a directory: {args.case_dir}", file=sys.stderr)
        return 2

    # Load case bundle
    try:
        manifest, expected = load_case_bundle(args.case_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Validate required evidence
    missing_evidence = validate_required_evidence(args.case_dir, manifest)
    if missing_evidence:
        print("ERROR: Missing required evidence files:", file=sys.stderr)
        for path in missing_evidence:
            print(f"  - {path}", file=sys.stderr)
        return 1

    # Run prerequisite verifications (unless skipped)
    if not args.skip_prerequisites:
        scripts_dir = REPO_ROOT / "scripts"
        privacy_script = scripts_dir / "verify_diagnosis_golden_case_privacy.py"
        privacy_valid, privacy_error = run_verifier_script(privacy_script, args.case_dir)
        if not privacy_valid:
            print(f"ERROR: Privacy verification failed: {privacy_error}", file=sys.stderr)
            return 3

        provenance_script = scripts_dir / "verify_provenance_golden_case.py"
        provenance_valid, provenance_error = run_verifier_script(provenance_script, args.case_dir)
        if not provenance_valid:
            print(f"ERROR: Provenance verification failed: {provenance_error}", file=sys.stderr)
            return 3

    # Create evidence provider and build diagnosis
    evidence_provider = GoldenCaseEvidenceProvider(args.case_dir)
    print("Building diagnosis via production adapter...", file=sys.stderr)
    diagnosis = build_deterministic_diagnosis(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    # Add metadata
    diagnosis["timestamp"] = datetime.now(UTC).isoformat()
    diagnosis["case_id"] = manifest.get("case_id", "unknown")
    diagnosis["diagnosis_engine"] = "production-golden-case-adapter"

    # Enforce safety constraints
    is_safe, safety_errors = enforce_safety(diagnosis)
    if not is_safe:
        print("ERROR: Safety enforcement failed:", file=sys.stderr)
        for error in safety_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    # Write outputs
    args.output_dir.mkdir(parents=True, exist_ok=True)
    diagnosis_path = args.output_dir / "diagnosis.json"
    with open(diagnosis_path, "w", encoding="utf-8") as f:
        import json
        json.dump(diagnosis, f, indent=2)

    summary = format_summary(diagnosis, manifest)
    summary_path = args.output_dir / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    # Print summary
    print("Production diagnosis completed:")
    print(f"  Case: {diagnosis.get('case_id')}")
    print(f"  Category: {diagnosis.get('category')}")
    print(f"  Root Cause: {diagnosis.get('root_cause')}")
    print(f"  Confidence: {diagnosis.get('confidence')}")
    print(f"  Diagnosis Engine: {diagnosis.get('diagnosis_engine')}")
    print(f"  Evidence Refs: {len(diagnosis.get('evidence_refs') or [])}")  # type: ignore[arg-type]
    print(f"  Next Checks: {len(diagnosis.get('next_checks') or [])}")  # type: ignore[arg-type]
    print("  Safety: PASS")
    print(f"  Output: {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

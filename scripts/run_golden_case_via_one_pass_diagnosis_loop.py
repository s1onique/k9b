#!/usr/bin/env python3
"""
run_golden_case_via_one_pass_diagnosis_loop.py

CLI adapter that wires golden-case bundle through the production one-pass
diagnosis/read-only-check machinery using golden-case fake handlers.

Usage:
    python scripts/run_golden_case_via_one_pass_diagnosis_loop.py \\
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
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    build_golden_case_case_file,
    enforce_safety,
    format_diagnosis_summary,
    run_production_diagnosis_loop,
)

__all__ = ["main"]


def run_verifier_script(script_path: Path, case_dir: Path) -> tuple[bool, str]:
    """Run a verifier script and return (success, error_message)."""
    try:
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


def load_case_bundle(case_dir: Path) -> tuple[dict, dict]:
    """Load and validate golden-case bundle."""
    manifest_path = case_dir / "manifest.json"
    expected_path = case_dir / "expected.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not expected_path.exists():
        raise FileNotFoundError(f"Expected not found: {expected_path}")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    return manifest, expected


def validate_required_evidence(case_dir: Path, manifest: dict) -> list[str]:
    """Validate that all required evidence files exist."""
    missing: list[str] = []
    required_files = manifest.get("expected_evidence_files", [])

    if not required_files:
        required_files = list(manifest.get("required_evidence", {}).values())

    for rel_path in required_files:
        file_path = case_dir / rel_path
        if not file_path.exists():
            missing.append(rel_path)

    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Production one-pass diagnosis loop adapter for golden-case bundles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/run_golden_case_via_one_pass_diagnosis_loop.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/golden-case-production-output
        """,
    )
    parser.add_argument("--case-dir", type=Path, required=True,
                        help="Directory containing golden case bundle")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for diagnosis results")
    parser.add_argument("--skip-prerequisites", action="store_true",
                        help="Skip privacy and provenance verification (debug only)")

    args = parser.parse_args(argv)

    if not args.case_dir.exists():
        print(f"ERROR: Case directory does not exist: {args.case_dir}", file=sys.stderr)
        return 2
    if not args.case_dir.is_dir():
        print(f"ERROR: Case path is not a directory: {args.case_dir}", file=sys.stderr)
        return 2

    try:
        manifest, expected = load_case_bundle(args.case_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    missing_evidence = validate_required_evidence(args.case_dir, manifest)
    if missing_evidence:
        print("ERROR: Missing required evidence files:", file=sys.stderr)
        for path in missing_evidence:
            print(f"  - {path}", file=sys.stderr)
        return 1

    # Fail-closed: prerequisite verifiers must exist and pass
    scripts_dir = REPO_ROOT / "scripts"

    privacy_script = scripts_dir / "verify_diagnosis_golden_case_privacy.py"
    if not privacy_script.exists():
        print("ERROR: Privacy verifier script not found: verify_diagnosis_golden_case_privacy.py", file=sys.stderr)
        return 3

    if not args.skip_prerequisites:
        privacy_valid, privacy_error = run_verifier_script(privacy_script, args.case_dir)
        if not privacy_valid:
            print(f"ERROR: Privacy verification failed: {privacy_error}", file=sys.stderr)
            return 3

    provenance_script = scripts_dir / "verify_provenance_golden_case.py"
    if not provenance_script.exists():
        print("ERROR: Provenance verifier script not found: verify_provenance_golden_case.py", file=sys.stderr)
        return 3

    if not args.skip_prerequisites:
        provenance_valid, provenance_error = run_verifier_script(provenance_script, args.case_dir)
        if not provenance_valid:
            print(f"ERROR: Provenance verification failed: {provenance_error}", file=sys.stderr)
            return 3

    evidence_provider = GoldenCaseEvidenceProvider(args.case_dir)

    print("Building production case-file from golden-case bundle...", file=sys.stderr)
    case_file = build_golden_case_case_file(
        case_dir=args.case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

    print("Running production one-pass diagnosis loop...", file=sys.stderr)
    diagnosis = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=args.output_dir,
    )

    diagnosis["timestamp"] = datetime.now(UTC).isoformat()

    is_safe, safety_errors = enforce_safety(diagnosis)
    if not is_safe:
        print("ERROR: Safety enforcement failed:", file=sys.stderr)
        for error in safety_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    diagnosis_path = args.output_dir / "diagnosis.json"
    with open(diagnosis_path, "w", encoding="utf-8") as f:
        json.dump(diagnosis, f, indent=2)

    summary = format_diagnosis_summary(diagnosis, manifest)
    summary_path = args.output_dir / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print("Production one-pass diagnosis loop completed:")
    print(f"  Case: {diagnosis.get('case_id')}")
    print(f"  Category: {diagnosis.get('category')}")
    print(f"  Root Cause: {diagnosis.get('root_cause')}")
    print(f"  Confidence: {diagnosis.get('confidence')}")
    print(f"  Diagnosis Engine: {diagnosis.get('diagnosis_engine')}")
    print(f"  Loop Decision: {diagnosis.get('loop_decision')}")
    print(f"  Checks Run: {diagnosis.get('checks_run')}")
    print(f"  Evidence Refs: {len(diagnosis.get('evidence_refs') or [])}")
    print(f"  Next Checks: {len(diagnosis.get('next_checks') or [])}")
    print("  Safety: PASS")
    print(f"  Output: {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
verify_k3s_cnpg_incident_lab_artifact.py

Verifies the artifact directory produced by the K3s CNPG incident lab.
This script validates:
- lab-result.json exists and is well-formed
- Required phase artifact files are present
- Baseline was captured
- Incident phase was captured
- k9b incident evidence was captured (if incident_detected=true)
- No actual secrets appear in sanitized artifacts
- incident_detected=true is consistent with artifacts
- namespace-mode fields are present when cluster_mode=existing

The verifier operates on the SANITIZED artifact directory, not raw artifacts.
Raw artifacts are kept local during the job; only sanitized artifacts are verified and uploaded.

Exit codes:
  0 - All checks passed
  1 - Verification failed (with diagnostic output)
  2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import from modules
from sanitize_live_lab_artifacts import FindingKind
from verify_k3s_cnpg_incident_lab_artifact_contract import (
    VerificationContext,
)
from verify_k3s_cnpg_incident_lab_artifact_report import (
    format_findings_report,
)
from verify_k3s_cnpg_incident_lab_artifact_validators import (
    verify_artifact_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify K3s CNPG incident lab artifacts (sanitized).",
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Path to the sanitized lab artifact directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--sanitize-only",
        action="store_true",
        help="Only run sanitization (for CI workflow integration)",
    )
    parser.add_argument(
        "--raw-artifact-dir",
        type=str,
        help="Path to raw artifact directory for sanitization (used with --sanitize-only)",
    )

    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).resolve()

    # If sanitize-only mode, run sanitization first
    if args.sanitize_only:
        if not args.raw_artifact_dir:
            print("ERROR: --raw-artifact-dir required with --sanitize-only", file=sys.stderr)
            return 2

        raw_dir = Path(args.raw_artifact_dir).resolve()
        print(f"Sanitizing raw artifacts: {raw_dir}")
        print(f"Output directory: {artifact_dir}")
        print()

        # Import and run sanitization
        import sanitize_live_lab_artifacts
        success, findings, results = sanitize_live_lab_artifacts.sanitize_directory(raw_dir, artifact_dir)

        # Write findings for downstream use FIRST (before any exit)
        findings_path = artifact_dir / "_findings.json"
        fatal_count = sum(1 for f in findings if f.kind == FindingKind.FATAL)
        findings_data = {
            "scan_completed": True,
            "success": success,
            "upload_safe": fatal_count == 0 and success,
            "total_files": len(results),
            "succeeded": sum(1 for r in results if r.success),
            "fatal_count": fatal_count,
            "findings": [
                {"kind": f.kind, "message": f.message, "file": f.file, "context": f.context}
                for f in findings
            ],
        }
        findings_path.write_text(json.dumps(findings_data, indent=2))
        print(f"\nFindings written to: {findings_path}")

        # Check for fatal findings - these MUST fail the gate
        fatal_findings = [f for f in findings if f.kind == FindingKind.FATAL]
        if fatal_findings:
            print()
            print("=" * 50)
            print("FATAL: Artifact sanitization detected actual secrets!")
            print("=" * 50)
            print()
            for f in fatal_findings[:10]:
                print(f"  • {f.file}: {f.message}")
            if len(fatal_findings) > 10:
                print(f"  ... and {len(fatal_findings) - 10} more")
            print()
            print("Raw artifacts remain local; sanitized artifacts not uploaded.")
            return 1

        # Check for sanitization errors (non-success but no fatal findings)
        # FAIL CLOSED: file errors must fail the gate, not silently continue
        if not success:
            print()
            print("FATAL: Sanitization had file errors!")
            file_errors = [r for r in results if not r.success and r.error]
            for r in file_errors[:10]:
                print(f"  {r.input_path}: {r.error}")
            if len(file_errors) > 10:
                print(f"  ... and {len(file_errors) - 10} more file errors")
            print("Raw artifacts remain local; sanitized artifacts not uploaded.")
            findings_data["findings"] = [
                {"kind": "fatal", "message": f"File error: {r.error}", "file": str(r.input_path), "context": None}
                for r in file_errors
            ]
            findings_path.write_text(json.dumps(findings_data, indent=2))
            return 1

        print()
        print(sanitize_live_lab_artifacts.format_findings_summary(findings))

    print(f"\nVerifying artifacts in: {artifact_dir}")
    print()

    if not artifact_dir.exists():
        print(f"ERROR: artifact directory does not exist: {artifact_dir}")
        return 1

    if not artifact_dir.is_dir():
        print(f"ERROR: artifact path is not a directory: {artifact_dir}")
        return 1

    ctx = VerificationContext(artifact_dir=artifact_dir, verbose=args.verbose)
    passed = verify_artifact_dir(ctx)

    # Print findings report
    findings_report = format_findings_report(ctx)
    if findings_report:
        print(findings_report)

    # Update _findings.json with verifier findings
    findings_path = artifact_dir / "_findings.json"
    verifier_fatal_count = sum(1 for f in ctx.findings if f.kind == FindingKind.FATAL)
    
    if findings_path.exists():
        try:
            findings_data = json.loads(findings_path.read_text())
        except (json.JSONDecodeError, OSError):
            findings_data = {}
    else:
        findings_data = {}
    
    # Merge verifier findings into the combined findings
    sanitizer_findings = findings_data.get("findings", [])
    verifier_findings = [
        {"kind": f.kind, "message": f.message, "file": f.file, "context": f.context}
        for f in ctx.findings
    ]
    
    # Combined fatal count (sanitizer + verifier)
    sanitizer_fatal_count = findings_data.get("fatal_count", 0)
    combined_fatal_count = sanitizer_fatal_count + verifier_fatal_count
    
    # Update findings data with combined results
    findings_data.update({
        "verifier_passed": passed,
        "verifier_errors": list(ctx.errors),
        "combined_fatal_count": combined_fatal_count,
        "upload_safe": combined_fatal_count == 0 and passed,
        "sanitizer_findings": sanitizer_findings,
        "verifier_findings": verifier_findings,
        "findings": sanitizer_findings + verifier_findings,  # Combined for backward compatibility
    })
    findings_path.write_text(json.dumps(findings_data, indent=2))

    if passed:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: PASSED")
        print("=" * 50)
        print()

        # Summary of findings
        warning_count = sum(1 for f in ctx.findings if f.kind == FindingKind.WARNING)
        info_count = sum(1 for f in ctx.findings if f.kind == FindingKind.INFO)

        if ctx.findings:
            print(f"Findings: {verifier_fatal_count} fatal, {warning_count} warnings, {info_count} info")
        else:
            print("No findings.")
        
        print(f"\nCombined findings written to: {findings_path}")

        return 0
    else:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: FAILED")
        print("=" * 50)
        print()

        # Print errors
        if ctx.errors:
            print("Errors:")
            for i, error in enumerate(ctx.errors, 1):
                print(f"  {i}. {error}")

        # Print findings report
        if findings_report:
            print(findings_report)

        print(f"\nCombined findings written to: {findings_path}")

        return 1


if __name__ == "__main__":
    sys.exit(main())

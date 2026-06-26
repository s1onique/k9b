#!/usr/bin/env python3
"""
sanitize_live_lab_artifacts.py

Structured sanitizer for live lab artifacts that:
- Parses JSON/YAML when possible and redacts actual sensitive values
- Preserves safe Kubernetes metadata (field names, resource names, RBAC)
- Writes sanitized copies to a separate directory for verification and upload

Usage:
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized

Exit codes:
    0 - All artifacts sanitized successfully
    1 - Sanitization failed
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Import from split modules
from sanitize_live_lab_artifacts_contract import (
    REDACTION_PLACEHOLDER,
    Finding,
    FindingKind,
    SanitizationResult,
)
from sanitize_live_lab_artifacts_report import (
    format_findings_summary,
    print_summary,
    print_verbose_results,
    write_findings_json,
)
from sanitize_live_lab_artifacts_sanitization import (
    sanitize_directory,
)

# Re-export for backward compatibility
__all__ = [
    "Finding",
    "FindingKind",
    "REDACTION_PLACEHOLDER",
    "SanitizationResult",
    "format_findings_summary",
    "print_summary",
    "print_verbose_results",
    "sanitize_directory",
    "write_findings_json",
]


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize live lab artifacts for safe verification and upload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sanitize a live lab artifact directory
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized

    # With verbose output
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized --verbose

    # Dry run - show what would be sanitized
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized --dry-run
        """,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input artifact directory to sanitize",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for sanitized artifacts",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sanitized without writing files",
    )

    args = parser.parse_args()

    # Validate input
    if not args.input.exists():
        print(f"ERROR: Input directory does not exist: {args.input}", file=sys.stderr)
        return 2

    if not args.input.is_dir():
        print(f"ERROR: Input path is not a directory: {args.input}", file=sys.stderr)
        return 2

    # Dry run mode
    if args.dry_run:
        print(f"DRY RUN: Would sanitize {args.input} -> {args.output}")
        for input_path in args.input.rglob("*"):
            if input_path.is_file():
                rel_path = input_path.relative_to(args.input)
                print(f"  - {rel_path}")
        return 0

    # Sanitize
    print(f"Sanitizing artifacts: {args.input}")
    print(f"Output directory: {args.output}")
    print()

    success, findings, results = sanitize_directory(args.input, args.output)

    # Print verbose output
    if args.verbose:
        print_verbose_results(results, args.input)

    # Print findings summary
    print()
    print("Findings:")
    print(format_findings_summary(findings))

    # Summary
    print()
    total, succeeded, fatal_count = print_summary(results, findings, success)

    # Write findings to JSON for downstream consumption
    findings_path = write_findings_json(args.output, success, findings, results)
    print(f"\nFindings written to: {findings_path}")

    if fatal_count > 0:
        print("\nFATAL: Actual credential values detected in artifacts!")
        return 1

    if not success:
        return 1

    # Fail on warnings (Secret.data, stringData, etc. need manual review)
    warning_count = sum(1 for f in findings if f.kind == "warning")
    if warning_count > 0:
        print("\nWARNING: Sensitive fields detected and redacted.")
        return 1

    print("\nSanitization complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

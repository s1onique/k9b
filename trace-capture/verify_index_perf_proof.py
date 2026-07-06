"""Index performance proof verification script.

This script verifies that the content-index read path performance proof
artifacts meet the required criteria for ACT-K9B-API-INDEX-PERF-PROOF01.

Usage:
    python verify_index_perf_proof.py \
        --artifact-dir trace-capture/index-perf-proof \
        --fail

Exit codes:
    0 - All checks passed
    1 - One or more checks failed (only with --fail)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verify_index_perf_proof_contract import VerificationResult
from verify_index_perf_proof_logic import verify_artifacts

# =============================================================================
# CLI Interface
# =============================================================================


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verify index performance proof artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify with default paths:
  python verify_index_perf_proof.py

  # With custom artifact directory:
  python verify_index_perf_proof.py --artifact-dir trace-capture/index-perf-proof

  # Verbose output:
  python verify_index_perf_proof.py --artifact-dir trace-capture/index-perf-proof -v

  # Fail on any issue:
  python verify_index_perf_proof.py --artifact-dir trace-capture/index-perf-proof --fail
        """,
    )

    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("trace-capture/index-perf-proof"),
        help="Directory containing index perf proof artifacts",
    )
    parser.add_argument(
        "--index-db",
        type=Path,
        default=Path("/tmp/k9b-content-index.sqlite"),
        help="Path to the content index database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write summary JSON to file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Exit with non-zero code if verification fails",
    )

    args = parser.parse_args()

    # Run verification
    print("=" * 70)
    print("Index Performance Proof Verification")
    print("=" * 70)
    print(f"Artifact directory: {args.artifact_dir}")
    print(f"Index DB: {args.index_db}")
    print()

    summary = verify_artifacts(args.artifact_dir, args.index_db, args.verbose)
    verification = VerificationResult(**summary.verification)

    # Print results
    print("Results:")
    print(f"  Index DB valid: {summary.index_db_valid}")
    print(f"  Disabled run success: {verification.disabled_run_success}")
    print(f"  Enabled run success: {verification.enabled_run_success}")
    print(f"  Content index spans emitted: {verification.enabled_emits_content_index_spans}")
    print(f"  No fallback for indexed endpoints: {verification.fallback_spans_for_indexed_endpoints}")
    print(f"  API shape compatible: {summary.api_shape_compatible}")
    print(f"  Privacy check passed: {summary.privacy_check_passed}")

    # Print latency deltas if available
    if summary.latency_delta:
        print()
        print("Latency Deltas (p50/p90/p99):")
        for route, delta in summary.latency_delta.items():
            p50_d = delta.get("p50_delta_ms", 0)
            p50_p = delta.get("p50_improvement_percent", 0)
            p90_d = delta.get("p90_delta_ms", 0)
            p90_p = delta.get("p90_improvement_percent", 0)
            print(f"  {route}:")
            print(f"    p50: {p50_d:+.2f}ms ({p50_p:+.2f}%)")
            print(f"    p90: {p90_d:+.2f}ms ({p90_p:+.2f}%)")

    # Print errors and warnings
    if verification.errors:
        print()
        print("Errors:")
        for error in verification.errors:
            print(f"  - {error}")

    if verification.warnings:
        print()
        print("Warnings:")
        for warning in verification.warnings:
            print(f"  - {warning}")

    # Write summary if output path specified
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary.to_dict(), indent=2))
        print()
        print(f"Summary written to: {args.output}")

    # Determine pass/fail
    all_passed = (
        summary.index_db_valid
        and verification.disabled_run_success
        and verification.enabled_run_success
        and verification.enabled_emits_content_index_spans
        and verification.fallback_spans_for_indexed_endpoints
        and summary.api_shape_compatible
        and summary.privacy_check_passed
    )

    print()
    print("=" * 70)
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")
    print("=" * 70)

    # Write index-perf-summary.json to artifact directory
    summary_path = args.artifact_dir / "index-perf-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary.to_dict(), indent=2))
    print(f"Summary saved to: {summary_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

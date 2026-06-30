#!/usr/bin/env python3
"""CI-enforced live-lab contract verifier for unschedulable-shipping.

This module provides the CLI façade for live-lab contract verification.
Implementation is delegated to the `scripts.otel_lab_contracts` package.

Usage:
    python -m scripts.k9b_otel_demo_lab_contract_verify \
        --artifact-dir lab-artifacts/otel-demo \
        --scenario unschedulable-shipping \
        --require-lab-passed \
        --otel-traces auto

Exit codes:
    0 - All contracts passed
    1 - Contract failure

OTel trace behavior:
- auto: Inspect traces if present, skip if missing
- require: Fail if traces are missing
- skip: Do not inspect traces
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Re-export all public functions from the package for backward compatibility
from scripts.otel_lab_contracts import (
    ContractCheck,
    OtelTracesMode,
    VerificationReport,
    format_report,
    scan_for_sensitive_payloads,
    verify_lab_result,
    verify_live_lab_contracts,
    verify_otel_traces,
    verify_p3c_discovery,
    verify_p4c_diagnosis,
    verify_runtime_loop_passes,
)

__all__ = [
    "ContractCheck",
    "OtelTracesMode",
    "VerificationReport",
    "format_report",
    "scan_for_sensitive_payloads",
    "verify_lab_result",
    "verify_live_lab_contracts",
    "verify_otel_traces",
    "verify_p3c_discovery",
    "verify_p4c_diagnosis",
    "verify_runtime_loop_passes",
]


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Verify live-lab contracts for unschedulable-shipping scenario")
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Root artifact directory (e.g., lab-artifacts/otel-demo)",
    )
    parser.add_argument(
        "--scenario",
        default="unschedulable-shipping",
        help="Incident scenario name (default: unschedulable-shipping)",
    )
    parser.add_argument(
        "--require-lab-passed",
        action="store_true",
        help="Require lab-result.json to indicate success",
    )
    parser.add_argument(
        "--otel-traces",
        choices=["auto", "require", "skip"],
        default="auto",
        help="OTel trace verification mode (default: auto)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)

    if not artifact_dir.exists():
        print(f"ERROR: Artifact directory does not exist: {artifact_dir}", file=sys.stderr)
        return 1

    otel_mode = OtelTracesMode(args.otel_traces)

    report = verify_live_lab_contracts(
        artifact_dir=artifact_dir,
        scenario=args.scenario,
        require_lab_passed=args.require_lab_passed,
        otel_traces_mode=otel_mode,
    )

    output = format_report(report, args.json)
    print(output)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

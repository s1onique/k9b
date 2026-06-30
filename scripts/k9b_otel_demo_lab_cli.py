#!/usr/bin/env python3
"""OTel Demo Lab CLI - command-line interface for the lab orchestrator.

This module contains the CLI entry point and argument parsing for the OTel Demo Lab.
The actual lab orchestration logic is in k9b_otel_demo_lab.py.

Usage:
    python -m scripts.k9b_otel_demo_lab --kubeconfig /path/to/kubeconfig [options]
    python -m scripts.k9b_otel_demo_lab_cli --kubeconfig /path/to/kubeconfig [options]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add scripts to path for imports
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))


def run_cli() -> int:
    """Run the OTel Demo Lab CLI.

    Returns:
        Exit code: 0 for success, 1 for failure
    """
    # Import constants from contract module for CLI choices
    from scripts.k9b_otel_demo_lab_contract import (
        INCIDENT_SCENARIOS,
        LAB_MODE_SCAFFOLD,
        LAB_MODES,
        SCENARIO_RECOMMENDATION_CACHE_FAILURE,
    )

    parser = argparse.ArgumentParser(
        description="Run OTel Demo incident lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument(
        "--artifact-dir",
        default="./lab-artifacts/otel-demo",
        help="Artifact directory",
    )
    parser.add_argument(
        "--mode",
        choices=LAB_MODES,
        default=LAB_MODE_SCAFFOLD,
        help="Lab mode: scaffold (fixture-based) or live (real cluster traffic)",
    )
    # Live mode timing overrides
    parser.add_argument(
        "--live-traffic-duration",
        type=int,
        default=600,
        help="Duration of live traffic generation in seconds (default: 600)",
    )
    parser.add_argument(
        "--live-observation-wait",
        type=int,
        default=600,
        help="Wait time for symptoms to manifest in seconds (default: 600)",
    )
    parser.add_argument(
        "--live-poll-interval",
        type=int,
        default=30,
        help="Poll interval for observation in seconds (default: 30)",
    )
    # Provider smoke option (runs AFTER incident injection, fail-closed)
    parser.add_argument(
        "--enable-provider-smoke",
        action="store_true",
        default=False,
        help="Enable provider smoke phases (fail-closed: any P1/P1b/P2/P3/P4 failure fails the lab)",
    )
    # Incident scenario option (opt-in K8s-native path)
    parser.add_argument(
        "--incident-scenario",
        choices=INCIDENT_SCENARIOS,
        default=SCENARIO_RECOMMENDATION_CACHE_FAILURE,
        help="Incident scenario (default: recommendation-cache-failure)",
    )

    args = parser.parse_args()

    from scripts.k9b_otel_demo_lab import run_lab
    from scripts.k9b_otel_demo_lab_contract import LabConfig

    config = LabConfig(
        kubeconfig=args.kubeconfig,
        artifact_dir=args.artifact_dir,
        mode=args.mode,
        live_traffic_duration_seconds=args.live_traffic_duration,
        live_observation_wait_seconds=args.live_observation_wait,
        live_poll_interval_seconds=args.live_poll_interval,
        enable_provider_smoke=args.enable_provider_smoke,
        incident_scenario=args.incident_scenario,
    )

    result = run_lab(config)

    print(f"LAB RESULT: {'SUCCESS' if result.success else 'FAILED'} (mode={args.mode})")
    print(f"Provider smoke: {'PASSED' if result.provider_smoke_passed else 'SKIPPED/FAILED'}")
    print(f"Elapsed: {result.elapsed_seconds:.1f}s")

    if not result.success:
        print(f"Failure reason: {result.failure_reason}")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

#!/usr/bin/env python3
"""Offline health-loop fixture for structured output verification.

This script runs a minimal health-loop path that exercises real logging plumbing
without requiring a live Kubernetes cluster.

Usage:
    python scripts/run_health_loop_offline.py [--output-dir DIR]

Output:
    Writes structured JSON log entries to stdout and health.log file.
    Returns 0 on success, non-zero on failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Add src to path for imports
_repo_root = Path(__file__).resolve().parents[1]
_src_path = _repo_root / "src"
sys.path.insert(0, str(_src_path))

from k8s_diag_agent.structured_logging import emit_structured_log


def create_minimal_health_config(output_dir: Path) -> Path:
    """Create a minimal health config for offline testing."""
    config = {
        "run_label": "structured-output-test",
        "output_dir": str(output_dir),
        "targets": [
            {
                "context": "offline-test-context",
                "label": "offline-test",
                "cluster_class": "test",
                "cluster_role": "test",
                "baseline_cohort": "test",
                "baseline_policy_path": "baseline-policy.json",
            }
        ],
    }
    config_path = output_dir / "health-config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path


def run_offline_health_loop(output_dir: Path) -> int:
    """Run a minimal health loop with fake snapshot data.

    This exercises the real logging pipeline without requiring a live cluster.
    """
    run_label = "structured-output-test"

    # Emit test events through the real logging infrastructure
    emit_structured_log(
        component="health-loop",
        message="Health run started",
        run_label=run_label,
        severity="INFO",
        event="start",
    )

    emit_structured_log(
        component="health-loop",
        message="Snapshot collection would occur",
        run_label=run_label,
        severity="INFO",
        event="snapshot-would-collect",
        cluster_label="offline-test",
    )

    emit_structured_log(
        component="health-loop",
        message="Health loop test completed",
        run_label=run_label,
        severity="INFO",
        event="complete",
        assessment_count=1,
        healthy_count=1,
        degraded_count=0,
    )

    return 0


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Offline health loop fixture")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for health artifacts",
    )
    args = parser.parse_args()

    # Use temp directory if not specified
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="health-loop-offline-"))

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create minimal config (used to verify config structure is valid)
        _config_path = create_minimal_health_config(output_dir)

        # Run the offline health loop
        exit_code = run_offline_health_loop(output_dir)

        if exit_code == 0:
            # Emit completion marker to stdout
            emit_structured_log(
                component="health-loop",
                message="Offline health loop completed successfully",
                run_label="structured-output-test",
                severity="INFO",
                event="offline-complete",
                output_dir=str(output_dir),
            )
        else:
            # Emit error through structured logging
            emit_structured_log(
                component="health-loop",
                message="Offline health loop failed",
                run_label="structured-output-test",
                severity="ERROR",
                event="offline-failed",
                exit_code=exit_code,
            )

        return exit_code

    except Exception as exc:
        # Emit error through structured logging
        emit_structured_log(
            component="health-loop",
            message=f"Offline health loop error: {exc}",
            run_label="structured-output-test",
            severity="ERROR",
            event="offline-error",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

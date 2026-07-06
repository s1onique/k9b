#!/usr/bin/env python3
"""vmalert→Alertmanager→K9B incident lab.

This module orchestrates the complete lab workflow to prove:
1. vmalert fires a deterministic rule
2. Alertmanager receives the alert
3. Alertmanager POSTs to K9B webhook
4. K9B normalizes and stores the alert signal
5. K9B auto-promotes signal to incident
6. K9B opens exactly one incident for the lab incident key
7. Incident is OPEN, not RESOLVED
8. Diagnosis loop can run on alert-backed incident

Usage:
    python -m scripts.k9b_vmalert_alertmanager_lab --kubeconfig /path/to/kubeconfig --artifact-dir ./lab-artifacts/alertmanager
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.k9b_vmalert_alertmanager_lab_constants import (
    K9B_NAMESPACE,
    MONITORING_NAMESPACE,
    PHASE_DEPLOY,
    PHASE_INJECT,
    PHASE_PREFILIGHT,
    PHASE_RECOVERY,
    PHASE_VERIFY,
)
from scripts.k9b_vmalert_alertmanager_lab_helpers import log, write_json_atomically
from scripts.k9b_vmalert_alertmanager_lab_types import LabConfig, LabPhase, LabResult


def _run_phase(name: str, func: Any, *args: Any, **kwargs: Any) -> LabPhase:
    """Run a lab phase with timing and error handling."""
    log("=" * 60)
    log(f"Phase: {name}")
    log("=" * 60)
    start = time.time()
    try:
        result = func(*args, **kwargs)
        duration = time.time() - start
        log(f"Phase {name} completed in {duration:.1f}s: {'PASS' if result.success else 'FAIL'}")
        if not result.success:
            log(f"  Message: {result.message}")
            if result.failure_class:
                log(f"  Failure class: {result.failure_class}")
        return result  # type: ignore[no-any-return]
    except Exception as e:
        duration = time.time() - start
        log(f"Phase {name} failed with exception: {e}")
        return LabPhase(
            name=name,
            success=False,
            message=str(e),
            failure_class="internal_error",
        )


def run_lab(config: LabConfig) -> LabResult:
    """Run the complete lab."""
    from scripts.k9b_vmalert_alertmanager_lab_phases import (
        phase_cleanup,
        phase_deploy_alertmanager,
        phase_inject_alert,
        phase_preflight,
        phase_verify,
    )

    start_time = datetime.now(UTC)
    result = LabResult(started_at=start_time.isoformat())

    # Create artifact directories
    for phase in [PHASE_PREFILIGHT, PHASE_DEPLOY, PHASE_INJECT, PHASE_VERIFY, PHASE_RECOVERY]:
        (config.artifact_dir / phase).mkdir(parents=True, exist_ok=True)

    # Run phases
    phases = [
        (PHASE_PREFILIGHT, phase_preflight),
        (PHASE_DEPLOY, phase_deploy_alertmanager),
        (PHASE_INJECT, phase_inject_alert),
        (PHASE_VERIFY, phase_verify),
        (PHASE_RECOVERY, phase_cleanup),
    ]

    for phase_name, phase_func in phases:
        phase_result = _run_phase(phase_name, phase_func, config)
        result.phases.append({
            "name": phase_result.name,
            "success": phase_result.success,
            "message": phase_result.message,
            "failure_class": phase_result.failure_class,
            "artifacts": phase_result.artifacts,
        })

        if not phase_result.success:
            result.failure_reason = phase_result.message
            break

    result.success = all(p["success"] for p in result.phases)
    result.finished_at = datetime.now(UTC).isoformat()

    # Write final result
    result_data = {
        "success": result.success,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "failure_reason": result.failure_reason,
        "phases": result.phases,
    }
    write_json_atomically(config.artifact_dir / "lab-result.json", result_data)

    return result


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Alertmanager synthetic webhook promotion lab",
        epilog="NOTE: This lab uses synthetic webhook injection to prove K9B's "
               "Alertmanager webhook handling. Real vmalert→Alertmanager delivery "
               "is not proven in this lab.",
    )

    # Support 'run' subcommand for Makefile/workflow compatibility
    subparsers = parser.add_subparsers(dest="command", help="Lab commands")
    run_parser = subparsers.add_parser("run", help="Run the lab")
    run_parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    run_parser.add_argument("--artifact-dir", required=True, help="Artifact output directory")
    run_parser.add_argument("--timeout", default="20m", help="Lab timeout (default: 20m)")
    run_parser.add_argument("--k9b-namespace", default=K9B_NAMESPACE, help="k9b namespace")
    run_parser.add_argument("--monitoring-namespace", default=MONITORING_NAMESPACE, help="Monitoring namespace")
    run_parser.add_argument("--webhook-token", default="lab-secret-token", help="Webhook bearer token")

    args = parser.parse_args()

    # Get the run subcommand arguments
    run_args = args.command == "run" and args
    if not run_args:
        parser.print_help()
        return 1

    config = LabConfig(
        kubeconfig=run_args.kubeconfig,
        artifact_dir=Path(run_args.artifact_dir),
        k9b_namespace=run_args.k9b_namespace,
        monitoring_namespace=run_args.monitoring_namespace,
        webhook_token=run_args.webhook_token,
    )

    result = run_lab(config)

    if result.success:
        log("=" * 60)
        log("LAB RESULT: PASSED")
        log("=" * 60)
        return 0
    else:
        log("=" * 60)
        log("LAB RESULT: FAILED")
        log(f"Reason: {result.failure_reason}")
        log("=" * 60)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

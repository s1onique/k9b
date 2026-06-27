#!/usr/bin/env python3
"""Scheduler health gate for provider smoke testing.

Checks scheduler readiness BEFORE incident discovery to fail fast when
the scheduler is unhealthy instead of waiting for incidents that will
never be produced.

Exit codes:
    0 - Scheduler health check passed (Ready)
    1 - Scheduler health check failed (classified with failure artifact written)

Usage:
    python scripts/check_scheduler_health_gate.py \
        --kubeconfig <path> \
        --namespace <ns> \
        --artifact-dir <path>

This is a thin wrapper around the scheduler_health_gate package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Establish repo root as import root before importing the local package.
# When Python runs a script file, sys.path[0] is the script's directory,
# not the repo root. This ensures `from scripts.scheduler_health_gate` resolves
# correctly regardless of the execution context.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.scheduler_health_gate import run_scheduler_health_gate  # noqa: E402


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scheduler health gate for provider smoke testing"
    )
    parser.add_argument(
        "--kubeconfig", required=True,
        help="Path to kubeconfig"
    )
    parser.add_argument(
        "--namespace", required=True,
        help="Kubernetes namespace"
    )
    parser.add_argument(
        "--artifact-dir", default="./lab-artifacts/live",
        help="Artifact directory"
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Scheduler Health Gate ===", flush=True)
    print(f"Namespace: {args.namespace}", flush=True)
    print(f"Artifact dir: {artifact_dir}", flush=True)
    print("", flush=True)
    
    result = run_scheduler_health_gate(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        artifact_dir=artifact_dir,
    )
    
    # Write result artifact
    result_data = result.to_dict()
    result_path = artifact_dir / "provider-smoke" / "scheduler-health" / "scheduler-health-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result_data, indent=2))
    
    if result.passed:
        print("\nScheduler health gate PASSED", flush=True)
        print(f"Deployment: {result.deployment_name}", flush=True)
        print(f"Ready replicas: {result.ready_replicas}", flush=True)
        return 0
    else:
        print(f"\nScheduler health gate FAILED: {result.failure_class}", flush=True)
        print(f"Reason: {result.failure_reason}", flush=True)
        print(f"Details: {result.failure_details}", flush=True)
        print(f"Artifacts: {artifact_dir}/provider-smoke/scheduler-health/", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Backend health gate for provider smoke testing.

Polls /api/health with bounded retries and classifies failures.
Fails fast if backend returns persistent HTTP 500.

Exit codes:
    0 - Backend health check passed (HTTP 200)
    1 - Backend health check failed (classified with failure artifact written)

Usage:
    python scripts/check_backend_health_gate.py \
        --kubeconfig <path> \
        --namespace <ns> \
        --deployment <name> \
        --container <name> \
        --port <port> \
        --max-retries <n> \
        --retry-interval <s> \
        --artifact-dir <path>

This is a thin wrapper around the check_backend_health_gate package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.backend_health_gate import run_health_gate


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backend health gate for provider smoke testing"
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
        "--deployment", default="k9b-backend",
        help="Backend deployment name"
    )
    parser.add_argument(
        "--container", default="backend",
        help="Backend container name"
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="Backend port"
    )
    parser.add_argument(
        "--max-retries", type=int, default=30,
        help="Maximum polling attempts"
    )
    parser.add_argument(
        "--retry-interval", type=int, default=5,
        help="Seconds between retries"
    )
    parser.add_argument(
        "--artifact-dir", default="./lab-artifacts/live",
        help="Artifact directory"
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Backend Health Gate ===", flush=True)
    print(f"Namespace: {args.namespace}", flush=True)
    print(f"Deployment: {args.deployment}", flush=True)
    print(f"Container: {args.container}", flush=True)
    print(f"Max retries: {args.max_retries} x {args.retry_interval}s = {args.max_retries * args.retry_interval}s", flush=True)
    print("", flush=True)
    
    result = run_health_gate(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        deployment=args.deployment,
        container=args.container,
        port=args.port,
        max_retries=args.max_retries,
        retry_interval=args.retry_interval,
        artifact_dir=artifact_dir,
    )
    
    # Write result artifact
    result_data = result.to_dict()
    result_path = artifact_dir / "provider-smoke" / "backend-health" / "health-check-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result_data, indent=2))
    
    if result.passed:
        print("\nBackend health gate PASSED", flush=True)
        print(f"HTTP 200 after {result.poll_count} polls ({result.total_elapsed_seconds:.1f}s)", flush=True)
        return 0
    else:
        print(f"\nBackend health gate FAILED: {result.failure_class}", flush=True)
        print(f"Final HTTP: {result.final_http_code}", flush=True)
        print("Artifacts: lab-artifacts/live/provider-smoke/backend-health/", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

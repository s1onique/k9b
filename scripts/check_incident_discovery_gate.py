#!/usr/bin/env python3
"""CLI wrapper for incident discovery gate.

This script provides a command-line interface to the incident discovery gate,
allowing it to be called from workflows or directly.

Usage:
    python scripts/check_incident_discovery_gate.py \
        --kubeconfig <path> \
        --namespace <ns> \
        --fixture-name <name> \
        --max-retries 12 \
        --retry-interval 10 \
        --artifact-dir ./lab-artifacts/live

Exit codes:
    0 - Incident discovered (passed)
    1 - Incident discovery failed (classified with failure artifact written)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Establish repo root as import root before importing the local package.
# When Python runs a script file, sys.path[0] is the script's directory,
# not the repo root. This ensures `from scripts.incident_discovery_gate` resolves
# correctly regardless of the execution context.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.incident_discovery_gate import run_incident_discovery


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Incident discovery gate for provider smoke testing"
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
        "--backend-deployment",
        default="k9b-backend",
        help="Backend deployment name"
    )
    parser.add_argument(
        "--backend-container",
        default="backend",
        help="Backend container name"
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8080,
        help="Backend port"
    )
    parser.add_argument(
        "--fixture-name",
        default="cnpg-lab-failing-app",
        help="Incident fixture pod name"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=12,
        help="Maximum polling attempts"
    )
    parser.add_argument(
        "--retry-interval",
        type=int,
        default=10,
        help="Seconds between retries"
    )
    parser.add_argument(
        "--artifact-dir",
        default="./lab-artifacts/live",
        help="Artifact directory"
    )
    parser.add_argument(
        "--expect-llm-enrichment",
        action="store_true",
        help="Fail if an incident exists but LLM enrichment/provider invocation is not observed."
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Incident Discovery Gate ===", flush=True)
    print(f"Namespace: {args.namespace}", flush=True)
    print(f"Backend: {args.backend_deployment}:{args.backend_port}", flush=True)
    print(f"Fixture: {args.fixture_name}", flush=True)
    print(f"Max retries: {args.max_retries} x {args.retry_interval}s = {args.max_retries * args.retry_interval}s", flush=True)
    if args.expect_llm_enrichment:
        print("LLM enrichment check: ENABLED", flush=True)
    else:
        print("LLM enrichment check: DISABLED", flush=True)
    print(f"Artifact directory: {artifact_dir}", flush=True)
    print("", flush=True)
    
    result = run_incident_discovery(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        backend_deployment=args.backend_deployment,
        backend_container=args.backend_container,
        backend_port=args.backend_port,
        fixture_name=args.fixture_name,
        artifact_dir=artifact_dir,
        max_retries=args.max_retries,
        retry_interval=args.retry_interval,
        expect_llm_enrichment=args.expect_llm_enrichment,
    )
    
    # Write result artifact to the correct path (not double-nested)
    result_data = result.to_dict()
    result_path = artifact_dir / "incident-discovery-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result_data, indent=2))
    
    if result.passed:
        print("\nIncident discovery gate PASSED", flush=True)
        print(f"Incident ID: {result.incident_id}", flush=True)
        print(f"Discovery time: {result.total_elapsed_seconds:.1f}s after {result.poll_count} polls", flush=True)
        return 0
    else:
        print(f"\nIncident discovery gate FAILED: {result.failure_class}", flush=True)
        print(f"Final HTTP statuses: {', '.join(set(result.http_status_codes_seen[-3:]))}", flush=True)
        print(f"Artifacts: {artifact_dir}/", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

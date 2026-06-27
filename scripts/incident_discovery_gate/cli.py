"""CLI module for incident discovery gate.

This module handles argument parsing, environment variable defaults,
and command orchestration for the incident discovery gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .constants import (
    DEFAULT_FIXTURE_NAME,
)
from .main import run_incident_discovery


def create_arg_parser() -> argparse.ArgumentParser:
    """Create the argument parser for incident discovery gate CLI."""
    parser = argparse.ArgumentParser(
        prog="incident-discovery-gate",
        description="Check incident discovery with classified failure modes.",
    )
    
    parser.add_argument(
        "--kubeconfig",
        type=str,
        default=os.environ.get("KUBECONFIG", ""),
        help="Path to kubeconfig file (default: from KUBECONFIG env)",
    )
    
    parser.add_argument(
        "--namespace",
        type=str,
        default=os.environ.get("NAMESPACE", "default"),
        help="Kubernetes namespace (default: from NAMESPACE env or 'default')",
    )
    
    parser.add_argument(
        "--backend-deployment",
        type=str,
        default=os.environ.get("BACKEND_DEPLOYMENT", "k9b-backend"),
        help="Backend deployment name (default: from BACKEND_DEPLOYMENT env or 'k9b-backend')",
    )
    
    parser.add_argument(
        "--backend-container",
        type=str,
        default=os.environ.get("BACKEND_CONTAINER", "backend"),
        help="Backend container name (default: from BACKEND_CONTAINER env or 'backend')",
    )
    
    parser.add_argument(
        "--backend-port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", "8080")),
        help="Backend port (default: from BACKEND_PORT env or 8080)",
    )
    
    parser.add_argument(
        "--fixture-name",
        type=str,
        default=os.environ.get("FIXTURE_NAME", DEFAULT_FIXTURE_NAME),
        help=f"Incident fixture pod name (default: from FIXTURE_NAME env or '{DEFAULT_FIXTURE_NAME}')",
    )
    
    parser.add_argument(
        "--max-retries",
        type=int,
        default=12,
        help="Maximum polling attempts (default: 12)",
    )
    
    parser.add_argument(
        "--retry-interval",
        type=int,
        default=10,
        help="Seconds between retries (default: 10)",
    )
    
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default=os.environ.get("ARTIFACT_DIR", "/tmp/k9b-artifacts"),
        help="Directory for output artifacts (default: from ARTIFACT_DIR env or /tmp/k9b-artifacts)",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    
    parser.add_argument(
        "--expect-llm-enrichment",
        action="store_true",
        help="Fail if an incident exists but LLM enrichment/provider invocation is not observed.",
    )
    
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for incident discovery gate CLI.
    
    Args:
        argv: Command line arguments (defaults to sys.argv)
        
    Returns:
        Exit code: 0 for pass, 1 for fail
    """
    parser = create_arg_parser()
    args = parser.parse_args(argv)
    
    # Validate kubeconfig
    if not args.kubeconfig:
        print("ERROR: --kubeconfig required or KUBECONFIG env must be set", file=sys.stderr)
        return 1
    
    kubeconfig = args.kubeconfig
    namespace = args.namespace
    artifact_dir = Path(args.artifact_dir)
    
    # Run incident discovery
    result = run_incident_discovery(
        kubeconfig=kubeconfig,
        namespace=namespace,
        backend_deployment=args.backend_deployment,
        backend_container=args.backend_container,
        backend_port=args.backend_port,
        fixture_name=args.fixture_name,
        artifact_dir=artifact_dir,
        max_retries=args.max_retries,
        retry_interval=args.retry_interval,
        expect_llm_enrichment=args.expect_llm_enrichment,
    )
    
    # Output JSON if requested
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    
    # Return appropriate exit code
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

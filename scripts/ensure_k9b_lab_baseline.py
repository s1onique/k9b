#!/usr/bin/env python3
"""CLI wrapper for ensure_k9b_baseline_ready.

Usage:
    .venv/bin/python scripts/ensure_k9b_lab_baseline.py \
        --lab-name otel-demo \
        --release-name k9b \
        --namespace k9b \
        --chart-path ./charts/k9b \
        --artifact-dir ./lab-artifacts/otel-demo \
        --kubeconfig /path/to/kubeconfig \
        --backend-deployment k9b-backend \
        --timeout-seconds 240
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.k9b_lab_common_baseline import ensure_k9b_baseline_ready


def main() -> None:
    parser = argparse.ArgumentParser(description="Install k9b baseline and verify rollout")
    parser.add_argument("--lab-name", required=True, help="Lab identifier (e.g., cnpg, otel-demo)")
    parser.add_argument("--release-name", default="k9b", help="Helm release name")
    parser.add_argument("--namespace", default="k9b", help="Kubernetes namespace")
    parser.add_argument("--chart-path", required=True, type=Path, help="Path to Helm chart directory")
    parser.add_argument("--artifact-dir", required=True, type=Path, help="Directory for evidence artifacts")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig file")
    parser.add_argument("--values-path", type=Path, help="Path to values file")
    parser.add_argument("--backend-deployment", default="k9b-backend", help="Backend deployment name")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Rollout timeout in seconds")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        dest="set_values",
        help="Set Helm values (can be repeated, e.g., --set image.backend.repository=foo)",
    )
    parser.add_argument(
        "--set-string",
        action="append",
        default=[],
        dest="set_string_values",
        help="Set Helm string values (can be repeated, e.g., --set-string diagnosisProvider.baseUrl=https://example.invalid/v1)",
    )

    args = parser.parse_args()

    result = ensure_k9b_baseline_ready(
        lab_name=args.lab_name,
        release_name=args.release_name,
        namespace=args.namespace,
        chart_path=args.chart_path,
        artifact_dir=args.artifact_dir,
        kubeconfig=args.kubeconfig,
        values_path=args.values_path,
        backend_deployment=args.backend_deployment,
        timeout_seconds=args.timeout_seconds,
        set_values=args.set_values if args.set_values else None,
        set_string_values=args.set_string_values if args.set_string_values else None,
    )

    # Write result artifact
    import json
    result_file = args.artifact_dir / "k9b-baseline-result.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(result, indent=2))

    if not result["success"]:
        print(f"FAIL: {result['message']}", file=sys.stderr)
        if result["failure_class"]:
            print(f"Failure class: {result['failure_class']}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {result['message']}")
    print(f"Artifacts written to: {args.artifact_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()

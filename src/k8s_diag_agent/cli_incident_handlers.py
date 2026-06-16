"""CLI handlers for incident snapshot operations."""

from __future__ import annotations

import argparse
import sys

from .cli_logging import _cli_run_label, _log_cli_event

# =============================================================================
# Incident Snapshot Handler
# =============================================================================


def handle_incident(args: argparse.Namespace) -> int:
    """Handle the incident snapshot command.

    Captures a bounded, sanitized incident evidence bundle from a Kubernetes
    namespace for LLM/Cline review.
    """
    component = "cli-incident"
    run_label = _cli_run_label(component, args.namespace)
    _log_cli_event(
        component,
        run_label,
        "incident command started",
        metadata={
            "namespace": args.namespace,
            "context": args.context,
            "since_hours": args.since,
        },
    )

    try:
        from .collect.incident_snapshot import (
            collect_incident_snapshot,
            write_incident_bundle,
        )
    except ImportError as exc:
        print(f"Unable to import incident snapshot module: {exc}", file=sys.stderr)
        return 1

    try:
        bundle = collect_incident_snapshot(
            namespace=args.namespace,
            context=args.context,
            since_hours=args.since,
        )
    except RuntimeError as exc:
        _log_cli_event(
            component,
            run_label,
            "incident collection failed",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Incident collection failed: {exc}", file=sys.stderr)
        return 1

    # Ensure output directory exists
    args.output.mkdir(parents=True, exist_ok=True)

    try:
        written = write_incident_bundle(bundle, args.output)
    except OSError as exc:
        _log_cli_event(
            component,
            run_label,
            "incident bundle write failed",
            severity="ERROR",
            metadata={"error": str(exc), "output": str(args.output)},
        )
        print(f"Failed to write incident bundle: {exc}", file=sys.stderr)
        return 1

    print(f"Incident snapshot captured for namespace '{args.namespace}'")
    print(f"Bundle ID: {bundle.metadata.bundle_id}")
    print(f"Output: {args.output}")
    print()
    print("Evidence summary:")
    print(f"  - Pods: {bundle.metadata.total_pods} (failing: {bundle.metadata.failing_pods_count})")
    print(f"  - Deployments: {bundle.metadata.total_deployments}")
    print(f"  - Events: {bundle.metadata.total_events}")
    print(f"  - Symptoms: {bundle.metadata.symptoms_count}")
    print()
    print("Files written:")
    for name, path in sorted(written.items()):
        print(f"  - {name}")

    if bundle.collection_errors:
        print()
        print("Collection warnings:")
        for error in bundle.collection_errors:
            print(f"  - {error}", file=sys.stderr)

    _log_cli_event(
        component,
        run_label,
        "incident command completed",
        metadata={
            "bundle_id": bundle.metadata.bundle_id,
            "output": str(args.output),
            "failing_pods": bundle.metadata.failing_pods_count,
            "symptoms": bundle.metadata.symptoms_count,
        },
    )
    return 0


# Re-export for backward compatibility
__all__ = [
    "handle_incident",
]

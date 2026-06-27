"""CLI module for scheduler health gate.

This module handles argument parsing, environment variable defaults,
and command orchestration for the scheduler health gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from .collect import (
    collect_scheduler_logs,
    get_namespace_events,
    get_scheduler_deployment_status,
    get_scheduler_pod_selector,
    get_scheduler_pods,
)
from .contracts import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
    SchedulerHealthResult,
)
from .evaluate import (
    check_crash_loop,
    check_terminated_pods,
    check_waiting_pods,
)
from .render import (
    render_deployment_status,
    render_partial_readiness_warning,
    write_all_artifacts,
)

# =============================================================================
# Argument parsing
# =============================================================================


def create_arg_parser() -> argparse.ArgumentParser:
    """Create the argument parser for scheduler health gate CLI."""
    parser = argparse.ArgumentParser(
        prog="scheduler-health-gate",
        description="Check scheduler health before incident discovery.",
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
    
    return parser


# =============================================================================
# Main orchestration
# =============================================================================


def run_scheduler_health_gate(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
) -> SchedulerHealthResult:
    """Check scheduler health and classify failures.
    
    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        artifact_dir: Directory for artifacts
        
    Returns:
        SchedulerHealthResult with classification and diagnostics
    """
    result = SchedulerHealthResult()
    result.scheduler_diagnosis["timestamp"] = datetime.now(UTC).isoformat()
    
    # Create artifact directory
    scheduler_dir = artifact_dir / "provider-smoke" / "scheduler-health"
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Check deployment existence
    print("Checking scheduler deployment...", flush=True)
    deployment_status = get_scheduler_deployment_status(kubeconfig, namespace)
    result.deployment_found = deployment_status.get("found", False)
    result.deployment_name = SCHEDULER_DEPLOYMENT_NAME
    result.scheduler_diagnosis["deployment"] = deployment_status
    
    if not deployment_status.get("found"):
        # Scheduler deployment not found
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_MISSING
        result.failure_reason = "scheduler_deployment_not_found"
        result.failure_details = f"Deployment {SCHEDULER_DEPLOYMENT_NAME} not found in namespace {namespace}"
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        write_all_artifacts(scheduler_dir, result, {})
        return result
    
    # Derive pod selector from deployment (canonical Kubernetes relationship)
    pod_selector = get_scheduler_pod_selector(kubeconfig, namespace, SCHEDULER_DEPLOYMENT_NAME)
    result.scheduler_diagnosis["pod_selector"] = pod_selector
    
    # Step 2: Get pod status using derived selector
    print("Checking scheduler pods...", flush=True)
    pods_data = get_scheduler_pods(kubeconfig, namespace, pod_selector)
    result.scheduler_pods_json = json.dumps(pods_data)
    result.pod_count = len(pods_data.get("items", []))
    result.scheduler_diagnosis["pods"] = {
        "count": result.pod_count,
        "raw": "collected",
    }
    
    # Step 3: Check crash loop FIRST (highest priority)
    crash_loop_pods = check_crash_loop(pods_data)
    result.crash_loop_pods = crash_loop_pods
    result.scheduler_diagnosis["crash_loop_pods"] = crash_loop_pods
    
    if crash_loop_pods:
        first_crash = crash_loop_pods[0]
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.failure_reason = "scheduler_crash_loop"
        result.failure_details = (
            f"Scheduler pod {first_crash['pod']} container {first_crash['container']} "
            f"is in {first_crash['reason']} after {first_crash['restart_count']} restarts"
        )
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        logs = collect_scheduler_logs(kubeconfig, namespace, pod_selector)
        result.scheduler_logs = logs  # Store for bounded summary
        write_all_artifacts(scheduler_dir, result, logs)
        return result
    
    # Step 4: Check deployment readiness
    ready_replicas = deployment_status.get("ready_replicas", 0) or 0
    available_replicas = deployment_status.get("available_replicas", 0) or 0
    spec_replicas = deployment_status.get("replicas", 1) or 1
    result.ready_replicas = ready_replicas
    result.available_replicas = available_replicas
    
    render_deployment_status(ready_replicas, spec_replicas, available_replicas)
    
    # Step 5: Check for other waiting pods
    result.waiting_pods = check_waiting_pods(pods_data)
    result.scheduler_diagnosis["waiting_pods"] = result.waiting_pods
    
    # Step 6: Check for terminated pods
    result.terminated_pods = check_terminated_pods(pods_data)
    result.scheduler_diagnosis["terminated_pods"] = result.terminated_pods
    
    # Step 7: Determine health based on ready replicas
    # Fail when deployment expects replicas but none are ready
    if spec_replicas > 0 and ready_replicas == 0:
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_NOT_READY
        # Distinguish between no pods and pods but none ready
        if result.pod_count == 0:
            result.failure_reason = "scheduler_no_pods"
            result.failure_details = (
                f"Scheduler deployment expects {spec_replicas} replica(s) but has no pods running."
            )
        else:
            result.failure_reason = "scheduler_no_ready_replicas"
            result.failure_details = (
                f"Scheduler has {result.pod_count} pod(s) but 0 ready replicas. "
                f"Check waiting/terminated containers."
            )
        result.scheduler_diagnosis["failure_class"] = result.failure_class
        result.scheduler_diagnosis["failure_reason"] = result.failure_reason
        result.scheduler_diagnosis["failure_details"] = result.failure_details
        
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)
        
        # Collect events before returning
        result.namespace_events = get_namespace_events(kubeconfig, namespace)
        result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
        logs = collect_scheduler_logs(kubeconfig, namespace, pod_selector)
        result.scheduler_logs = logs  # Store for bounded summary
        write_all_artifacts(scheduler_dir, result, logs)
        return result
    
    if ready_replicas < spec_replicas:
        # Partial readiness - this could be a transient state
        # We'll consider it healthy but log a warning
        render_partial_readiness_warning(ready_replicas, spec_replicas)
        result.passed = True
        result.failure_class = ""
    
    # Step 8: Get namespace events
    result.namespace_events = get_namespace_events(kubeconfig, namespace)
    result.scheduler_diagnosis["namespace_events_count"] = len(result.namespace_events)
    
    # Scheduler is healthy
    result.passed = True
    result.failure_class = ""
    print("SCHEDULER HEALTH GATE PASSED", flush=True)
    
    logs = collect_scheduler_logs(kubeconfig, namespace, pod_selector)
    write_all_artifacts(scheduler_dir, result, logs)
    return result


# =============================================================================
# CLI entry point
# =============================================================================


def main(argv: list[str] | None = None) -> int:
    """Main entry point for scheduler health gate CLI.
    
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
    
    # Run health check
    result = run_scheduler_health_gate(kubeconfig, namespace, artifact_dir)
    
    # Output JSON if requested
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    
    # Return appropriate exit code
    return 0 if result.passed else 1

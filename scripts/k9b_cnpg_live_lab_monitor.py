#!/usr/bin/env python3
"""Proactive rollout monitor for CNPG Live Lab.

This module provides:
- Periodic rollout health monitoring during deployment
- Automatic failure classification
- Artifact collection for diagnostics
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Import crash artifact collection - module is required as part of monitor contract
from .k9b_cnpg_live_lab_constants import FAILURE_CRASH_LOOP
from .k9b_cnpg_live_lab_crash_artifacts import collect_crash_artifacts
from .k9b_cnpg_live_lab_helm_inventory import (
    parse_workload_inventory_from_file,
)
from .k9b_cnpg_live_lab_helpers import log, write_json_atomically
from .k9b_cnpg_live_lab_rollout import (
    _check_rollout_success,
    _check_rollout_success_multi,
    _collect_rollout_snapshot,
)

# Monitoring intervals in seconds
INTERVAL_SHORT = 5  # First few minutes
INTERVAL_MEDIUM = 15  # After initial checks
INTERVAL_LONG = 30  # Later stages

# Timeout thresholds
TIMEOUT_INITIAL = 120  # 2 minutes for first pod
TIMEOUT_DEPLOYMENT = 300  # 5 minutes for full deployment


def monitor_rollout(
    kubeconfig: str,
    namespace: str,
    release: str = "k9b",
    deadline_seconds: int | None = None,
    poll_interval: int | None = None,
    target_count: int = 1,
    artifact_dir: Path | None = None,
    *,
    max_wait: int | None = None,  # New preferred name
    interval: int | None = None,  # New preferred name
    expected_deployments: list[str] | None = None,  # Multi-deployment mode
) -> tuple[bool, str, dict[str, Any]]:
    """Monitor rollout until success or timeout.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        release: Release name to monitor
        deadline_seconds: Maximum time to wait in seconds (backward-compatible alias for max_wait)
        poll_interval: Polling interval in seconds (backward-compatible alias for interval)
        target_count: Expected number of replicas
        artifact_dir: Directory for artifacts
        max_wait: Maximum time to wait in seconds (new preferred name)
        interval: Polling interval in seconds (new preferred name)
        expected_deployments: List of expected deployment names. When provided with one
            or more items, uses manifest-derived deployment checks. When empty or None,
            falls back to legacy single-deployment mode using release name.

    Returns:
        Tuple of (success, status_message, snapshot)
    """
    # Resolve max_wait: deadline_seconds takes precedence for backward compat
    effective_max_wait = deadline_seconds if deadline_seconds is not None else (max_wait if max_wait is not None else 300)
    # Resolve interval: poll_interval takes precedence for backward compat
    effective_interval = poll_interval if poll_interval is not None else (interval if interval is not None else 15)
    start_time = time.time()
    last_snapshot: dict[str, Any] | None = None
    snapshot_count = 0

    # Determine if we should use manifest-derived deployment inventory
    # A rendered manifest with one or more Deployments is authoritative.
    # We must NOT fall back to release name as deployment name when manifest has deployments.
    resolved_expected_deployments = expected_deployments or []
    use_manifest_inventory = len(resolved_expected_deployments) > 0

    if use_manifest_inventory:
        # Manifest-derived mode: use the actual deployment names from rendered manifest
        deployments_str = ", ".join(resolved_expected_deployments)
        effective_target_count = len(resolved_expected_deployments)
        log(f"Starting rollout monitor for {release} in {namespace}")
        log(f"Expected deployments: {deployments_str}")
        log(f"Max wait: {effective_max_wait}s, interval: {effective_interval}s, target: {effective_target_count}")
    else:
        # Fallback mode: single deployment using release name as deployment name
        effective_target_count = target_count
        log(f"Starting rollout monitor for {release} in {namespace}")
        log(f"Max wait: {effective_max_wait}s, interval: {effective_interval}s, target: {effective_target_count}")

    while time.time() - start_time < effective_max_wait:
        elapsed = int(time.time() - start_time)

        # Get deployment status using manifest inventory or fallback mode
        if use_manifest_inventory:
            success, status = _check_rollout_success_multi(
                kubeconfig, namespace, resolved_expected_deployments, effective_target_count
            )
        else:
            success, status = _check_rollout_success(kubeconfig, namespace, release, effective_target_count)

        if success:
            if use_manifest_inventory:
                log(f"Multi-deployment rollout successful after {elapsed}s")
            else:
                log(f"Rollout successful after {elapsed}s")
            return True, status, last_snapshot or {}

        log(f"[{elapsed}s] Rollout not complete: {status}")

        # Collect snapshot for classification check on every poll iteration
        # This enables fail-fast detection of fatal conditions like CrashLoopBackOff
        snapshot_ts = datetime.now(UTC).isoformat()
        snapshot = _collect_rollout_snapshot(
            kubeconfig, namespace,
            artifact_dir or Path("/tmp"),
            release, snapshot_ts,
            expected_deployments=resolved_expected_deployments if use_manifest_inventory else None,
            target_count=effective_target_count,
        )
        if snapshot:
            last_snapshot = snapshot
            snapshot_count += 1

            # FAIL-FAST: Check for fatal crash loop and exit immediately
            # CrashLoopBackOff is a Kubernetes-reported fatal condition - no point
            # waiting for full timeout when the container is already failing repeatedly
            rollout_checks = snapshot.get("rollout_checks", {})
            failure_class = rollout_checks.get("failure_class", "")
            diagnostics = rollout_checks.get("diagnostics", {})

            if failure_class == FAILURE_CRASH_LOOP:
                crash_loop_data = diagnostics.get("crash_loop", [])
                if crash_loop_data:
                    first_crash = crash_loop_data[0]
                    crash_pod = first_crash.get("pod", "unknown")
                    crash_container = first_crash.get("container", "unknown")
                    crash_restarts = first_crash.get("restart_count", 0)
                    log(f"FAIL-FAST: CrashLoopBackOff detected for {crash_pod}/{crash_container} "
                        f"after {crash_restarts} restarts at {elapsed}s")

                    # Write final diagnosis with crash loop details
                    final_diagnosis = {
                        "fatal": True,
                        "failure_class": failure_class,
                        "status": f"Rollout failed: pod {crash_pod} container {crash_container} "
                                  f"is in CrashLoopBackOff after {crash_restarts} restarts",
                        "diagnostics": diagnostics,
                        "crash_pod_name": crash_pod,
                        "crash_container_name": crash_container,
                        "crash_restart_count": crash_restarts,
                    }
                    if artifact_dir:
                        write_json_atomically(artifact_dir / "final-diagnosis.json", final_diagnosis)

                    # Write snapshot to file
                    if artifact_dir:
                        snapshot_path = artifact_dir / f"rollout-snapshot-{snapshot_count}.json"
                        write_json_atomically(snapshot_path, snapshot)
                        log(f"Snapshot written to {snapshot_path}")

                    return False, final_diagnosis["status"], snapshot

            # Write periodic snapshot only on first or long intervals to reduce artifact noise
            if snapshot_count == 1 or elapsed >= 60:
                if artifact_dir:
                    snapshot_path = artifact_dir / f"rollout-snapshot-{snapshot_count}.json"
                    write_json_atomically(snapshot_path, snapshot)
                    log(f"Snapshot written to {snapshot_path}")

        time.sleep(effective_interval)

    # Timed out - collect final snapshot
    elapsed = int(time.time() - start_time)
    if use_manifest_inventory:
        log(f"Multi-deployment rollout timed out after {elapsed}s")
    else:
        log(f"Rollout timed out after {elapsed}s")

    final_snapshot = _collect_rollout_snapshot(
        kubeconfig, namespace,
        artifact_dir or Path("/tmp"),
        release, datetime.now(UTC).isoformat(),
        expected_deployments=resolved_expected_deployments if use_manifest_inventory else None,
        target_count=effective_target_count,
    )

    if final_snapshot:
        last_snapshot = final_snapshot
        if artifact_dir:
            write_json_atomically(artifact_dir / "rollout-final.json", final_snapshot)

    return False, f"Rollout timed out after {elapsed}s", last_snapshot or {}


def _classify_and_write_results(
    artifact_dir: Path,
    success: bool,
    status: str,
    failure_class: str,
    diagnostics: dict[str, Any],
    crash_artifacts_collected: bool,
    expected_deployments: list[str],
    elapsed: int,
    deployments_str: str,
) -> None:
    """Write classification results to artifact files."""
    final_status = status
    if not success:
        if failure_class == "crash_loop":
            crash_loop_data = diagnostics.get("crash_loop", [])
            if crash_loop_data:
                first_crash = crash_loop_data[0]
                crash_pod = first_crash.get("pod", "unknown")
                crash_container = first_crash.get("container", "unknown")
                crash_restarts = first_crash.get("restart_count", 0)
                final_status = (
                    f"Rollout failed: pod {crash_pod} container {crash_container} "
                    f"is in CrashLoopBackOff after {crash_restarts} restarts"
                )
        elif failure_class == "expected_deployment_missing":
            final_status = (
                f"Rollout failed: expected deployment(s) not found in cluster: {deployments_str}. "
                "Check Helm install/upgrade status."
            )
        else:
            # Use the actual status from monitor_rollout (avoids "timed out after 0s" when elapsed is not tracked)
            final_status = status

    result = {
        "success": success,
        "status": final_status,
        "failure_class": failure_class,
        "rollout_checks": {"failure_class": failure_class, "diagnostics": diagnostics},
        "expected_deployments": expected_deployments,
    }
    write_json_atomically(artifact_dir / "rollout-result.json", result)
    diagnosis_result = {
        "failure_class": failure_class,
        "status": final_status,
        "success": success,
        "diagnostics": diagnostics,
    }
    write_json_atomically(artifact_dir / "final-diagnosis.json", diagnosis_result)
    failure_line = f"**Failure class**: `{failure_class}`" if failure_class else ""
    artifact_line = "**Crash artifacts**: collected" if crash_artifacts_collected else ""
    bounded_content = f"""### Rollout Monitor Result

**Success**: {success}
**Status**: {final_status}
{failure_line}
{artifact_line}
**Expected deployments**: {deployments_str}
"""
    (artifact_dir / "bounded-summary.txt").write_text(bounded_content)
    print(json.dumps(result, indent=2))


def main_monitor_rollout() -> int:
    """CLI entry point for rollout monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor Kubernetes rollout until success or timeout"
    )
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig file")
    parser.add_argument("--namespace", required=True, help="Kubernetes namespace")
    parser.add_argument("--release", default="k9b", help="Release name (default: k9b)")
    parser.add_argument("--max-wait", type=int, default=300, help="Max wait time in seconds")
    parser.add_argument("--deadline", type=int, help="Alias for --max-wait (backward compatibility)")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
    parser.add_argument("--poll-interval", type=int, help="Alias for --interval (backward compatibility)")
    parser.add_argument("--target-count", type=int, default=1, help="Expected replica count")
    parser.add_argument("--artifact-dir", default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
                        help="Artifact directory")
    parser.add_argument("--expected-deployment", action="append", default=[], dest="expected_deployments",
                        help="Expected deployment name (can be repeated)")

    args = parser.parse_args(sys.argv[2:])
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Use aliases if provided (backward compatibility with workflow)
    max_wait = args.deadline if args.deadline is not None else args.max_wait
    interval = args.poll_interval if args.poll_interval is not None else args.interval

    # Determine expected deployments from rendered manifest
    expected_deployments = get_expected_deployments_from_manifest(artifact_dir, args.release, args.namespace)

    if not expected_deployments and args.expected_deployments:
        expected_deployments = args.expected_deployments
        log(f"Using explicit expected deployments: {expected_deployments}")

    # Monitor rollout using shared logic for both single and multi-deployment
    success, status, snapshot = monitor_rollout(
        args.kubeconfig,
        args.namespace,
        args.release,
        deadline_seconds=max_wait,
        poll_interval=interval,
        target_count=args.target_count,
        artifact_dir=artifact_dir,
        expected_deployments=expected_deployments if expected_deployments else None,
    )

    # Extract classification data from snapshot
    rollout_checks = snapshot.get("rollout_checks", {}) if snapshot else {}
    diagnostics = rollout_checks.get("diagnostics", {}) if rollout_checks else {}
    failure_class = rollout_checks.get("failure_class", "") if rollout_checks else ""

    # Collect crash artifacts when crash loop is detected
    crash_artifacts_collected = False
    crash_loop_data = diagnostics.get("crash_loop", [])
    if failure_class == "crash_loop" and crash_loop_data and collect_crash_artifacts is not None:
        log("Crash loop detected, collecting artifacts...")
        try:
            artifact_paths = collect_crash_artifacts(args.kubeconfig, args.namespace, artifact_dir, crash_loop_data)
            if artifact_paths:
                log(f"Crash artifacts collected: {len(artifact_paths)} files")
                crash_artifacts_collected = True
        except Exception as e:
            log(f"Warning: Failed to collect crash artifacts: {e}")
            diagnostics["artifact_collection_failed"] = True
            diagnostics["artifact_collection_error"] = str(e)

    # Hardening: set expected_deployment_missing when deployments not found
    if not failure_class and "not found" in status.lower():
        failure_class = "expected_deployment_missing"

    # Write results
    deployments_str = ", ".join(expected_deployments) if expected_deployments else args.release
    elapsed = 0  # Not tracked in single-call mode
    _classify_and_write_results(
        artifact_dir, success, status, failure_class, diagnostics,
        crash_artifacts_collected, expected_deployments, elapsed, deployments_str
    )

    return 0 if success else 1


def get_expected_deployments_from_manifest(
    artifact_dir: Path,
    release_name: str = "k9b",
    namespace: str = "",
) -> list[str]:
    """Get expected deployment names from rendered manifest inventory.

    This function is the primary source for determining which deployments
    should be monitored. It parses the rendered-manifest.yaml captured
    during the preflight/render phase.

    Args:
        artifact_dir: Directory containing rendered manifest artifacts
        release_name: Helm release name (used for label selector fallback)
        namespace: Kubernetes namespace (used for filtering)

    Returns:
        List of expected deployment names sorted alphabetically.
        Empty list if no rendered manifest is available.
    """
    rendered_path = artifact_dir / "helm" / "rendered-manifest.yaml"

    if not rendered_path.exists():
        log(f"No rendered manifest at {rendered_path}, cannot derive expected deployments")
        return []

    try:
        inventory = parse_workload_inventory_from_file(
            rendered_path,
            expected_name=release_name,
            expected_namespace=namespace,
        )

        all_workloads = inventory.get("rendered", {}).get("all_workloads", [])

        # Extract deployment names, sorted for determinism
        deployment_names = sorted([
            w["metadata"]["name"]
            for w in all_workloads
            if w.get("kind") == "Deployment" and w.get("metadata", {}).get("name")
        ])

        if deployment_names:
            log(f"Derived expected deployments from rendered manifest: {deployment_names}")
        else:
            log("Rendered manifest has no Deployment resources")

        return deployment_names

    except Exception as e:
        log(f"Failed to parse rendered manifest for expected deployments: {e}")
        return []



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

from .k9b_cnpg_live_lab_helm_inventory import (
    parse_workload_inventory_from_file,
)
from .k9b_cnpg_live_lab_helpers import log, write_json_atomically
from .k9b_cnpg_live_lab_rollout import (
    _check_rollout_success,
    _check_rollout_success_multi,
    _collect_rollout_snapshot,
)

# Import crash artifact collection - module is required as part of monitor contract
from .k9b_cnpg_live_lab_crash_artifacts import collect_crash_artifacts

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

    log(f"Starting rollout monitor for {release} in {namespace}")
    log(f"Max wait: {effective_max_wait}s, interval: {effective_interval}s, target: {target_count}")

    while time.time() - start_time < effective_max_wait:
        elapsed = int(time.time() - start_time)

        # Get deployment status
        success, status = _check_rollout_success(kubeconfig, namespace, release, target_count)

        if success:
            log(f"Rollout successful after {elapsed}s")
            return True, status, last_snapshot or {}

        log(f"[{elapsed}s] Rollout not complete: {status}")

        # Collect periodic snapshots
        if snapshot_count == 0 or elapsed >= 60:
            snapshot_ts = datetime.now(UTC).isoformat()
            snapshot = _collect_rollout_snapshot(
                kubeconfig, namespace,
                artifact_dir or Path("/tmp"),
                release, snapshot_ts
            )
            if snapshot:
                last_snapshot = snapshot
                snapshot_count += 1

                # Write snapshot to file
                if artifact_dir:
                    snapshot_path = artifact_dir / f"rollout-snapshot-{snapshot_count}.json"
                    write_json_atomically(snapshot_path, snapshot)
                    log(f"Snapshot written to {snapshot_path}")

        time.sleep(effective_interval)

    # Timed out - collect final snapshot
    elapsed = int(time.time() - start_time)
    log(f"Rollout timed out after {elapsed}s")

    final_snapshot = _collect_rollout_snapshot(
        kubeconfig, namespace,
        artifact_dir or Path("/tmp"),
        release, datetime.now(UTC).isoformat()
    )

    if final_snapshot:
        last_snapshot = final_snapshot
        if artifact_dir:
            write_json_atomically(artifact_dir / "rollout-final.json", final_snapshot)

    return False, f"Rollout timed out after {elapsed}s", last_snapshot or {}


def main_monitor_rollout() -> int:
    """CLI entry point for rollout monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor Kubernetes rollout until success or timeout"
    )
    parser.add_argument(
        "--kubeconfig",
        required=True,
        help="Path to kubeconfig file",
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="Kubernetes namespace",
    )
    parser.add_argument(
        "--release",
        default="k9b",
        help="Release name (default: k9b)",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=300,
        help="Max wait time in seconds (default: 300)",
    )
    # Backward-compatible alias for --max-wait (used by workflow)
    parser.add_argument(
        "--deadline",
        type=int,
        help="Alias for --max-wait (backward compatibility)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Polling interval in seconds (default: 15)",
    )
    # Backward-compatible alias for --interval (used by workflow)
    parser.add_argument(
        "--poll-interval",
        type=int,
        help="Alias for --interval (backward compatibility)",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=1,
        help="Expected replica count (default: 1)",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory (default: $ARTIFACT_DIR or ./lab-artifacts/live)",
    )
    # Fallback: explicit expected deployments when rendered manifest is unavailable
    parser.add_argument(
        "--expected-deployment",
        action="append",
        default=[],
        dest="expected_deployments",
        help="Expected deployment name (can be repeated). Used when rendered manifest is unavailable.",
    )
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Use aliases if provided (backward compatibility with workflow)
    max_wait = args.deadline if args.deadline is not None else args.max_wait
    interval = args.poll_interval if args.poll_interval is not None else args.interval

    # Determine expected deployments for multi-deployment monitoring
    expected_deployments = get_expected_deployments_from_manifest(artifact_dir, args.release, args.namespace)

    if not expected_deployments and args.expected_deployments:
        # Fall back to explicit --expected-deployment flags
        expected_deployments = args.expected_deployments
        log(f"Using explicit expected deployments: {expected_deployments}")

    if not expected_deployments:
        log("No expected deployments found, using single-deployment mode")

    # Monitor rollout with multi-deployment support
    if len(expected_deployments) > 1:
        # Log expected deployments in header - DO NOT use stale "Deployment k9b" message
        deployments_str = ", ".join(expected_deployments)
        log(f"Monitoring multi-deployment rollout for expected deployments: {deployments_str}")
        # Run inside polling loop - same semantics as single-deployment mode
        start_time = time.time()
        last_snapshot: dict[str, Any] | None = None
        snapshot_count = 0

        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)

            # Get multi-deployment status
            success, status = _check_rollout_success_multi(
                args.kubeconfig, args.namespace, expected_deployments, args.target_count
            )

            if success:
                log(f"Multi-deployment rollout successful after {elapsed}s")
                result = {
                    "success": True,
                    "status": status,
                    "failure_class": "",
                    "rollout_checks": {},
                    "expected_deployments": expected_deployments,
                }
                write_json_atomically(artifact_dir / "rollout-result.json", result)
                diagnosis_result = {"failure_class": "", "status": status, "success": True}
                write_json_atomically(artifact_dir / "final-diagnosis.json", diagnosis_result)
                bounded_content = f"""### Rollout Monitor Result

**Success**: True
**Status**: {status}
**Expected deployments**: {deployments_str}
"""
                (artifact_dir / "bounded-summary.txt").write_text(bounded_content)
                print(json.dumps(result, indent=2))
                return 0

            # Use expected deployments in progress message - NOT hardcoded "Deployment k9b"
            log(f"[{elapsed}s] Rollout not complete: {status}")

            # Collect periodic snapshots
            if snapshot_count == 0 or elapsed >= 60:
                snapshot_ts = datetime.now(UTC).isoformat()
                snapshot = _collect_rollout_snapshot(
                    args.kubeconfig, args.namespace,
                    artifact_dir, args.release, snapshot_ts
                )
                if snapshot:
                    last_snapshot = snapshot
                    snapshot_count += 1
                    snapshot_path = artifact_dir / f"rollout-snapshot-{snapshot_count}.json"
                    write_json_atomically(snapshot_path, snapshot)
                    log(f"Snapshot written to {snapshot_path}")

            time.sleep(interval)

        # Timed out - collect final snapshot and classify
        elapsed = int(time.time() - start_time)
        log(f"Multi-deployment rollout timed out after {elapsed}s")

        final_snapshot = _collect_rollout_snapshot(
            args.kubeconfig, args.namespace,
            artifact_dir, args.release, datetime.now(UTC).isoformat()
        )

        if final_snapshot:
            last_snapshot = final_snapshot
            write_json_atomically(artifact_dir / "rollout-final.json", final_snapshot)

        # Classify the failure using the snapshot data
        failure_class = last_snapshot.get("rollout_checks", {}).get("failure_class", "") if last_snapshot else ""

        # Extract crash-loop details for human-readable status if applicable
        rollout_checks = last_snapshot.get("rollout_checks", {}) if last_snapshot else {}
        diagnostics = rollout_checks.get("diagnostics", {}) if rollout_checks else {}
        crash_loop_data = diagnostics.get("crash_loop", [])
        crash_artifacts_collected = False

        # Collect crash artifacts when crash loop is detected
        if failure_class == "crash_loop" and crash_loop_data and collect_crash_artifacts:
            log(f"Crash loop detected, collecting artifacts...")
            try:
                artifact_paths = collect_crash_artifacts(
                    args.kubeconfig,
                    args.namespace,
                    artifact_dir,
                    crash_loop_data,
                )
                if artifact_paths:
                    log(f"Crash artifacts collected: {len(artifact_paths)} files")
                    crash_artifacts_collected = True
            except Exception as e:
                log(f"Warning: Failed to collect crash artifacts: {e}")
                diagnostics["artifact_collection_failed"] = True
                diagnostics["artifact_collection_error"] = str(e)

        # Hardening: if _check_rollout_success_multi reported missing deployments
        # but classifier returned empty failure_class, set expected_deployment_missing directly
        if not failure_class and "not found" in status.lower():
            failure_class = "expected_deployment_missing"
            log(f"Setting failure_class to 'expected_deployment_missing' based on status: {status}")

        # Generate human-readable status message based on failure class
        if failure_class == "crash_loop" and crash_loop_data:
            first_crash = crash_loop_data[0] if crash_loop_data else {}
            crash_pod = first_crash.get("pod", "unknown")
            crash_container = first_crash.get("container", "unknown")
            crash_restarts = first_crash.get("restart_count", 0)
            final_status = (
                f"Rollout failed: pod {crash_pod} container {crash_container} "
                f"is in CrashLoopBackOff after {crash_restarts} restarts"
            )
        elif failure_class == "expected_deployment_missing":
            # Use actual expected deployment names from rendered manifests
            final_status = (
                f"Rollout failed: expected deployment(s) not found in cluster: {deployments_str}. "
                "Check Helm install/upgrade status."
            )
        else:
            final_status = f"Rollout timed out after {elapsed}s"

        result = {
            "success": False,
            "status": final_status,
            "failure_class": failure_class,
            "rollout_checks": {"failure_class": failure_class, "diagnostics": diagnostics},
            "expected_deployments": expected_deployments,
        }
        write_json_atomically(artifact_dir / "rollout-result.json", result)
        diagnosis_result = {
            "failure_class": failure_class,
            "status": final_status,
            "success": False,
            "diagnostics": diagnostics,
        }
        write_json_atomically(artifact_dir / "final-diagnosis.json", diagnosis_result)
        failure_line = f"**Failure class**: `{failure_class}`" if failure_class else ""
        artifact_line = "**Crash artifacts**: collected" if crash_artifacts_collected else ""
        bounded_content = f"""### Rollout Monitor Result

**Success**: False
**Status**: {final_status}
{failure_line}
{artifact_line}
**Expected deployments**: {deployments_str}
"""
        (artifact_dir / "bounded-summary.txt").write_text(bounded_content)
        print(json.dumps(result, indent=2))
        return 1

    # Single-deployment mode (backward compatibility)
    success, status, snapshot = monitor_rollout(
        args.kubeconfig,
        args.namespace,
        args.release,
        deadline_seconds=max_wait,
        poll_interval=interval,
        target_count=args.target_count,
        artifact_dir=artifact_dir,
    )

    # Output result
    result = {
        "success": success,
        "status": status,
        "failure_class": snapshot.get("rollout_checks", {}).get("failure_class", "")
            if snapshot else "",
        "rollout_checks": snapshot.get("rollout_checks", {}) if snapshot else {},
    }

    # Write result JSON
    write_json_atomically(artifact_dir / "rollout-result.json", result)

    # Write final-diagnosis.json (backward compatibility with workflow)
    diagnosis_result = {
        "failure_class": result["failure_class"],
        "status": status,
        "success": success,
    }
    write_json_atomically(artifact_dir / "final-diagnosis.json", diagnosis_result)

    # Write bounded-summary.txt (backward compatibility with workflow)
    failure_line = f"**Failure class**: `{result['failure_class']}`" if result['failure_class'] else ""
    bounded_content = f"""### Rollout Monitor Result

**Success**: {success}
**Status**: {status}
{failure_line}
"""
    (artifact_dir / "bounded-summary.txt").write_text(bounded_content)

    # Print to stdout
    print(json.dumps(result, indent=2))

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



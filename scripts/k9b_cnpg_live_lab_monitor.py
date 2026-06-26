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

from .k9b_cnpg_live_lab_helpers import log, write_json_atomically
from .k9b_cnpg_live_lab_rollout import (
    _check_rollout_success,
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
    max_wait: int = 300,
    interval: int = 15,
    target_count: int = 1,
    artifact_dir: Path | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Monitor rollout until success or timeout.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        release: Release name to monitor
        max_wait: Maximum time to wait in seconds
        interval: Polling interval in seconds
        target_count: Expected number of replicas
        artifact_dir: Directory for artifacts

    Returns:
        Tuple of (success, status_message, snapshot)
    """
    start_time = time.time()
    last_snapshot: dict[str, Any] | None = None
    snapshot_count = 0

    log(f"Starting rollout monitor for {release} in {namespace}")
    log(f"Max wait: {max_wait}s, interval: {interval}s, target: {target_count}")

    while time.time() - start_time < max_wait:
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

        time.sleep(interval)

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
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Use aliases if provided (backward compatibility with workflow)
    max_wait = args.deadline if args.deadline is not None else args.max_wait
    interval = args.poll_interval if args.poll_interval is not None else args.interval

    # Monitor rollout
    success, status, snapshot = monitor_rollout(
        args.kubeconfig,
        args.namespace,
        args.release,
        max_wait,
        interval,
        args.target_count,
        artifact_dir,
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

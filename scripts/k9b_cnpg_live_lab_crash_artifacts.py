#!/usr/bin/env python3
"""Crash artifact collection for CNPG Live Lab rollout diagnostics.

This module provides functions to collect crash artifacts when pod crashes
or container exits are detected during rollout monitoring.

Collected artifacts include:
- Current container logs
- Previous container logs (--previous)
- Pod describe output
- Pod JSON
- Owning ReplicaSet/Deployment
- PVC/PV state
- Helm status/manifest/values
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Sentinel file to track that crash artifacts were collected
CRASH_ARTIFACT_COLLECTED_SENTINEL = "crash-artifacts-collected.txt"


def collect_crash_artifacts(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    crash_evidence: list[dict[str, Any]],
) -> list[str]:
    """Collect crash artifacts for diagnostic investigation.

    When crash evidence is detected (pod_crash_loop, container_exit_nonzero, etc.),
    this function collects:
    - Current container logs
    - Previous container logs (--previous)
    - Pod describe output
    - Pod JSON
    - Owning ReplicaSet/Deployment
    - PVC/PV state
    - Helm status/manifest/values

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        artifact_dir: Directory for collected artifacts
        crash_evidence: List of crash evidence dicts from classify_rollout_state

    Returns:
        List of paths to collected artifact files
    """
    collected_paths: list[str] = []
    crash_dir = artifact_dir / "crash-artifacts"
    crash_dir.mkdir(parents=True, exist_ok=True)

    _log(f"Collecting crash artifacts for {len(crash_evidence)} crash evidence items")

    for evidence in crash_evidence:
        pod_name = evidence.get("pod", "")
        container_name = evidence.get("container", "")
        reason = evidence.get("reason", "unknown")

        if not pod_name:
            continue

        _log(f"Collecting artifacts for crashed pod: {pod_name} (container: {container_name}, reason: {reason})")

        # Collect pod describe
        _collect_kubectl_output(
            kubeconfig, namespace, pod_name, container_name,
            ["describe", "pod", pod_name, "-n", namespace],
            crash_dir / f"pod-describe-{pod_name}.txt",
            collected_paths
        )

        # Collect pod JSON
        _collect_kubectl_output(
            kubeconfig, namespace, pod_name, container_name,
            ["get", "pod", pod_name, "-n", namespace, "-o", "json"],
            crash_dir / f"pod-json-{pod_name}.json",
            collected_paths
        )

        # Collect current and previous logs (if container specified)
        if container_name:
            _collect_container_logs(
                kubeconfig, namespace, pod_name, container_name,
                crash_dir, collected_paths
            )

    # Collect related resources
    _collect_kubectl_output(
        kubeconfig, namespace, "", "",
        ["get", "deployments,replicasets,pods,pvc", "-n", namespace, "-o", "yaml"],
        crash_dir / "related-resources.yaml",
        collected_paths
    )

    # Write sentinel to track that crash artifacts were collected
    sentinel_path = artifact_dir / CRASH_ARTIFACT_COLLECTED_SENTINEL
    sentinel_path.write_text(json.dumps({
        "collected_at": datetime.now(UTC).isoformat(),
        "crash_evidence_count": len(crash_evidence),
        "artifacts_collected": collected_paths,
    }))
    collected_paths.append(str(sentinel_path))

    _log(f"Crash artifact collection complete: {len(collected_paths)} files in {crash_dir}")
    return collected_paths


def _log(message: str) -> None:
    """Log a message (imported from helpers to avoid circular deps)."""
    import sys
    print(f"[crash-artifacts] {message}", file=sys.stderr)


def _collect_kubectl_output(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
    container_name: str,
    cmd: list[str],
    output_path: Path,
    collected_paths: list[str],
) -> None:
    """Collect kubectl output and write to file."""
    try:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig] + cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output_path.write_text(result.stdout or "(no output)")
        collected_paths.append(str(output_path))
        _log(f"  - Collected: {output_path.name}")
    except Exception as e:
        _log(f"  - Failed to collect {output_path.name}: {e}")


def _collect_container_logs(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
    container_name: str,
    crash_dir: Path,
    collected_paths: list[str],
) -> None:
    """Collect current and previous container logs."""
    # Collect current logs
    _collect_kubectl_output(
        kubeconfig, namespace, pod_name, container_name,
        ["logs", pod_name, "-c", container_name, "-n", namespace],
        crash_dir / f"logs-{pod_name}-{container_name}-current.txt",
        collected_paths
    )

    # Collect previous logs (crash evidence)
    _collect_kubectl_output(
        kubeconfig, namespace, pod_name, container_name,
        ["logs", pod_name, "-c", container_name, "-n", namespace, "--previous"],
        crash_dir / f"logs-{pod_name}-{container_name}-previous.txt",
        collected_paths
    )

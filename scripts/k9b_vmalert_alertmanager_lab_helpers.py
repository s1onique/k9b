#!/usr/bin/env python3
"""Helper functions for the vmalert→Alertmanager→K9B incident lab.

This module provides:
- Artifact collection and sanitization
- HTTP client utilities for webhook testing
- JSON artifact helpers
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    """Write JSON data atomically to a file.

    Uses a temporary file + rename for atomic write semantics.

    Args:
        path: Destination file path
        data: Dictionary to serialize as JSON
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(path)


def log(message: str) -> None:
    """Print a log message with timestamp."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{timestamp}] {message}")


def run_kubectl(
    kubeconfig: str,
    namespace: str,
    args: list[str],
    capture_output: bool = True,
    check: bool = True,
    input_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run kubectl with common arguments.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        args: Additional kubectl arguments
        capture_output: Whether to capture stdout/stderr
        check: Whether to raise on non-zero exit
        input_data: Optional stdin input

    Returns:
        CompletedProcess with command results
    """
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, *args]
    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        check=check,
        input=input_data,
    )


def wait_for_deployment(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    timeout_seconds: int = 120,
    poll_interval: int = 5,
) -> bool:
    """Wait for a deployment to be ready.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        deployment: Deployment name
        timeout_seconds: Maximum wait time
        poll_interval: Seconds between checks

    Returns:
        True if deployment is ready, False if timeout
    """
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = run_kubectl(
            kubeconfig,
            namespace,
            ["rollout", "status", f"deployment/{deployment}", "--timeout=0"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return True
        time.sleep(poll_interval)
    return False


def collect_pod_logs(
    kubeconfig: str,
    namespace: str,
    pod_prefix: str,
    container: str | None = None,
    lines: int = 100,
) -> str:
    """Collect logs from a pod matching a prefix.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        pod_prefix: Prefix of pod name to match
        container: Optional container name
        lines: Number of log lines to fetch

    Returns:
        Log output as string
    """
    # Find pod
    result = run_kubectl(
        kubeconfig,
        namespace,
        ["get", "pods", "-o", "jsonpath={.items[*].metadata.name}"],
        capture_output=True,
        check=True,
    )
    pod_name = None
    for name in result.stdout.strip().split():
        if name.startswith(pod_prefix):
            pod_name = name
            break

    if not pod_name:
        return f"No pod found with prefix: {pod_prefix}"

    args = ["logs", f"pod/{pod_name}", f"--tail={lines}"]
    if container:
        args.extend(["-c", container])

    result = run_kubectl(
        kubeconfig,
        namespace,
        args,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr


def wait_for_condition(
    kubeconfig: str,
    namespace: str,
    resource_type: str,
    name: str,
    condition: str,
    timeout_seconds: int = 60,
    poll_interval: int = 2,
) -> bool:
    """Wait for a condition to be true on a resource.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        resource_type: Resource type (e.g., "pod", "deployment")
        name: Resource name
        condition: Condition to wait for (e.g., "Ready")
        timeout_seconds: Maximum wait time
        poll_interval: Seconds between checks

    Returns:
        True if condition is met, False if timeout
    """
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = run_kubectl(
            kubeconfig,
            namespace,
            [
                "get",
                resource_type,
                name,
                "-o",
                f"jsonpath={{.status.conditions[?(@.type=='{condition}')].status}}",
            ],
            capture_output=True,
            check=False,
        )
        if result.stdout.strip() == "True":
            return True
        time.sleep(poll_interval)
    return False


def port_forward(
    kubeconfig: str,
    namespace: str,
    resource_type: str,
    name: str,
    local_port: int,
    target_port: int,
) -> subprocess.Popen[str]:
    """Start a port-forward to a resource.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        resource_type: Resource type (e.g., "svc", "pod")
        name: Resource name
        local_port: Local port to listen on
        target_port: Target port on the resource

    Returns:
        Popen process (caller must terminate)
    """
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "-n",
        namespace,
        "port-forward",
        f"{resource_type}/{name}",
        f"{local_port}:{target_port}",
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def create_namespace(
    kubeconfig: str,
    namespace: str,
    labels: dict[str, str] | None = None,
) -> bool:
    """Create a namespace if it doesn't exist.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Namespace name
        labels: Optional labels to apply

    Returns:
        True if created, False if already exists
    """
    # Check if namespace exists
    result = run_kubectl(
        kubeconfig,
        "",
        ["get", "namespace", namespace],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return False

    # Create namespace
    args = ["create", "namespace", namespace]
    if labels:
        for k, v in labels.items():
            args.extend(["--dry-run=client", "-o", "yaml"])
            yaml_cmd = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig, *args],
                capture_output=True,
                text=True,
                check=True,
            )
            import yaml

            ns_doc = yaml.safe_load(yaml_cmd.stdout)
            ns_doc["metadata"]["labels"] = labels
            print(f"Creating namespace with labels: {labels}")

    run_kubectl(kubeconfig, "", args, check=True)
    return True


def apply_manifest(
    kubeconfig: str,
    namespace: str,
    manifest: str,
) -> bool:
    """Apply a Kubernetes manifest.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Namespace context
        manifest: YAML manifest content

    Returns:
        True if successful
    """
    result = run_kubectl(
        kubeconfig,
        namespace,
        ["apply", "-f", "-"],
        capture_output=True,
        check=False,
        input_data=manifest,
    )
    return result.returncode == 0


def delete_manifest(
    kubeconfig: str,
    namespace: str,
    manifest: str,
) -> bool:
    """Delete a Kubernetes manifest.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Namespace context
        manifest: YAML manifest content

    Returns:
        True if successful
    """
    result = run_kubectl(
        kubeconfig,
        namespace,
        ["delete", "-f", "-", "--ignore-not-found"],
        capture_output=True,
        check=False,
        input_data=manifest,
    )
    return result.returncode == 0


def get_deployment_status(
    kubeconfig: str,
    namespace: str,
    deployment: str,
) -> dict[str, Any]:
    """Get deployment status including available replicas.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        deployment: Deployment name

    Returns:
        Dict with status information
    """
    result = run_kubectl(
        kubeconfig,
        namespace,
        [
            "get",
            "deployment",
            deployment,
            "-o",
            "jsonpath={.status}",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {"availableReplicas": 0, "readyReplicas": 0}

    import yaml

    return yaml.safe_load(result.stdout) if result.stdout.strip() else {}


def check_service_endpoint(
    kubeconfig: str,
    namespace: str,
    service: str,
) -> str | None:
    """Get service cluster IP.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        service: Service name

    Returns:
        Cluster IP or None
    """
    result = run_kubectl(
        kubeconfig,
        namespace,
        ["get", "svc", service, "-o", "jsonpath={.spec.clusterIP}"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None

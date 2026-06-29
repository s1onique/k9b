"""Rollout monitoring for k9b baseline installer.

Provides functions for monitoring deployment rollouts and classifying failures.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .k9b_lab_common_helpers import log, write_text_artifact


def wait_for_rollout(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    timeout_seconds: int,
    artifact_dir: Path,
) -> dict:
    """Wait for deployment rollout using kubectl rollout status."""
    log(f"Waiting for deployment/{deployment} in {namespace}")
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig, "-n", namespace,
        "rollout", "status", f"deployment/{deployment}",
        f"--timeout={timeout_seconds}s",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds + 30)
        if proc.returncode == 0:
            return {"success": True, "message": f"{deployment} rollout complete", "failure_class": None}
        failure_class = classify_rollout_failure(kubeconfig, namespace, deployment)
        return {"success": False, "message": f"{deployment} rollout failed: {proc.stderr[:200]}", "failure_class": failure_class}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"Rollout timed out after {timeout_seconds}s", "failure_class": "rollout_timeout"}
    except Exception as e:
        return {"success": False, "message": f"Rollout check failed: {e}", "failure_class": "rollout_check_error"}


def classify_rollout_failure(kubeconfig: str, namespace: str, deployment: str) -> str:
    """Classify rollout failure by inspecting deployment state."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, "get", "pods", "-o", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        try:
            pods = json.loads(result.stdout)
            for pod in pods.get("items", []):
                status = pod.get("status", {})
                phase = status.get("phase", "")
                for cs in status.get("containerStatuses", []):
                    state = cs.get("state", {})
                    if "waiting" in state:
                        reason = state["waiting"].get("reason", "")
                        if reason == "ImagePullBackOff":
                            return "image_pull_backoff"
                        if reason == "ErrImagePull":
                            return "image_pull_failed"
                        if reason == "CrashLoopBackOff":
                            return "pod_crash_loop"
                        if reason == "ContainerCreating":
                            return "pod_pending"
                if phase == "Pending":
                    return "pod_pending"
        except json.JSONDecodeError:
            pass

    deploy_result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, "get", "deployment", deployment, "-o", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if deploy_result.returncode == 0:
        try:
            deploy = json.loads(deploy_result.stdout)
            for cond in deploy.get("status", {}).get("conditions", []):
                # Kubernetes Deployment ProgressDeadlineExceeded condition:
                # type="Progressing", status="False", reason="ProgressDeadlineExceeded"
                if (
                    cond.get("type") == "Progressing"
                    and cond.get("status") == "False"
                    and cond.get("reason") == "ProgressDeadlineExceeded"
                ):
                    return "deployment_progress_deadline"
                if cond.get("type") == "ReplicaFailure":
                    return "deployment_replica_failure"
        except json.JSONDecodeError:
            pass
    return "rollout_unknown"


def collect_rollout_failure_evidence(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    artifact_dir: Path,
) -> None:
    """Collect comprehensive evidence on rollout failure."""
    from .k9b_lab_baseline_helpers import run_kubectl_collector
    log("Collecting rollout failure evidence")
    run_kubectl_collector(kubeconfig, namespace, artifact_dir, [
        ("pods.json", ["get", "pods", "-o", "json"]),
        ("services.json", ["get", "services", "-o", "json"]),
        ("deployments.json", ["get", "deployments", "-o", "json"]),
        ("endpoints.json", ["get", "endpoints", "-o", "json"]),
        ("events.txt", ["get", "events", "--sort-by=.lastTimestamp"]),
    ])

    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace,
         "describe", "deployment", backend_deployment],
        capture_output=True, text=True, timeout=15,
    )
    write_text_artifact(artifact_dir, "describe-deployment.txt", result.stdout)

    pods_result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, "get", "pods", "-o", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if pods_result.returncode == 0:
        try:
            pods = json.loads(pods_result.stdout)
            for pod in pods.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "")
                for cs in pod.get("status", {}).get("containerStatuses", []):
                    container = cs.get("name", "")
                    if not container:
                        continue
                    logs = subprocess.run(
                        ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace,
                         "logs", f"pod/{pod_name}", "-c", container],
                        capture_output=True, text=True, timeout=15,
                    )
                    if logs.stdout:
                        write_text_artifact(artifact_dir, f"pod-log-{pod_name}-{container}.txt", logs.stdout)
                    if cs.get("restartCount", 0) > 0:
                        prev = subprocess.run(
                            ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace,
                             "logs", f"pod/{pod_name}", "-c", container, "--previous"],
                            capture_output=True, text=True, timeout=15,
                        )
                        if prev.stdout:
                            write_text_artifact(artifact_dir, f"pod-prev-log-{pod_name}-{container}.txt", prev.stdout)
        except json.JSONDecodeError:
            pass

"""Helm operations for k9b baseline installer.

Provides functions for rendering, installing Helm charts, and collecting
Helm evidence artifacts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import write_json_artifact, write_text_artifact


def render_manifest(
    chart_path: str,
    values_path: str | None,
    namespace: str,
    release_name: str,
    artifact_dir: Path,
    set_values: list[str] | None = None,
    set_string_values: list[str] | None = None,
) -> dict[str, Any]:
    """Render Helm manifest and collect evidence.

    Args:
        chart_path: Path to Helm chart directory
        values_path: Path to values file
        namespace: Kubernetes namespace
        release_name: Helm release name
        artifact_dir: Directory for evidence artifacts
        set_values: List of --set values (e.g., ["image.backend.repository=foo", "image.backend.tag=v1"])
        set_string_values: List of --set-string values (e.g., ["diagnosisProvider.baseUrl=https://example.invalid"])
    """
    result: dict[str, Any] = {"success": False, "error": None, "manifest_path": None}
    cmd = ["helm", "template", release_name, chart_path]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_path:
        cmd.extend(["--values", values_path])
    if set_values:
        for sv in set_values:
            cmd.extend(["--set", sv])
    if set_string_values:
        for sv in set_string_values:
            cmd.extend(["--set-string", sv])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        write_text_artifact(artifact_dir, "rendered-manifest-exit-code.txt", str(proc.returncode))
        if proc.stderr:
            write_text_artifact(artifact_dir, "rendered-manifest-stderr.log", proc.stderr)
        if proc.returncode == 0:
            path = write_text_artifact(artifact_dir, "rendered-manifest.yaml", proc.stdout)
            result["success"] = True
            result["manifest_path"] = str(path)
        else:
            result["error"] = f"helm template failed: {proc.stderr[:200]}"
    except subprocess.TimeoutExpired:
        result["error"] = "helm template timed out"
    except Exception as e:
        result["error"] = f"Failed to render manifest: {e}"
    return result


def install_helm(
    kubeconfig: str,
    chart_path: str,
    values_path: str | None,
    namespace: str,
    release_name: str,
    artifact_dir: Path,
    set_values: list[str] | None = None,
    set_string_values: list[str] | None = None,
) -> dict[str, Any]:
    """Install/upgrade Helm release.

    Args:
        kubeconfig: Path to kubeconfig file
        chart_path: Path to Helm chart directory
        values_path: Path to values file
        namespace: Kubernetes namespace
        release_name: Helm release name
        artifact_dir: Directory for evidence artifacts
        set_values: List of --set values (e.g., ["image.backend.repository=foo", "image.backend.tag=v1"])
        set_string_values: List of --set-string values (e.g., ["diagnosisProvider.baseUrl=https://example.invalid"])
    """
    result: dict[str, Any] = {"returncode": -1, "stdout": "", "stderr": ""}
    cmd = [
        "helm", "upgrade", "--install", release_name, chart_path,
        "--kubeconfig", kubeconfig, "--namespace", namespace,
        "--create-namespace", "--wait=false",
    ]
    if values_path:
        cmd.extend(["--values", values_path])
    if set_values:
        for sv in set_values:
            cmd.extend(["--set", sv])
    if set_string_values:
        for sv in set_string_values:
            cmd.extend(["--set-string", sv])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        if proc.stdout:
            write_text_artifact(artifact_dir, "install-output.log", proc.stdout)
        if proc.stderr:
            write_text_artifact(artifact_dir, "install-stderr.log", proc.stderr)
        write_text_artifact(artifact_dir, "install-exit-code.txt", str(proc.returncode))
    except subprocess.TimeoutExpired:
        result["stderr"] = "helm upgrade timed out"
    except Exception as e:
        result["stderr"] = f"Failed to install helm: {e}"
    return result


def collect_helm_evidence(
    kubeconfig: str,
    namespace: str,
    release_name: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Collect Helm status, history, manifest, and values evidence."""
    evidence: dict[str, Any] = {"collected": [], "errors": []}

    def run_helm(args: list[str]) -> tuple[bool, str]:
        cmd = ["helm", "--kubeconfig", kubeconfig, "--namespace", namespace] + args
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return proc.returncode == 0, proc.stdout
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def safe_json(text: str) -> Any:
        import json
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    success, output = run_helm(["status", release_name, "-o", "json"])
    if success:
        write_json_artifact(artifact_dir, "status.json", safe_json(output) or {})
        evidence["collected"].append("status.json")
    else:
        evidence["errors"].append(f"helm status failed: {output}")

    success, output = run_helm(["history", release_name, "-o", "json"])
    if success:
        hist = safe_json(output)
        if isinstance(hist, list):
            write_json_artifact(artifact_dir, "history.json", {"history": hist})
            evidence["collected"].append("history.json")
        else:
            write_json_artifact(artifact_dir, "history.json", {"history": []})
            evidence["errors"].append("helm history returned non-list data")
    else:
        evidence["errors"].append(f"helm history failed: {output}")

    success, output = run_helm(["get", "manifest", release_name])
    if success:
        write_text_artifact(artifact_dir, "get-manifest.yaml", output)
        evidence["collected"].append("get-manifest.yaml")
    else:
        evidence["errors"].append(f"helm get manifest failed: {output}")

    success, output = run_helm(["get", "values", release_name, "-o", "json"])
    if success:
        write_json_artifact(artifact_dir, "get-values.json", safe_json(output) or {})
        evidence["collected"].append("get-values.json")

    success, output = run_helm(["get", "values", release_name, "-o", "yaml"])
    if success:
        write_text_artifact(artifact_dir, "get-values.yaml", output)
        evidence["collected"].append("get-values.yaml")

    return evidence


def collect_helm_failure_evidence(
    kubeconfig: str,
    namespace: str,
    release_name: str,
    artifact_dir: Path,
) -> None:
    """Collect evidence when Helm install fails."""
    from .k9b_lab_baseline_helpers import run_kubectl_collector
    from .k9b_lab_common_helpers import log
    log("Collecting Helm failure evidence")
    result = subprocess.run(
        ["helm", "--kubeconfig", kubeconfig, "--namespace", namespace, "status", release_name],
        capture_output=True, text=True, timeout=15,
    )
    write_text_artifact(artifact_dir, "helm-status-on-failure.txt", result.stdout or result.stderr)
    run_kubectl_collector(kubeconfig, namespace, artifact_dir, [
        ("failure-pods.json", ["get", "pods", "-o", "json"]),
        ("failure-events.txt", ["get", "events", "--sort-by=.lastTimestamp"]),
    ])

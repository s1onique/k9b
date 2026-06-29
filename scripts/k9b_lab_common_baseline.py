"""Common k9b baseline installer for live labs.

This module provides a reusable function for installing and verifying the k9b
Helm chart with proper evidence collection and rollout monitoring.

Both CNPG and OTel demo labs should use ensure_k9b_baseline_ready() instead of
direct helm upgrade calls.

Evidence collected on success and failure:
- helm/rendered-manifest.yaml (pre-deploy manifest render)
- helm/status.json (Helm release status)
- helm/history.json (Helm release history)
- helm/get-manifest.yaml (installed manifest)
- helm/get-values.yaml (installed values)
- helm/install-output.log (helm stdout)
- helm/install-stderr.log (helm stderr)
- helm/install-exit-code.txt (helm exit code)
- rollout-watch/ (proactive rollout monitoring)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import log
from .k9b_lab_helm import collect_helm_evidence, collect_helm_failure_evidence, install_helm, render_manifest
from .k9b_lab_rollout import collect_rollout_failure_evidence, wait_for_rollout


def ensure_k9b_baseline_ready(
    lab_name: str,
    release_name: str,
    namespace: str,
    chart_path: Path,
    artifact_dir: Path,
    kubeconfig: str,
    values_path: Path | None = None,
    backend_deployment: str = "k9b-backend",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Install k9b baseline and verify backend deployment is ready.

    This function replaces minimal Helm install paths with a robust install
    pattern that collects evidence and monitors rollout.

    Args:
        lab_name: Lab identifier (e.g., "cnpg", "otel-demo")
        release_name: Helm release name (default: "k9b")
        namespace: Kubernetes namespace (default: "k9b")
        chart_path: Path to Helm chart directory
        artifact_dir: Directory to write evidence artifacts
        kubeconfig: Path to kubeconfig file
        values_path: Path to values file (default: chart_path/values-live-lab.yaml)
        backend_deployment: Name of the backend deployment to wait for
        timeout_seconds: Rollout timeout in seconds (default: 300)

    Returns:
        Dictionary with:
        - success: bool
        - message: str
        - artifacts: dict of artifact paths
        - failure_class: str or None
    """
    log(f"[{lab_name}] Installing k9b baseline")
    log(f"[{lab_name}] Release: {release_name}, Namespace: {namespace}")
    log(f"[{lab_name}] Chart: {chart_path}")

    # Default values path
    if values_path is None:
        values_path = chart_path / "values-live-lab.yaml"

    helm_dir = artifact_dir / "helm"
    helm_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "success": False,
        "message": "",
        "artifacts": {},
        "failure_class": None,
    }

    # Step 1: Collect rendered manifest evidence
    log(f"[{lab_name}] Step 1: Rendering Helm manifest")
    render_result = render_manifest(
        chart_path=str(chart_path),
        values_path=str(values_path) if values_path.exists() else None,
        namespace=namespace,
        release_name=release_name,
        artifact_dir=helm_dir,
    )
    results["artifacts"]["render_manifest"] = render_result

    if not render_result.get("success"):
        results["failure_class"] = "helm_render_failed"
        results["message"] = f"Helm render failed: {render_result.get('error', 'unknown')}"
        return results

    # Step 2: Install/upgrade Helm release
    log(f"[{lab_name}] Step 2: Installing Helm release")
    install_result = install_helm(
        kubeconfig=kubeconfig,
        chart_path=str(chart_path),
        values_path=str(values_path) if values_path.exists() else None,
        namespace=namespace,
        release_name=release_name,
        artifact_dir=helm_dir,
    )
    results["artifacts"]["helm_install"] = install_result

    if install_result.get("returncode", 0) != 0:
        results["failure_class"] = "helm_install_failed"
        results["message"] = f"Helm install failed: {install_result.get('stderr', '')[:200]}"
        collect_helm_failure_evidence(kubeconfig, namespace, release_name, helm_dir)
        return results

    # Step 3: Collect Helm evidence
    log(f"[{lab_name}] Step 3: Collecting Helm evidence")
    helm_evidence = collect_helm_evidence(
        kubeconfig=kubeconfig,
        namespace=namespace,
        release_name=release_name,
        artifact_dir=helm_dir,
    )
    results["artifacts"]["helm_evidence"] = helm_evidence

    # Step 4: Wait for backend rollout
    log(f"[{lab_name}] Step 4: Waiting for {backend_deployment} rollout")
    rollout_result = wait_for_rollout(
        kubeconfig=kubeconfig,
        namespace=namespace,
        deployment=backend_deployment,
        timeout_seconds=timeout_seconds,
        artifact_dir=artifact_dir,
    )

    if not rollout_result.get("success"):
        results["failure_class"] = rollout_result.get("failure_class", "rollout_timeout")
        results["message"] = rollout_result.get("message", "Rollout timeout")
        collect_rollout_failure_evidence(kubeconfig, namespace, backend_deployment, artifact_dir)
        return results

    log(f"[{lab_name}] k9b baseline ready: {backend_deployment} is Ready")
    results["success"] = True
    results["message"] = f"k9b baseline installed and {backend_deployment} is ready"
    return results

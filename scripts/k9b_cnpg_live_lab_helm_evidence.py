#!/usr/bin/env python3
"""Helm evidence collection for CNPG Live Lab.

This module captures Helm render, install, and release state evidence
for diagnosing deployment failures.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.k9b_cnpg_live_lab_helm_inventory import (
    parse_workload_inventory,
    write_workload_inventory,
)


def collect_helm_evidence(
    kubeconfig: str,
    namespace: str,
    release_name: str,
    artifact_dir: Path,
    helm_install_returncode: int | None = None,
    helm_install_stdout: str = "",
    helm_install_stderr: str = "",
) -> dict[str, Any]:
    """Collect Helm evidence after install/upgrade.

    Captures:
    - Helm status (JSON)
    - Helm history (JSON)
    - Helm get manifest
    - Helm get values (JSON)
    - Install output logs

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        release_name: Helm release name
        artifact_dir: Directory to write evidence files
        helm_install_returncode: Exit code from helm install/upgrade
        helm_install_stdout: Stdout from helm install/upgrade
        helm_install_stderr: Stderr from helm install/upgrade

    Returns:
        Dictionary with evidence collection results
    """
    helm_dir = artifact_dir / "helm"
    helm_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "release_name": release_name,
        "namespace": namespace,
        "evidence_artifacts": [],
        "helm_release_exists": False,
        "helm_release_status": None,
        "helm_release_revision": None,
        "helm_history": [],
        "errors": [],
    }

    # Write install output logs
    if helm_install_stdout or helm_install_stderr:
        _write_file(helm_dir / "install-output.log", helm_install_stdout)
        results["evidence_artifacts"].append("helm/install-output.log")

    if helm_install_stderr:
        _write_file(helm_dir / "install-stderr.log", helm_install_stderr)
        results["evidence_artifacts"].append("helm/install-stderr.log")

    if helm_install_returncode is not None:
        _write_file(helm_dir / "install-exit-code.txt", str(helm_install_returncode))
        results["evidence_artifacts"].append("helm/install-exit-code.txt")

    # Collect Helm status
    status_result = _run_helm_command(
        kubeconfig, namespace, release_name,
        ["status", release_name, "-o", "json"]
    )
    if status_result["success"]:
        _write_file(helm_dir / "status.json", status_result["stdout"])
        results["evidence_artifacts"].append("helm/status.json")
        results["helm_release_exists"] = True

        try:
            status_data = json.loads(status_result["stdout"])
            results["helm_release_status"] = status_data.get("info", {}).get("status", {}).get("status")
            results["helm_release_revision"] = status_data.get("info", {}).get("last_deployed", {}).get("Revision")
        except json.JSONDecodeError:
            pass
    else:
        _write_file(helm_dir / "status.json", status_result["stderr"])
        results["evidence_artifacts"].append("helm/status.json")
        results["errors"].append(f"helm status failed: {status_result['stderr']}")

    # Collect Helm history
    history_result = _run_helm_command(
        kubeconfig, namespace, release_name,
        ["history", release_name, "-o", "json"]
    )
    if history_result["success"]:
        _write_file(helm_dir / "history.json", history_result["stdout"])
        results["evidence_artifacts"].append("helm/history.json")

        try:
            history_data = json.loads(history_result["stdout"])
            results["helm_history"] = history_data
        except json.JSONDecodeError:
            pass
    else:
        _write_file(helm_dir / "history.json", history_result["stderr"])
        results["evidence_artifacts"].append("helm/history.json")
        results["errors"].append(f"helm history failed: {history_result['stderr']}")

    # Collect Helm get manifest
    manifest_result = _run_helm_command(
        kubeconfig, namespace, release_name,
        ["get", "manifest", release_name]
    )
    if manifest_result["success"]:
        _write_file(helm_dir / "get-manifest.yaml", manifest_result["stdout"])
        results["evidence_artifacts"].append("helm/get-manifest.yaml")
    else:
        _write_file(helm_dir / "get-manifest.yaml", manifest_result["stderr"])
        results["evidence_artifacts"].append("helm/get-manifest.yaml")
        results["errors"].append(f"helm get manifest failed: {manifest_result['stderr']}")

    # Collect Helm get values
    values_result = _run_helm_command(
        kubeconfig, namespace, release_name,
        ["get", "values", release_name, "-o", "json"]
    )
    if values_result["success"]:
        _write_file(helm_dir / "get-values.json", values_result["stdout"])
        results["evidence_artifacts"].append("helm/get-values.json")
    else:
        _write_file(helm_dir / "get-values.json", values_result["stderr"])
        results["evidence_artifacts"].append("helm/get-values.json")
        results["errors"].append(f"helm get values failed: {values_result['stderr']}")

    return results


def collect_rendered_manifest_evidence(
    chart_path: str | None,
    values_path: str | None,
    artifact_dir: Path,
    namespace: str = "",
    release_name: str = "k9b",
) -> dict[str, Any]:
    """Collect rendered manifest evidence using helm template.

    Args:
        chart_path: Path to Helm chart directory
        values_path: Path to values file
        artifact_dir: Directory to write evidence files
        namespace: Kubernetes namespace
        release_name: Release name

    Returns:
        Dictionary with rendered manifest evidence
    """
    helm_dir = artifact_dir / "helm"
    helm_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "rendered_manifest_captured": False,
        "rendered_manifest_path": None,
        "rendered_workload_inventory_path": None,
        "evidence_artifacts": [],
        "errors": [],
    }

    if not chart_path:
        results["errors"].append("No chart path provided for rendering")
        return results

    # Build helm template command
    cmd = ["helm", "template", release_name, chart_path]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_path:
        cmd.extend(["--values", values_path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Write render metadata (always - even on failure)
        _write_file(helm_dir / "rendered-manifest-exit-code.txt", str(result.returncode))
        results["evidence_artifacts"].append("helm/rendered-manifest-exit-code.txt")
        
        # Write stderr only if present
        if result.stderr:
            _write_file(helm_dir / "rendered-manifest-stderr.log", result.stderr)
            results["evidence_artifacts"].append("helm/rendered-manifest-stderr.log")

        # Only write rendered manifest when returncode is 0
        # This allows classifier to trust rendered-manifest.yaml only when exit code is 0
        if result.returncode == 0:
            _write_file(helm_dir / "rendered-manifest.yaml", result.stdout)
            results["rendered_manifest_captured"] = True
            results["rendered_manifest_path"] = "helm/rendered-manifest.yaml"
            results["evidence_artifacts"].append("helm/rendered-manifest.yaml")
            
            # Generate rendered workload inventory using public parser
            try:
                inventory = parse_workload_inventory(
                    result.stdout,
                    expected_name="k9b",
                    expected_namespace=namespace,
                )
                if inventory:
                    inventory_path = write_workload_inventory(artifact_dir, inventory)
                    results["rendered_workload_inventory_path"] = str(inventory_path.relative_to(artifact_dir))
                    results["evidence_artifacts"].append(str(inventory_path.relative_to(artifact_dir)))
            except Exception as e:
                results["errors"].append(f"Failed to generate inventory: {e}")
        else:
            results["rendered_manifest_captured"] = False
            results["errors"].append(f"helm template failed with exit code {result.returncode}")

    except subprocess.TimeoutExpired:
        results["errors"].append("helm template timed out")
        _write_file(helm_dir / "rendered-manifest-exit-code.txt", "-1")
        results["evidence_artifacts"].append("helm/rendered-manifest-exit-code.txt")
    except Exception as e:
        results["errors"].append(f"Failed to render manifest: {e}")

    return results


def _run_helm_command(
    kubeconfig: str,
    namespace: str,
    release_name: str,
    args: list[str],
) -> dict[str, Any]:
    """Run a Helm command and return the result.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        release_name: Helm release name
        args: Additional Helm command arguments

    Returns:
        Dictionary with success, stdout, stderr
    """
    cmd = [
        "helm",
        "--kubeconfig", kubeconfig,
        "--namespace", namespace,
    ] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }

def _write_file(path: Path, content: str) -> None:
    """Write content to file, creating parent directories.

    Args:
        path: File path
        content: Content to write
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")


def check_helm_release_failed(
    helm_history: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Check if Helm release failed before workload creation.

    Args:
        helm_history: List of history entries from helm history -o json

    Returns:
        Tuple of (is_failed, reason)
    """
    if not helm_history:
        return False, ""

    # Check most recent revision for failed status
    # History is sorted by revision, most recent last
    for entry in reversed(helm_history):
        status = entry.get("status", "").lower()
        if status in ("failed", "pending-install", "pending-upgrade", "pending-rollback"):
            revision = entry.get("revision", "?")
            return True, f"Release status '{status}' at revision {revision}"

    return False, ""

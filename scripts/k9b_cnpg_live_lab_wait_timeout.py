#!/usr/bin/env python3
"""Wait timeout classification for CNPG Live Lab.

This module provides the classify-wait-timeout CLI command implementation
that determines the specific cause when Helm wait times out.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from scripts.k9b_cnpg_live_lab_bootstrap_funcs import (
    _parse_crash_loop_from_pods,
    _parse_deployment_not_found,
    _parse_deployment_not_ready_from_deployments,
    _parse_image_pull_failure_from_pods,
    _parse_probe_failure_from_pods,
    _parse_pvc_pending_from_pods,
)
from scripts.k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from scripts.k9b_cnpg_live_lab_constants import (
    FAILURE_DEPLOYMENT_NOT_AVAILABLE,
    FAILURE_EXPECTED_WORKLOAD_MISSING,
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN,
    FAILURE_IMAGE_PULL_FAILED,
    FAILURE_POD_CRASH_LOOP,
    FAILURE_PROBE_FAILED,
    FAILURE_PVC_PENDING,
)
from scripts.k9b_cnpg_live_lab_helpers import (
    read_json,
)
from scripts.k9b_cnpg_live_lab_workload_missing_classify import (
    classify_expected_workload_missing,
)


def main_classify_wait_timeout() -> int:
    """Classify Helm wait timeout using watchdog artifacts."""
    parser = _create_wait_timeout_parser()
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    helm_log_path = Path(args.helm_log)
    namespace = args.namespace
    kubeconfig = args.kubeconfig or None

    # Read Helm log
    helm_output = _read_helm_log(helm_log_path)

    preflight = PreflightData(artifact_dir, namespace)
    diagnosis = DiagnosisGenerator(artifact_dir, namespace)

    # Read existing preflight to preserve context
    existing = read_json(artifact_dir / "lab-preflight.json")
    if existing:
        preflight.active_identity = existing.get("active_identity")
        preflight.namespace = existing.get("namespace", namespace)
        preflight.timestamp = existing.get("bootstrap_timestamp", preflight.timestamp)

    # Classify the failure
    failure_class, failure_subclass = _classify_failure(
        kubeconfig, namespace, artifact_dir, helm_log_path, helm_output, preflight, diagnosis
    )

    diagnosis.save()
    preflight.save()

    # Output classification to stdout
    output = failure_class
    if failure_subclass:
        output = f"{failure_class}::{failure_subclass}"
    print(output)
    return 0


def _create_wait_timeout_parser() -> argparse.ArgumentParser:
    """Create argument parser for classify-wait-timeout command."""
    import argparse

    parser = argparse.ArgumentParser(description="Classify Helm wait timeout")
    parser.add_argument(
        "--helm-log",
        default=os.environ.get("HELM_LOG", "./lab-artifacts/live/logs/helm-install.log"),
        help="Path to Helm install log (default: $HELM_LOG or ./lab-artifacts/live/logs/helm-install.log)",
    )
    parser.add_argument("--namespace", required=True, help="Namespace name")
    parser.add_argument(
        "--kubeconfig",
        default=os.environ.get("KUBECONFIG", ""),
        help="Path to kubeconfig",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    parser.add_argument(
        "--release-name",
        default="k9b",
        help="Helm release name (default: k9b)",
    )
    return parser


def _read_helm_log(helm_log_path: Path) -> str:
    """Read Helm log from file."""
    if helm_log_path.exists():
        return helm_log_path.read_text()
    return ""


def _classify_failure(
    kubeconfig: str | None,
    namespace: str,
    artifact_dir: Path,
    helm_log_path: Path,
    helm_output: str,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> tuple[str, str]:
    """Classify the wait timeout failure and update diagnosis.

    Returns:
        Tuple of (failure_class, failure_subclass)
    """
    failure_subclass = ""

    if kubeconfig and Path(kubeconfig).exists():
        failure_class, failure_subclass = _classify_with_cluster_state(
            kubeconfig, namespace, artifact_dir, helm_log_path, helm_output, preflight, diagnosis
        )
    else:
        failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Helm wait timed out without cluster state data.")
        diagnosis.text("**Evidence**: helm install log")

    return failure_class, failure_subclass


def _classify_with_cluster_state(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    helm_log_path: Path,
    helm_output: str,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> tuple[str, str]:
    """Classify failure when cluster state is available."""
    # Collect current state
    _collect_watchdog_artifacts(kubeconfig, namespace, artifact_dir)

    # Read collected artifacts
    pods_json = _read_artifact(artifact_dir / "watchdog/pods-final.json")
    deployments_json = _read_artifact(artifact_dir / "watchdog/deployments-final.json")
    events_text = _read_artifact(artifact_dir / "watchdog/events-final.txt")

    helm_lower = helm_output.lower()
    failure_subclass = ""

    # Priority order: most specific first
    if _parse_deployment_not_found(deployments_json):
        failure_class = FAILURE_EXPECTED_WORKLOAD_MISSING
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Expected Deployment was never observed before rollout deadline.")
        diagnosis.text("**Evidence**: watchdog/deployments-final.json (empty items list)")

        failure_subclass, subclass_diagnostics = _subclassify_workload_missing(
            artifact_dir, namespace, deployments_json, helm_output
        )

        diagnosis.text("")
        diagnosis.text(f"**Sub-classification**: `{failure_subclass}`")
        _report_subclass_diagnostics(diagnosis, subclass_diagnostics)

    elif _parse_crash_loop_from_pods(pods_json):
        failure_class = FAILURE_POD_CRASH_LOOP
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Pod containers are in CrashLoopBackOff state.")
        diagnosis.text("**Evidence**: watchdog/pods-final.json")

    elif _parse_image_pull_failure_from_pods(pods_json):
        failure_class = FAILURE_IMAGE_PULL_FAILED
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Container image could not be pulled.")
        diagnosis.text("**Evidence**: watchdog/pods-final.json")

    elif _parse_probe_failure_from_pods(pods_json):
        failure_class = FAILURE_PROBE_FAILED
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Container probe failed (exit code != 0).")
        diagnosis.text("**Evidence**: watchdog/pods-final.json")

    elif _parse_deployment_not_ready_from_deployments(deployments_json):
        failure_class = FAILURE_DEPLOYMENT_NOT_AVAILABLE
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Deployment has no available replicas.")
        diagnosis.text("**Evidence**: watchdog/deployments-final.json")

    elif _parse_pvc_pending_from_pods(pods_json, events_text):
        failure_class = FAILURE_PVC_PENDING
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: PVC is stuck in Pending state.")
        diagnosis.text("**Evidence**: watchdog/pods-final.json, watchdog/events-final.txt")

    elif "unknown field" in helm_lower:
        failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Helm chart has schema drift (unknown field warnings).")
        diagnosis.text("**Evidence**: helm install log")

    else:
        failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Helm wait timed out but specific cause not determined.")
        diagnosis.text("**Evidence**: Review watchdog/ artifacts for details.")

    diagnosis.text("")
    diagnosis.text(f"**Suggested action**: Review watchdog/ artifacts and {helm_log_path.name}")
    diagnosis.text("to determine the root cause of the timeout.")

    # Update preflight
    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"
        if failure_subclass:
            preflight.failure_reason = failure_subclass

    return failure_class, failure_subclass


def _collect_watchdog_artifacts(kubeconfig: str, namespace: str, artifact_dir: Path) -> None:
    """Collect kubectl artifacts for watchdog analysis."""
    kubectl_artifacts = [
        ("watchdog/pods-final.json", ["get", "pods", "-n", namespace, "-o", "json"]),
        ("watchdog/deployments-final.json", ["get", "deployments", "-n", namespace, "-o", "json"]),
        ("watchdog/events-final.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
    ]

    for filename, cmd in kubectl_artifacts:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig] + cmd,
            capture_output=True,
            text=True,
        )
        artifact_path = artifact_dir / filename
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(result.stdout or "(empty)", encoding="utf-8")


def _read_artifact(path: Path) -> str:
    """Read an artifact file, returning empty string if missing."""
    if path.exists():
        return path.read_text()
    return ""


def _subclassify_workload_missing(
    artifact_dir: Path,
    namespace: str,
    deployments_json: str,
    helm_output: str,
) -> tuple[str, dict]:
    """Sub-classify expected_workload_missing using render/apply evidence."""
    # Collect render metadata (trust check)
    render_exit_code = ""
    render_stderr = ""
    rendered_manifest = ""

    render_exit_code_path = artifact_dir / "helm" / "rendered-manifest-exit-code.txt"
    render_stderr_path = artifact_dir / "helm" / "rendered-manifest-stderr.log"

    if render_exit_code_path.exists():
        render_exit_code = render_exit_code_path.read_text().strip()

    if render_stderr_path.exists():
        render_stderr = render_stderr_path.read_text()

    # Only trust rendered manifest when exit code is 0
    if render_exit_code == "0":
        rendered_path = artifact_dir / "helm" / "rendered-manifest.yaml"
        if rendered_path.exists():
            rendered_manifest = rendered_path.read_text()
    # else: helm template failed - rendered manifest not trusted

    # Collect Helm install logs (trust check)
    install_stderr = ""

    install_stderr_path = artifact_dir / "helm" / "install-stderr.log"

    if install_stderr_path.exists():
        install_stderr = install_stderr_path.read_text()

    # Collect Helm evidence
    helm_status_json = _read_artifact(artifact_dir / "helm" / "status.json")
    helm_history_json = _read_artifact(artifact_dir / "helm" / "history.json")
    helm_values_json = _read_artifact(artifact_dir / "helm" / "get-values.json")

    # Run sub-classification
    failure_subclass, subclass_diagnostics = classify_expected_workload_missing(
        artifact_dir=artifact_dir,
        namespace=namespace,
        deployments_json=deployments_json,
        helm_install_stdout=helm_output,
        helm_install_stderr=install_stderr,
        helm_status_json=helm_status_json,
        helm_history_json=helm_history_json,
        helm_values_json=helm_values_json,
        rendered_manifest_yaml=rendered_manifest,
    )

    # Add render failure info to diagnostics if template failed
    if render_exit_code and render_exit_code != "0":
        subclass_diagnostics["render_failed"] = True
        subclass_diagnostics["render_exit_code"] = render_exit_code
        if render_stderr:
            subclass_diagnostics["render_stderr_preview"] = render_stderr[:500]

    return failure_subclass, subclass_diagnostics


def _report_subclass_diagnostics(diagnosis: DiagnosisGenerator, subclass_diagnostics: dict) -> None:
    """Report subclassification diagnostics to diagnosis object."""
    if subclass_diagnostics.get("rendered_manifest_captured"):
        rendered_deployment_present = subclass_diagnostics.get("rendered_deployment_present", False)
        cluster_deployment_present = subclass_diagnostics.get("cluster_deployment_present", False)
        diagnosis.text(f"**Rendered manifest captured**: {rendered_deployment_present}")
        diagnosis.text(f"**Cluster deployment present**: {cluster_deployment_present}")

        if subclass_diagnostics.get("evidence_artifacts"):
            artifacts = subclass_diagnostics["evidence_artifacts"]
            diagnosis.text(f"**Evidence artifacts**: {', '.join(artifacts)}")

    # Add Helm release status if available (from classify_expected_workload_missing)
    helm_release_exists = subclass_diagnostics.get("helm_release_exists")
    helm_release_status = subclass_diagnostics.get("helm_release_status")
    if helm_release_status:
        diagnosis.text(f"**Helm release status**: {helm_release_status}")
        if helm_release_exists is not None:
            diagnosis.text(f"**Helm release exists**: {helm_release_exists}")

    # Add render failure note if helm template failed
    if subclass_diagnostics.get("render_failed"):
        render_exit_code = subclass_diagnostics.get("render_exit_code", "unknown")
        diagnosis.text(f"**Helm template failed**: exit code {render_exit_code}")
        render_stderr_preview = subclass_diagnostics.get("render_stderr_preview", "")
        if render_stderr_preview:
            diagnosis.text(f"**Render stderr preview**: {render_stderr_preview[:200]}...")


if __name__ == "__main__":
    raise SystemExit(main_classify_wait_timeout())

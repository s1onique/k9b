#!/usr/bin/env python3
"""OTel Demo Lab deployment phases.

Contains phase 0 (cluster baseline), phase 1 (Helm deploy), and
phase 1b (baseline readiness).
"""

from __future__ import annotations

import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import (
    kubectl_events,
    kubectl_json,
    log,
    write_json_artifact,
    write_text_artifact,
)
from .k9b_lab_common_readiness import (
    collect_namespace_snapshot,
    wait_for_deployments_ready,
)
from .k9b_otel_demo_lab_constants import (
    FAILURE_CLUSTER_API_TIMEOUT,
    PHASE_CLUSTER_BASELINE,
    PHASE_OTEL_BASELINE,
    REQUIRED_DEPLOYMENTS,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult

# Patterns that indicate cluster_api_timeout
_CLUSTER_API_TIMEOUT_PATTERNS = [
    re.compile(r"i/o timeout", re.IGNORECASE),
    re.compile(r"dial tcp.*timeout", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"no route to host", re.IGNORECASE),
    re.compile(r"network is unreachable", re.IGNORECASE),
]


def _classify_connectivity_error(error_output: str) -> str | None:
    """Classify a kubectl connectivity error.

    Returns the failure class string if classified, None otherwise.
    """
    if not error_output:
        return None

    for pattern in _CLUSTER_API_TIMEOUT_PATTERNS:
        if pattern.search(error_output):
            return FAILURE_CLUSTER_API_TIMEOUT

    # Generic check for timeout keywords
    if "timeout" in error_output.lower():
        return FAILURE_CLUSTER_API_TIMEOUT

    return None


def phase0_cluster_baseline(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 0: Collect cluster and k9b baseline.

    Classifies cluster_api_timeout when kubectl commands fail with TCP-level
    connectivity errors (e.g., dial tcp ... i/o timeout).
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_CLUSTER_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {}
    failure_class: str | None = None
    failure_reason: str | None = None

    # Get cluster nodes with connectivity classification
    nodes_result = kubectl_json(config.kubeconfig, "nodes")
    if nodes_result.success and nodes_result.data:
        nodes_path = write_json_artifact(phase_dir, "nodes.json", nodes_result.data)
        artifacts["nodes"] = str(nodes_path)
    else:
        # Check for connectivity errors
        error_output = nodes_result.stderr or nodes_result.stdout
        failure_class = _classify_connectivity_error(error_output)
        if failure_class:
            failure_reason = f"API server unreachable: {error_output[:200]}"
            log(f"Phase 0 connectivity failure classified as: {failure_class}")

    # Get namespaces (only if nodes succeeded - avoid redundant failures)
    if not failure_class:
        ns_result = kubectl_json(config.kubeconfig, "namespaces")
        if ns_result.success and ns_result.data:
            ns_path = write_json_artifact(phase_dir, "namespaces.json", ns_result.data)
            artifacts["namespaces"] = str(ns_path)
        else:
            error_output = ns_result.stderr or ns_result.stdout
            failure_class = _classify_connectivity_error(error_output)
            if failure_class:
                failure_reason = f"API server unreachable: {error_output[:200]}"

    # Get k9b pods if it exists
    if not failure_class:
        k9b_ns = "k9b"  # k9b namespace
        k9b_result = kubectl_json(config.kubeconfig, "pods", k9b_ns)
        if k9b_result.success and k9b_result.data:
            k9b_path = write_json_artifact(phase_dir, "k9b-pods.json", k9b_result.data)
            artifacts["k9b_pods"] = str(k9b_path)

        # Get k9b service
        k9b_svc_result = kubectl_json(config.kubeconfig, "services", k9b_ns)
        if k9b_svc_result.success and k9b_svc_result.data:
            k9b_svc_path = write_json_artifact(phase_dir, "k9b-service.json", k9b_svc_result.data)
            artifacts["k9b_service"] = str(k9b_svc_path)

    # Write connectivity failure artifact if classified
    if failure_class:
        connectivity_result = {
            "failure_class": failure_class,
            "failure_reason": failure_reason,
            "phase": PHASE_CLUSTER_BASELINE,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        connectivity_path = write_json_artifact(phase_dir, "connectivity-failure.json", connectivity_result)
        artifacts["connectivity_failure"] = str(connectivity_path)

    duration = time.time() - start

    # Return failure result if connectivity error classified
    if failure_class:
        return LabPhaseResult(
            phase=PHASE_CLUSTER_BASELINE,
            success=False,
            message=f"Cluster connectivity failed: {failure_class}",
            artifacts=artifacts,
            duration_seconds=duration,
        )

    return LabPhaseResult(
        phase=PHASE_CLUSTER_BASELINE,
        success=True,
        message=f"Cluster baseline collected: {len(artifacts)} artifacts",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase1_deploy_otel_demo(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Phase 1: Deploy OpenTelemetry Demo via Helm."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_OTEL_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)

    log(f"Adding Helm repo: {config.helm_repo_name} -> {config.helm_repo_url}")

    # Add Helm repo with proper URL
    add_repo_cmd = ["helm", "repo", "add", config.helm_repo_name, config.helm_repo_url]
    result = subprocess.run(add_repo_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return LabPhaseResult(
            phase=PHASE_OTEL_BASELINE,
            success=False,
            message=f"Failed to add Helm repo: {result.stderr}",
            duration_seconds=time.time() - start,
        )

    # Update Helm repos
    subprocess.run(["helm", "repo", "update"], capture_output=True)

    # Write Helm install log
    helm_log_path = phase_dir / "helm-install.log"

    # Install OTel Demo using chart reference
    install_cmd = [
        "helm", "upgrade", "--install", config.helm_release,
        config.helm_chart,
        "--namespace", config.namespace,
        "--create-namespace",
        "--version", config.helm_chart_version,
        "--values", "-",  # Use stdin for values
    ]

    # Minimal values to enable feature flags
    values = """
recommendation:
  featureFlags:
    - name: recommendationServiceCacheFailure
      enabled: false
flagd:
  enabled: true
"""

    log(f"Installing OTel Demo to namespace {config.namespace}")
    log(f"Command: {' '.join(install_cmd)}")

    result = subprocess.run(
        install_cmd,
        input=values,
        capture_output=True,
        text=True,
    )

    helm_log_path.write_text(result.stdout + "\n" + result.stderr)

    artifacts = {
        "helm_install_log": str(helm_log_path),
        "helm_returncode": result.returncode,
    }

    if result.returncode != 0:
        return LabPhaseResult(
            phase=PHASE_OTEL_BASELINE,
            success=False,
            message=f"Helm install failed: {result.stderr[:500]}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )

    log("OTel Demo Helm installation completed")

    duration = time.time() - start
    return LabPhaseResult(
        phase=PHASE_OTEL_BASELINE,
        success=True,
        message="OTel Demo deployed successfully",
        artifacts=artifacts,
        duration_seconds=duration,
    )


def phase1b_baseline_readiness(config: LabConfig, artifact_dir: Path) -> LabPhaseResult:
    """Wait for OTel Demo baseline to be ready and collect artifacts."""
    start = time.time()
    phase_dir = artifact_dir / PHASE_OTEL_BASELINE
    phase_dir.mkdir(parents=True, exist_ok=True)

    log(f"Waiting for {len(REQUIRED_DEPLOYMENTS)} deployments to be ready...")

    # Wait for deployments
    ready, status = wait_for_deployments_ready(
        config.kubeconfig,
        config.namespace,
        REQUIRED_DEPLOYMENTS,
        timeout_seconds=config.readiness_timeout,
        poll_interval=config.readiness_poll_interval,
    )

    artifacts: dict[str, Any] = {}

    if not ready:
        # Collect state for diagnosis
        collect_namespace_snapshot(
            config.kubeconfig,
            config.namespace,
            phase_dir,
            include_previous_logs=True,
        )

        return LabPhaseResult(
            phase="phase1-baseline",
            success=False,
            message=f"Readiness timeout: {status}",
            artifacts=artifacts,
            duration_seconds=time.time() - start,
        )

    log("Baseline deployments are ready")

    # Collect baseline artifacts
    pods_result = kubectl_json(config.kubeconfig, "pods", config.namespace)
    if pods_result.success and pods_result.data:
        pods_path = write_json_artifact(phase_dir, "pods.json", pods_result.data)
        artifacts["pods"] = str(pods_path)

    deploy_result = kubectl_json(config.kubeconfig, "deployments", config.namespace)
    if deploy_result.success and deploy_result.data:
        deploy_path = write_json_artifact(phase_dir, "deployments.json", deploy_result.data)
        artifacts["deployments"] = str(deploy_path)

    svc_result = kubectl_json(config.kubeconfig, "services", config.namespace)
    if svc_result.success and svc_result.data:
        svc_path = write_json_artifact(phase_dir, "services.json", svc_result.data)
        artifacts["services"] = str(svc_path)

    events_result = kubectl_events(config.kubeconfig, config.namespace)
    if events_result.success:
        events_path = write_text_artifact(phase_dir, "events.txt", events_result.stdout)
        artifacts["events"] = str(events_path)

    # Write readiness result
    readiness_result = {
        "success": True,
        "message": status,
        "deployments_checked": len(REQUIRED_DEPLOYMENTS),
        "deployments": REQUIRED_DEPLOYMENTS,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    readiness_path = write_json_artifact(phase_dir, "readiness-result.json", readiness_result)
    artifacts["readiness_result"] = str(readiness_path)

    duration = time.time() - start
    return LabPhaseResult(
        phase="phase1-baseline",
        success=True,
        message=f"Baseline ready: {status}",
        artifacts=artifacts,
        duration_seconds=duration,
    )

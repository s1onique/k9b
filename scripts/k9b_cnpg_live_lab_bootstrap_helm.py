#!/usr/bin/env python3
"""Helm error classification functions for CNPG Live Lab.

This module contains Helm error classification logic for schema errors,
wait timeouts, and other Helm failures.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .k9b_cnpg_live_lab_bootstrap_parse import (
    _parse_crash_loop_from_pods,
    _parse_deployment_not_found,
    _parse_deployment_not_ready_from_deployments,
    _parse_image_pull_failure_from_pods,
    _parse_probe_failure_from_pods,
    _parse_pvc_pending_from_pods,
)
from .k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from .k9b_cnpg_live_lab_constants import (
    FAILURE_CNPG_CRD_MISSING,
    FAILURE_DEPLOYMENT_NOT_AVAILABLE,
    FAILURE_EXPECTED_WORKLOAD_MISSING,
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED,
    FAILURE_HELM_RBAC_DENIED,
    FAILURE_HELM_UNKNOWN,
    FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN,
    FAILURE_IMAGE_PULL_FAILED,
    FAILURE_POD_CRASH_LOOP,
    FAILURE_PROBE_FAILED,
    FAILURE_PVC_PENDING,
    FAILURE_STORAGE_OR_CAPACITY,
    FAILURE_WORKLOAD_NOT_READY,
)


def classify_schema_error(
    output: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> str:
    """Classify Kubernetes schema/dry-run error and return failure class."""
    diagnosis.heading(2, "Helm Manifest Schema Classification")

    failure_class = FAILURE_HELM_UNKNOWN
    output_lower = output.lower()

    # Schema warning - "unknown field" pattern
    unknown_field_patterns = [
        r"unknown field",
        r"spec\.template\.spec\.containers\[0\]\.(allowPrivilegeEscalation|capabilities|limits|requests|readOnlyRootFilesystem)",
    ]
    has_unknown_field = any(re.search(p, output_lower) for p in unknown_field_patterns)
    if has_unknown_field:
        failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart renders container security/resource fields")
        diagnosis.text("at the wrong level (directly under containers[0]) instead of nested under")
        diagnosis.text("securityContext or resources.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Common mistakes')}:")
        diagnosis.text("- `allowPrivilegeEscalation: false` should be `securityContext.allowPrivilegeEscalation: false`")
        diagnosis.text("- `capabilities:` should be `securityContext.capabilities:`")
        diagnosis.text("- `limits:`/`requests:` should be `resources.limits:`/`resources.requests:`")
        diagnosis.text("- `readOnlyRootFilesystem: true` should be `securityContext.readOnlyRootFilesystem: true`")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-rendered.yaml")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Fix chart templates to nest securityContext/resources fields.")

    # Server dry-run validation failed
    elif any(pattern in output_lower for pattern in [
        "error: error validating",
        "error validating data",
        "dry-run failed",
        "validation failed",
    ]):
        failure_class = FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Server-side dry-run validation failed for rendered manifests.")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-server-dry-run.log")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review rendered manifests and fix schema issues.")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Unknown manifest validation error.")

    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"

    preflight.save()
    diagnosis.save()
    return failure_class


def classify_wait_timeout(
    helm_output: str,
    kubeconfig: str | None,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> str:
    """Classify Helm wait timeout using JSON-based parser helpers."""
    diagnosis.heading(2, "Helm Wait Timeout Classification")

    failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN

    if kubeconfig and namespace:
        # Collect kubectl artifacts
        kubectl_artifacts = [
            ("watchdog/pods.txt", ["get", "pods", "-n", namespace, "-o", "wide"]),
            ("watchdog/deployments.txt", ["get", "deployments", "-n", namespace, "-o", "wide"]),
            ("watchdog/events.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
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

        # Get JSON for proper parsing
        pods_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
        )
        deployments_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "deployments", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
        )
        events_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace, "--sort-by=.lastTimestamp"],
            capture_output=True,
            text=True,
        )

        pods_json = pods_result.stdout
        deployments_json = deployments_result.stdout
        events_text = events_result.stdout
        helm_lower = helm_output.lower()

        # Use JSON-based parsers for accurate detection
        # Check for expected workload missing first (primary failure indicator)
        if _parse_deployment_not_found(deployments_json):
            failure_class = FAILURE_EXPECTED_WORKLOAD_MISSING
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Expected Deployment was never observed before rollout deadline.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/deployments.txt (empty items list)")

        elif _parse_crash_loop_from_pods(pods_json):
            failure_class = FAILURE_POD_CRASH_LOOP
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Pod is in CrashLoopBackOff state.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_image_pull_failure_from_pods(pods_json):
            failure_class = FAILURE_IMAGE_PULL_FAILED
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Container image could not be pulled.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_probe_failure_from_pods(pods_json):
            failure_class = FAILURE_PROBE_FAILED
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Container probe failed (exit code != 0).")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_deployment_not_ready_from_deployments(deployments_json):
            failure_class = FAILURE_DEPLOYMENT_NOT_AVAILABLE
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Deployment has no available replicas.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/deployments.txt")

        elif _parse_pvc_pending_from_pods(pods_json, events_text):
            failure_class = FAILURE_PVC_PENDING
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: PVC is stuck in Pending state.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt, watchdog/events.txt")

        elif "unknown field" in helm_lower:
            failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart has schema drift (unknown field warnings).")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: logs/helm-install.log")

        else:
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Helm wait timed out but specific cause unknown.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/ directory")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm wait timed out without cluster state data.")
        diagnosis.text(f"{diagnosis.bold('Evidence')}: logs/helm-install.log")

    diagnosis.text("")
    diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review watchdog/ artifacts and helm-install.log")
    diagnosis.text("to determine the root cause of the timeout.")

    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"

    preflight.save()
    diagnosis.save()
    return failure_class


def classify_helm_error(
    helm_output: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
    kubeconfig: str | None = None,
    namespace: str = "",
) -> str:
    """Classify Helm error and return failure class."""
    diagnosis.heading(2, "Helm Error Classification")

    failure_class = FAILURE_HELM_UNKNOWN
    helm_lower = helm_output.lower()

    # Schema warning - "unknown field" pattern
    unknown_field_patterns = [
        r"unknown field",
        r"spec\.template\.spec\.containers\[0\]\.(allowPrivilegeEscalation|capabilities|limits|requests|readOnlyRootFilesystem)",
    ]
    has_unknown_field = any(re.search(p, helm_lower) for p in unknown_field_patterns)
    if has_unknown_field:
        failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart renders container security/resource fields")
        diagnosis.text("at the wrong level (directly under containers[0]) instead of nested under")
        diagnosis.text("securityContext or resources.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Common mistakes')}:")
        diagnosis.text("- `allowPrivilegeEscalation: false` should be `securityContext.allowPrivilegeEscalation: false`")
        diagnosis.text("- `capabilities:` should be `securityContext.capabilities:`")
        diagnosis.text("- `limits:`/`requests:` should be `resources.limits:`/`resources.requests:`")
        diagnosis.text("- `readOnlyRootFilesystem: true` should be `securityContext.readOnlyRootFilesystem: true`")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-rendered.yaml")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Fix chart templates to nest securityContext/resources fields.")

    # RBAC denied
    elif any(re.search(p, helm_lower) for p in [r"forbidden", r"is forbidden", r"cannot get resource"]) and \
         any(re.search(p, helm_lower) for p in [r"roles?", r"rolebindings?", r"rbac"]):
        failure_class = FAILURE_HELM_RBAC_DENIED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm command failed due to missing RBAC permissions for")
        diagnosis.text("Role/RoleBinding resources.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Ensure the kubeconfig has permissions for")
        diagnosis.text("roles.rbac.authorization.k8s.io and rolebindings.rbac.authorization.k8s.io.")

    # Server dry-run validation failed
    elif any(pattern in helm_lower for pattern in [
        "error: error validating",
        "error validating data",
        "dry-run failed",
        "validation failed",
    ]):
        failure_class = FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Server-side dry-run validation failed for rendered manifests.")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-server-dry-run.log")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review rendered manifests and fix schema issues.")

    # Image pull errors
    elif any(pattern in helm_lower for pattern in [
        "imagepullbackoff",
        "errimagepull",
        "failed to pull image",
        "image.*not found",
    ]):
        failure_class = FAILURE_IMAGE_PULL_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Container image could not be pulled.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Verify the image repository is accessible and image exists.")

    # CNPG CRD missing
    elif any(pattern in helm_lower for pattern in [
        "no matches for kind.*cluster",
        "customresourcedefinition.*not found",
        "clusters.postgresql.cnpg.io",
    ]):
        failure_class = FAILURE_CNPG_CRD_MISSING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: CNPG CRD (clusters.postgresql.cnpg.io) is not installed.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Install CloudNativePG operator before running the lab.")

    # Storage/capacity issues
    elif any(pattern in helm_lower for pattern in [
        "persistentvolumeclaim.*pending",
        "waiting for a volume",
        "no storage class",
        "cannot find storageclass",
    ]):
        failure_class = FAILURE_STORAGE_OR_CAPACITY
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: PVC is stuck in Pending state.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Verify StorageClass is available and has sufficient capacity.")

    # Timeout/workload not ready
    elif any(pattern in helm_lower for pattern in [
        "timeout",
        "timed out",
        "deadline exceeded",
        "has no deployed releases",
    ]):
        failure_class = FAILURE_WORKLOAD_NOT_READY
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm deployment timed out waiting for resources to become ready.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Check pod status and resource constraints.")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Unknown Helm error.")

    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"

    preflight.save()
    diagnosis.save()
    return failure_class

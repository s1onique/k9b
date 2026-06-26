#!/usr/bin/env python3
"""Kubectl helper functions for CNPG Live Lab.

This module contains:
- KubectlResult dataclass for structured kubectl output
- kubectl execution wrappers (_get_kubectl_json, _get_kubectl_events, etc.)
- PVC diagnostic and storage class helper functions
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class KubectlResult:
    """Structured result from kubectl command."""

    stdout: str
    stderr: str
    returncode: int
    success: bool
    data: dict[str, Any] | None = None
    parsed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_subprocess(
        cls,
        result: subprocess.CompletedProcess[str],
        parse_json: bool = False,
    ) -> KubectlResult:
        """Create KubectlResult from subprocess result."""
        data = None
        if parse_json and result.returncode == 0:
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        return cls(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            success=result.returncode == 0,
            data=data,
        )


@dataclass
class RolloutDiagnosis:
    """Diagnosis result for a rollout check."""

    check_name: str
    affected_count: int
    affected_items: list[dict[str, Any]]
    failure_class: str
    summary: str
    artifact_path: Path | None = None


# =============================================================================
# kubectl execution wrappers
# =============================================================================

def _get_kubectl_json(
    kubeconfig: str,
    resource: str,
    namespace: str | None = None,
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Execute kubectl get with JSON output."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", resource, "-o", "json"]
    if namespace:
        cmd.extend(["-n", namespace])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result, parse_json=True)


def _get_kubectl_events(
    kubeconfig: str,
    namespace: str,
    sort_by: str = ".lastTimestamp",
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Get events with sorting."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace]
    if sort_by:
        cmd.extend(["--sort-by=" + sort_by])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def _get_kubectl_text(
    kubeconfig: str,
    resource: str,
    namespace: str | None = None,
    extra_args: list[str] | None = None,
) -> KubectlResult:
    """Execute kubectl get with default text output."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", resource]
    if namespace:
        cmd.extend(["-n", namespace])
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    return KubectlResult.from_subprocess(result)


def _get_kubectl_storageclass(
    kubeconfig: str,
    name: str | None = None,
) -> KubectlResult:
    """Get storage class details."""
    resource = f"storageclass/{name}" if name else "storageclass"
    return _get_kubectl_json(kubeconfig, resource)


# =============================================================================
# Deployment helpers
# =============================================================================

def _get_deployment_conditions(
    kubeconfig: str,
    namespace: str,
    deployment: str,
) -> list[dict[str, Any]]:
    """Get deployment conditions."""
    result = _get_kubectl_json(kubeconfig, f"deployment/{deployment}", namespace)
    if not result.success or not result.data:
        return []

    status = result.data.get("status", {})
    conditions = status.get("conditions", [])
    return list(conditions)


# =============================================================================
# PVC helpers
# =============================================================================

def _get_pvc_status(
    kubeconfig: str,
    namespace: str,
) -> KubectlResult:
    """Get PVC status."""
    return _get_kubectl_json(kubeconfig, "pvc", namespace)


def _get_pod_waiting_info(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
) -> dict[str, Any]:
    """Get pod waiting container info."""
    result = _get_kubectl_json(kubeconfig, f"pod/{pod_name}", namespace)
    if not result.success or not result.data:
        return {}

    waiting_info = {}
    container_statuses = result.data.get("status", {}).get("containerStatuses", [])
    for cs in container_statuses:
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        if waiting:
            waiting_info[cs.get("name", "")] = {
                "reason": waiting.get("reason", ""),
                "message": waiting.get("message", ""),
            }

    return waiting_info


def _get_pvc_binding_mode(
    kubeconfig: str,
    pvc_name: str,
    namespace: str,
) -> str | None:
    """Get PVC binding mode from StorageClass."""
    result = _get_kubectl_json(kubeconfig, f"pvc/{pvc_name}", namespace)
    if not result.success or not result.data:
        return None

    storage_class_name = result.data.get("spec", {}).get("storageClassName")
    if not storage_class_name:
        return None

    sc_result = _get_kubectl_storageclass(kubeconfig, storage_class_name)
    if not sc_result.success or not sc_result.data:
        return None

    annotations: dict[str, Any] = sc_result.data.get("metadata", {})
    return cast(str | None, annotations.get("storageclass.kubernetes.io/is-default-class"))


def _get_default_storage_class(
    kubeconfig: str,
) -> str | None:
    """Get the default storage class name."""
    result = _get_kubectl_json(kubeconfig, "storageclass")
    if not result.success or not result.data:
        return None

    items = result.data.get("items", [])
    for sc in items:
        annotations = sc.get("metadata", {}).get("annotations", {})
        if annotations.get("storageclass.kubernetes.io/is-default-class") == "true":
            metadata: dict[str, Any] = sc.get("metadata", {})
            return cast(str | None, metadata.get("name"))

    return None


# =============================================================================
# PVC diagnostic collection
# =============================================================================

def _check_pvc_provisioning_failure(
    kubeconfig: str,
    namespace: str,
    pvc_name: str,
) -> dict[str, Any] | None:
    """Check if PVC has provisioning failure."""
    result = _get_kubectl_json(kubeconfig, f"pvc/{pvc_name}", namespace)
    if not result.success or not result.data:
        return None

    status = result.data.get("status", {})
    phase = status.get("phase", "")

    if phase != "Pending":
        return None

    conditions = status.get("conditions", [])
    for cond in conditions:
        if cond.get("type") == "Pending" and cond.get("status") == "True":
            reason = cond.get("reason", "")
            if reason in ("WaitingForFirstConsumer", "WaitingForVolumeBinding"):
                return {
                    "pvc": pvc_name,
                    "status": "Pending",
                    "reason": reason,
                    "message": cond.get("message", ""),
                }

    return None


def _check_pvc_missing_storage_class(
    kubeconfig: str,
    namespace: str,
    pvc_name: str,
) -> dict[str, Any] | None:
    """Check if PVC references missing storage class."""
    result = _get_kubectl_json(kubeconfig, f"pvc/{pvc_name}", namespace)
    if not result.success or not result.data:
        return None

    spec = result.data.get("spec", {})
    storage_class = spec.get("storageClassName")

    # If no storage class specified, check default
    if not storage_class:
        default_sc = _get_default_storage_class(kubeconfig)
        if not default_sc:
            return {
                "pvc": pvc_name,
                "status": "NoStorageClass",
                "reason": "NoStorageClass",
                "message": "No storage class specified and no default storage class found",
            }
        return None

    # Check if storage class exists
    sc_result = _get_kubectl_storageclass(kubeconfig, storage_class)
    if not sc_result.success:
        return {
            "pvc": pvc_name,
            "status": "StorageClassNotFound",
            "reason": "StorageClassNotFound",
            "message": f"Storage class '{storage_class}' not found",
        }

    return None


def _check_pvc_wait_for_first_consumer(
    kubeconfig: str,
    namespace: str,
    pvc_name: str,
) -> dict[str, Any] | None:
    """Check if PVC is waiting for first consumer."""
    result = _get_kubectl_json(kubeconfig, f"pvc/{pvc_name}", namespace)
    if not result.success or not result.data:
        return None

    storage_class_name = result.data.get("spec", {}).get("storageClassName")
    if not storage_class_name:
        return None

    sc_result = _get_kubectl_storageclass(kubeconfig, storage_class_name)
    if not sc_result.success or not sc_result.data:
        return None

    # Check volume binding mode
    volume_binding_mode = sc_result.data.get("metadata", {}).get("annotations", {}).get(
        "volume.kubernetes.io/volume-binding-mode"
    )
    if volume_binding_mode == "WaitForFirstConsumer":
        return {
            "pvc": pvc_name,
            "status": "WaitForFirstConsumer",
            "reason": "WaitingForFirstConsumer",
            "message": "PVC waiting for first consumer to start pod scheduling",
            "storage_class": storage_class_name,
            "binding_mode": volume_binding_mode,
        }

    return None


def _collect_pvc_diagnostic_info(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
) -> list[dict[str, Any]]:
    """Collect PVC diagnostic information.

    Returns:
        List of diagnostic results for each PVC.
    """
    result = _get_pvc_status(kubeconfig, namespace)
    if not result.success or not result.data:
        return []

    items = result.data.get("items", [])
    diagnostics = []

    for pvc in items:
        pvc_name = pvc.get("metadata", {}).get("name", "")
        diagnostics.append({
            "name": pvc_name,
            "namespace": namespace,
            "phase": pvc.get("status", {}).get("phase", ""),
            "storage_class": pvc.get("spec", {}).get("storageClassName", ""),
            "access_modes": pvc.get("spec", {}).get("accessModes", []),
            "capacity": pvc.get("status", {}).get("capacity", {}),
        })

    return diagnostics

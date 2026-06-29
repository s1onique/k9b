#!/usr/bin/env python3
"""Kubernetes prerequisite checks for backend health gates."""

from __future__ import annotations

import subprocess

from .constants import (
    FAILURE_BACKEND_DEPLOYMENT_MISSING,
    FAILURE_BACKEND_NAMESPACE_MISSING,
    FAILURE_BACKEND_ROLLOUT_NOT_READY,
    FAILURE_BACKEND_SERVICE_MISSING,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    K9B_BACKEND_SERVICE,
    K9B_NAMESPACE,
)
from .types import HealthCheckResult


def _check_namespace_exists(kubeconfig: str, namespace: str) -> tuple[bool, str]:
    """Check if a namespace exists."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "namespace", namespace]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, ""
        error_msg = result.stderr.strip().lower()
        if "notfound" in error_msg.replace(" ", "") or "not found" in error_msg:
            return False, f"namespace '{namespace}' not found"
        if "forbidden" in error_msg or "denied" in error_msg:
            return False, "namespace access denied (RBAC)"
        return False, result.stderr.strip() or "unknown error"
    except subprocess.TimeoutExpired:
        return False, "timeout checking namespace"
    except Exception as e:
        return False, str(e)


def _check_service_exists(kubeconfig: str, namespace: str, service: str) -> tuple[bool, str]:
    """Check if a service exists in a namespace."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "service", service, "-n", namespace]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, ""
        error_msg = result.stderr.strip().lower()
        if "notfound" in error_msg.replace(" ", "") or "not found" in error_msg:
            return False, f"service '{service}' not found"
        if "forbidden" in error_msg or "denied" in error_msg:
            return False, "service access denied (RBAC)"
        return False, result.stderr.strip() or "unknown error"
    except subprocess.TimeoutExpired:
        return False, "timeout checking service"
    except Exception as e:
        return False, str(e)


def _check_deployment_exists(kubeconfig: str, namespace: str, deployment: str) -> tuple[bool, str]:
    """Check if a deployment exists in a namespace."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "get", "deployment", deployment, "-n", namespace]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, ""
        error_msg = result.stderr.strip().lower()
        if "notfound" in error_msg.replace(" ", "") or "not found" in error_msg:
            return False, f"deployment '{deployment}' not found"
        if "forbidden" in error_msg or "denied" in error_msg:
            return False, "deployment access denied (RBAC)"
        return False, result.stderr.strip() or "unknown error"
    except subprocess.TimeoutExpired:
        return False, "timeout checking deployment"
    except Exception as e:
        return False, str(e)


def _check_deployment_ready(
    kubeconfig: str, namespace: str, deployment: str, timeout_seconds: int = 60
) -> tuple[bool, str]:
    """Check if a deployment is fully rolled out."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig, "rollout", "status",
        f"deployment/{deployment}", "-n", namespace,
        "--timeout", f"{timeout_seconds}s"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds + 10)
        if result.returncode == 0:
            return True, "deployment ready"
        error_msg = result.stdout.strip() or result.stderr.strip()
        if "error" in error_msg.lower():
            return False, error_msg
        return False, "deployment not ready"
    except subprocess.TimeoutExpired:
        return False, f"rollout timeout after {timeout_seconds}s"
    except Exception as e:
        return False, str(e)


def check_backend_prerequisites(
    kubeconfig: str,
    namespace: str = K9B_NAMESPACE,
    deployment: str = K9B_BACKEND_DEPLOYMENT,
    service: str = K9B_BACKEND_SERVICE,
    port: int = K9B_BACKEND_PORT,
    rollout_timeout: int = 60,
) -> tuple[HealthCheckResult, dict[str, str]]:
    """Check all k9b backend prerequisites."""
    result = HealthCheckResult()
    artifacts: dict[str, str] = {}

    # Check namespace
    ns_exists, ns_error = _check_namespace_exists(kubeconfig, namespace)
    if not ns_exists:
        result.failure_class = FAILURE_BACKEND_NAMESPACE_MISSING
        result.final_http_code = f"ERR:{FAILURE_BACKEND_NAMESPACE_MISSING}"
        return result, artifacts

    # Check service
    svc_exists, svc_error = _check_service_exists(kubeconfig, namespace, service)
    if not svc_exists:
        result.failure_class = FAILURE_BACKEND_SERVICE_MISSING
        result.final_http_code = f"ERR:{FAILURE_BACKEND_SERVICE_MISSING}"
        return result, artifacts

    # Check deployment
    deploy_exists, deploy_error = _check_deployment_exists(kubeconfig, namespace, deployment)
    if not deploy_exists:
        result.failure_class = FAILURE_BACKEND_DEPLOYMENT_MISSING
        result.final_http_code = f"ERR:{FAILURE_BACKEND_DEPLOYMENT_MISSING}"
        return result, artifacts

    # Check deployment is ready
    deploy_ready, ready_error = _check_deployment_ready(
        kubeconfig, namespace, deployment, timeout_seconds=rollout_timeout
    )
    if not deploy_ready:
        result.failure_class = FAILURE_BACKEND_ROLLOUT_NOT_READY
        result.final_http_code = f"ERR:{FAILURE_BACKEND_ROLLOUT_NOT_READY}"
        return result, artifacts

    result.passed = True
    return result, artifacts

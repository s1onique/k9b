"""Scheduler loop gate for automatic diagnosis.

This module provides the gate function that checks if the automatic diagnosis
loop is enabled on the scheduler deployment.

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
    The scheduler deployment must have K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
    for the loop to run. The backend does NOT need this env var.

    When running in a Kubernetes context (kubeconfig available), this function
    checks the scheduler deployment's env vars via kubectl. When running in
    a local/test context without cluster access, it falls back to os.environ.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .incident_diagnosis_loop_constants import (
    _AUTOMATIC_LOOP_ENV_VAR,
    _K9B_NAMESPACE_ENV_VAR,
    _SCHEDULER_DEPLOYMENT,
    DEFAULT_K9B_NAMESPACE,
)


def get_default_k9b_namespace() -> str:
    """Get the default k9b control-plane namespace.

    Resolves K9B_NAMESPACE environment variable, falling back to "k9b".

    Guards against blank values to avoid generating kubectl -n "" ...

    Returns:
        The configured k9b namespace, or "k9b" if not configured or blank.
    """
    return os.environ.get(_K9B_NAMESPACE_ENV_VAR, "").strip() or DEFAULT_K9B_NAMESPACE

if TYPE_CHECKING:
    pass

__all__ = [
    "get_default_k9b_namespace",
    "is_automatic_diagnosis_loop_enabled",
    "get_automatic_loop_enabled_with_reason",
    "DeploymentReadError",
    "LoopEnabledCheckResult",
]


class DeploymentReadError(Exception):
    """Raised when deployment env var read fails due to RBAC or network issues."""

    def __init__(self, message: str, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr

    def is_rbac_denied(self) -> bool:
        """Check if the error was caused by RBAC denial."""
        if self.returncode is None:
            return False
        # kubectl returns exit code 1 for RBAC denials and exit code 1 for "not found"
        # but RBAC denials typically include "Forbidden" or "Unauthorized" in stderr
        denied_patterns = ["Forbidden", "Unauthorized", "denied", "cannot get"]
        stderr_lower = self.stderr.lower()
        return any(pattern.lower() in stderr_lower for pattern in denied_patterns)

    def is_not_found(self) -> bool:
        """Check if the error was caused by resource not found."""
        if self.returncode is None:
            return False
        not_found_patterns = ["not found", "No resources found"]
        return any(p.lower() in self.stderr.lower() for p in not_found_patterns)


def _read_deployment_env_value(
    kubeconfig: str | None,
    namespace: str,
    deployment: str,
    env_var: str,
) -> tuple[str | None, DeploymentReadError | None]:
    """Get environment variable value from a Kubernetes Deployment.

    This reads the deployment spec directly, not runtime container env.
    Suitable for checking if the env var is CONFIGURED in the deployment.

    Note: Only includes --kubeconfig flag when kubeconfig is non-empty.
    When kubeconfig is None/empty, kubectl falls back to in-cluster config
    or $HOME/.kube/config as per Kubernetes behavior.

    Args:
        kubeconfig: Path to kubeconfig file (None for in-cluster)
        namespace: Namespace where the deployment lives
        deployment: Name of the deployment
        env_var: Environment variable name to retrieve

    Returns:
        Tuple of (env_var_value, error). If error is not None, the value is None
        and the error contains details about why the read failed.
    """
    cmd: list[str] = ["kubectl"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    cmd.extend([
        "-n", namespace,
        "get", "deployment",
        deployment,
        "-o", "json",
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            error = DeploymentReadError(
                message=f"Failed to read deployment {deployment} in namespace {namespace}: kubectl exited with code {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
            return None, error

        deployment_obj = json.loads(result.stdout)
        containers = deployment_obj.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])

        for container in containers:
            env_list = container.get("env", [])
            for env_entry in env_list:
                if env_entry.get("name") == env_var:
                    return str(env_entry.get("value")) if env_entry.get("value") is not None else None, None

        return None, None

    except subprocess.TimeoutExpired:
        error = DeploymentReadError(
            message=f"Timeout reading deployment {deployment} in namespace {namespace}",
            returncode=None,
            stderr="Command timed out after 30 seconds",
        )
        return None, error
    except json.JSONDecodeError as e:
        error = DeploymentReadError(
            message=f"Invalid JSON response from deployment {deployment}: {e}",
            returncode=None,
            stderr=str(e),
        )
        return None, error
    except OSError as e:
        error = DeploymentReadError(
            message=f"OS error reading deployment {deployment}: {e}",
            returncode=None,
            stderr=str(e),
        )
        return None, error


def _get_deployment_env_value(
    kubeconfig: str | None,
    namespace: str,
    deployment: str,
    env_var: str,
) -> str | None:
    """Get environment variable value from a Kubernetes Deployment.

    This is the public-facing helper that returns just the value (or None).
    For detailed error handling, use _read_deployment_env_value() instead.

    Args:
        kubeconfig: Path to kubeconfig file (None for in-cluster)
        namespace: Namespace where the deployment lives
        deployment: Name of the deployment
        env_var: Environment variable name to retrieve

    Returns:
        The env var value as a string, or None if not set or on error.
    """
    value, _error = _read_deployment_env_value(
        kubeconfig=kubeconfig,
        namespace=namespace,
        deployment=deployment,
        env_var=env_var,
    )
    return value


@dataclass(frozen=True)
class LoopEnabledCheckResult:
    """Result of loop enabled check with detailed reason.

    Attributes:
        enabled: Whether the automatic loop is enabled
        source: Where the value came from: "deployment", "environment", or "error"
        reason: Specific reason code:
            - "env_var_from_deployment": Env var found and enabled in deployment
            - "env_var_not_enabled": Env var found but set to false
            - "env_var_not_set": Env var not found in deployment
            - "automatic_loop_env_rbac_denied": RBAC prevented reading deployment
            - "automatic_loop_env_read_failed": Network/timeout/error reading deployment
            - "env_var_from_fallback": Using os.environ fallback
        error_message: Optional error message if source is "error"
    """

    enabled: bool
    source: str
    reason: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": self.enabled,
            "source": self.source,
            "reason": self.reason,
        }
        if self.error_message:
            result["error_message"] = self.error_message
        return result


def is_automatic_diagnosis_loop_enabled(
    kubeconfig: str | None = None,
    namespace: str = "k9b",
    *,
    allow_env_fallback: bool = True,
) -> bool:
    """Check if automatic diagnosis loop is enabled on the scheduler.

    Architecture: The automatic diagnosis loop belongs to the SCHEDULER,
    not the backend. This function checks the scheduler deployment's
    environment configuration.

    When kubeconfig is provided and the cluster is accessible, it reads
    the env var directly from the scheduler deployment spec. This is the
    authoritative source for whether the loop is enabled.

    Args:
        kubeconfig: Optional path to kubeconfig. If None, uses in-cluster config.
        namespace: Namespace where k9b scheduler runs (default: "k9b")
        allow_env_fallback: If True (default), falls back to os.environ when
            kubectl fails (useful for local dev). If False, returns False when
            cluster is not accessible (fail-closed for live-lab verification).

    Returns:
        True if K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true on scheduler deployment
    """
    enabled, _ = get_automatic_loop_enabled_with_reason(
        kubeconfig=kubeconfig,
        namespace=namespace,
        allow_env_fallback=allow_env_fallback,
    )
    return enabled


def get_automatic_loop_enabled_with_reason(
    kubeconfig: str | None = None,
    namespace: str = "k9b",
    *,
    allow_env_fallback: bool = True,
) -> tuple[bool, LoopEnabledCheckResult]:
    """Check if automatic diagnosis loop is enabled with detailed reason.

    This function provides more detailed information about WHY the loop is
    enabled or disabled, including specific error reasons for RBAC or read failures.

    Args:
        kubeconfig: Optional path to kubeconfig. If None, uses in-cluster config.
        namespace: Namespace where k9b scheduler runs (default: "k9b")
        allow_env_fallback: If True (default), falls back to os.environ when
            kubectl fails (useful for local dev). If False, returns False when
            cluster is not accessible (fail-closed for live-lab verification).

    Returns:
        Tuple of (enabled: bool, result: LoopEnabledCheckResult with detailed info)
    """
    # First, try to read from scheduler deployment in cluster
    # This is the authoritative source for the scheduler's configuration
    scheduler_env_value, read_error = _read_deployment_env_value(
        kubeconfig=kubeconfig,
        namespace=namespace,
        deployment=_SCHEDULER_DEPLOYMENT,
        env_var=_AUTOMATIC_LOOP_ENV_VAR,
    )

    if scheduler_env_value is not None:
        enabled = scheduler_env_value.lower() == "true"
        return enabled, LoopEnabledCheckResult(
            enabled=enabled,
            source="deployment",
            reason="env_var_from_deployment" if enabled else "env_var_not_enabled",
        )

    # Deployment read failed - classify the error
    if read_error is not None:
        if read_error.is_rbac_denied():
            # Fail-closed: RBAC denial means we can't verify the scheduler config
            return False, LoopEnabledCheckResult(
                enabled=False,
                source="error",
                reason="automatic_loop_env_rbac_denied",
                error_message=str(read_error),
            )
        elif not allow_env_fallback:
            # Other read failures (network, timeout, not found) - fail-closed if no fallback
            return False, LoopEnabledCheckResult(
                enabled=False,
                source="error",
                reason="automatic_loop_env_read_failed",
                error_message=str(read_error),
            )
        # For other errors with allow_env_fallback=True, fall through to env check

    # No env var found in deployment, or cluster read failed but fallback allowed
    # Fallback to local environment for local development/testing
    enabled = os.environ.get(_AUTOMATIC_LOOP_ENV_VAR, "false").lower() == "true"
    if scheduler_env_value is None and read_error is not None:
        # Cluster read failed but we fell back to env
        return enabled, LoopEnabledCheckResult(
            enabled=enabled,
            source="environment",
            reason="env_var_from_fallback" if enabled else "env_var_not_set",
        )
    elif scheduler_env_value is None:
        # No env var found in deployment spec
        return enabled, LoopEnabledCheckResult(
            enabled=enabled,
            source="environment",
            reason="env_var_from_fallback" if enabled else "env_var_not_set",
        )
    # This branch won't be reached due to earlier return, but kept for completeness
    return enabled, LoopEnabledCheckResult(
        enabled=enabled,
        source="environment",
        reason="env_var_from_fallback" if enabled else "env_var_not_set",
    )

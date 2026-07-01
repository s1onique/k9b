"""Configuration and eligibility model for automatic diagnosis loop.

This module provides:
- AutomaticDiagnosisLoopConfig dataclass with hard budget bounds
- EligibilityResult dataclass for eligibility checks
- Status constants for active/terminal incident states
- is_automatic_diagnosis_loop_enabled() gate function

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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import IncidentStatus
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    pass

__all__ = [
    "is_automatic_diagnosis_loop_enabled",
    "get_automatic_loop_enabled_with_reason",
    "AutomaticDiagnosisLoopConfig",
    "EligibilityResult",
    "check_incident_eligibility",
    "_ACTIVE_STATUSES",
    "_TERMINAL_STATUSES",
    # Internal functions for testing
    "_get_deployment_env_value",
    # Error types for external handling
    "DeploymentReadError",
    "LoopEnabledCheckResult",
]


# =============================================================================
# Environment Gate
# =============================================================================

_AUTOMATIC_LOOP_ENV_VAR = "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"
_SCHEDULER_DEPLOYMENT = "k9b-scheduler"
_SCHEDULER_CONTAINER = "scheduler"


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


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class AutomaticDiagnosisLoopConfig:
    """Configuration for automatic diagnosis loop collector.

    All bounds are hard constraints for safety.
    """

    # Maximum incidents to process per collector run
    max_incidents_per_run: int = 10

    # Maximum automatic passes per incident (default 1 for safety)
    max_passes_per_incident: int = 1

    # Maximum checks per pass (policy limit, not execution limit)
    max_checks_per_pass: int = 5

    # Whether to write review packet even for stop-path (no checks run)
    write_stop_path_packets: bool = True

    # Whether to write review packet for ineligible incidents
    write_ineligible_packets: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_incidents_per_run": self.max_incidents_per_run,
            "max_passes_per_incident": self.max_passes_per_incident,
            "max_checks_per_pass": self.max_checks_per_pass,
            "write_stop_path_packets": self.write_stop_path_packets,
            "write_ineligible_packets": self.write_ineligible_packets,
        }


# =============================================================================
# Eligibility Model
# =============================================================================

# Active statuses that qualify for automatic evidence collection
_ACTIVE_STATUSES: frozenset[IncidentStatus] = frozenset([
    IncidentStatus.OPEN,
    IncidentStatus.COLLECTING_EVIDENCE,
    IncidentStatus.INVESTIGATING,
])

# Terminal statuses that disqualify automatic evidence collection
_TERMINAL_STATUSES: frozenset[IncidentStatus] = frozenset([
    IncidentStatus.SUPPRESSED,
    IncidentStatus.DUPLICATE,
    IncidentStatus.RESOLVED,
    IncidentStatus.READY_FOR_REVIEW,
])


@dataclass(frozen=True)
class EligibilityResult:
    """Result of eligibility check for an incident."""

    eligible: bool
    incident_id: str
    reason: str
    status: str | None = None
    has_suggested_checks: bool = False
    auto_pass_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "eligible": self.eligible,
            "incident_id": self.incident_id,
            "reason": self.reason,
        }
        if self.status is not None:
            result["status"] = self.status
        result["has_suggested_checks"] = self.has_suggested_checks
        result["auto_pass_count"] = self.auto_pass_count
        return result


def check_incident_eligibility(
    incident_id: str,
    config: AutomaticDiagnosisLoopConfig,
    external_analysis_dir: Path | None = None,
) -> EligibilityResult:
    """Check if an incident is eligible for automatic diagnosis loop.

    Conservative eligibility model:
    - Must be in active status (OPEN, COLLECTING_EVIDENCE, INVESTIGATING)
    - Must not be in terminal status (SUPPRESSED, DUPLICATE, RESOLVED, READY_FOR_REVIEW)
    - Must have suggested_checks OR enough context for stop-path packet
    - Must not have exceeded automatic loop budget

    Args:
        incident_id: The incident ID to check
        config: Collector configuration with budget limits
        external_analysis_dir: Optional path to check for existing review packets

    Returns:
        EligibilityResult with eligible flag and reason
    """
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason="incident_not_found",
        )

    # Check status
    status = incident.status
    if status in _TERMINAL_STATUSES:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason=f"terminal_status_{status.value}",
            status=status.value,
        )

    if status not in _ACTIVE_STATUSES:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason=f"inactive_status_{status.value}",
            status=status.value,
        )

    # Check for suggested checks (required for meaningful evidence collection)
    # If no suggested checks, we can still write a stop-path packet
    suggested_checks = getattr(incident, "signals", [])  # Fallback check
    has_suggested_checks = len(suggested_checks) > 0

    # Check automatic loop budget by counting existing review packets
    auto_pass_count = 0
    if external_analysis_dir is not None and external_analysis_dir.exists():
        # Count existing automatic review packets for this incident
        # Pattern: auto-{incident_id}-*-diagnosis-review-packet.json
        prefix = f"auto-{incident_id}-"
        suffix = "-diagnosis-review-packet.json"
        try:
            for path in external_analysis_dir.iterdir():
                if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix):
                    auto_pass_count += 1
        except OSError:
            pass  # Ignore filesystem errors during budget check

    if auto_pass_count >= config.max_passes_per_incident:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason="budget_exhausted",
            status=status.value,
            has_suggested_checks=has_suggested_checks,
            auto_pass_count=auto_pass_count,
        )

    return EligibilityResult(
        eligible=True,
        incident_id=incident_id,
        reason="active_incident_with_suggested_checks",
        status=status.value,
        has_suggested_checks=has_suggested_checks,
        auto_pass_count=auto_pass_count,
    )

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
    "AutomaticDiagnosisLoopConfig",
    "EligibilityResult",
    "check_incident_eligibility",
    "_ACTIVE_STATUSES",
    "_TERMINAL_STATUSES",
]


# =============================================================================
# Environment Gate
# =============================================================================

_AUTOMATIC_LOOP_ENV_VAR = "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"
_SCHEDULER_DEPLOYMENT = "k9b-scheduler"
_SCHEDULER_CONTAINER = "scheduler"


def _get_deployment_env_value(
    kubeconfig: str | None,
    namespace: str,
    deployment: str,
    env_var: str,
) -> str | None:
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
        The env var value if found, None if not set or on error.
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
            return None

        deployment_obj = json.loads(result.stdout)
        containers = deployment_obj.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])

        for container in containers:
            env_list = container.get("env", [])
            for env_entry in env_list:
                if env_entry.get("name") == env_var:
                    return str(env_entry.get("value")) if env_entry.get("value") is not None else None

        return None

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


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
    # First, try to read from scheduler deployment in cluster
    # This is the authoritative source for the scheduler's configuration
    scheduler_env_value = _get_deployment_env_value(
        kubeconfig=kubeconfig,
        namespace=namespace,
        deployment=_SCHEDULER_DEPLOYMENT,
        env_var=_AUTOMATIC_LOOP_ENV_VAR,
    )

    if scheduler_env_value is not None:
        return scheduler_env_value.lower() == "true"

    # Fail-closed for live-lab: when cluster is not accessible,
    # return False instead of masking the real scheduler state
    if not allow_env_fallback:
        return False

    # Fallback to local environment for local development/testing
    # when cluster is not accessible
    return os.environ.get(_AUTOMATIC_LOOP_ENV_VAR, "false").lower() == "true"


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

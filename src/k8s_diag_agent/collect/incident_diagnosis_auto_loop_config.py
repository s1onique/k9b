"""Configuration and eligibility model for automatic diagnosis loop.

This module provides:
- AutomaticDiagnosisLoopConfig dataclass with hard budget bounds
- EligibilityResult dataclass for eligibility checks
- check_incident_eligibility() function

The gate functions (is_automatic_diagnosis_loop_enabled, etc.)
have been moved to incident_diagnosis_loop_gate.py for better organization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import IncidentStatus
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    pass

__all__ = [
    "AutomaticDiagnosisLoopConfig",
    "DiagnosisBudgetDiagnostic",
    "EligibilityResult",
    "check_incident_eligibility",
    "_ACTIVE_STATUSES",
    "_TERMINAL_STATUSES",
    # Re-export gate functions for backwards compatibility
    "is_automatic_diagnosis_loop_enabled",
    "get_automatic_loop_enabled_with_reason",
    "DeploymentReadError",
    "LoopEnabledCheckResult",
]

# Re-export gate functions and helpers for backwards compatibility
from .incident_diagnosis_loop_constants import (
    _SCHEDULER_DEPLOYMENT,
)
from .incident_diagnosis_loop_gate import (
    DeploymentReadError,
    LoopEnabledCheckResult,
    _get_deployment_env_value,
    get_automatic_loop_enabled_with_reason,
    get_default_k9b_namespace,
    is_automatic_diagnosis_loop_enabled,
)

__all__ = __all__ + [
    "_get_deployment_env_value",
    "_SCHEDULER_DEPLOYMENT",
    "get_default_k9b_namespace",
]


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
# Budget Diagnostic Model
# =============================================================================


@dataclass(frozen=True)
class DiagnosisBudgetDiagnostic:
    """Structured budget diagnostic for debugging eligibility failures.

    Provides detailed information about each budget that affects eligibility,
    making it easy to diagnose why an incident is not eligible.

    Attributes:
        name: Stable name for the budget (e.g., "review_packet_budget")
        used: Number of units consumed
        limit: Maximum allowed units
        remaining: Units remaining (limit - used)
        exhausted: Whether the budget is exhausted
        source: Where the budget count comes from (e.g., "review_packet_artifacts")
        resettable: Whether resetting would clear this budget
    """

    name: str
    used: int
    limit: int
    remaining: int
    exhausted: bool
    source: str
    resettable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "used": self.used,
            "limit": self.limit,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
            "source": self.source,
            "resettable": self.resettable,
        }

    def summary(self) -> str:
        """Human-readable summary for logging/debugging."""
        status = "EXHAUSTED" if self.exhausted else "OK"
        return f"{self.name}: {status} used={self.used} limit={self.limit} remaining={self.remaining} source={self.source} resettable={self.resettable}"


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
    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = ()

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
        if self.budget_diagnostics:
            result["budget_diagnostics"] = [d.to_dict() for d in self.budget_diagnostics]
        return result

    def exhausted_budget_names(self) -> tuple[str, ...]:
        """Return names of exhausted budgets."""
        return tuple(d.name for d in self.budget_diagnostics if d.exhausted)

    def budget_summary(self) -> str:
        """Human-readable summary of all budget diagnostics."""
        if not self.budget_diagnostics:
            return "no budget diagnostics"
        lines = [d.summary() for d in self.budget_diagnostics]
        return "; ".join(lines)


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
        EligibilityResult with eligible flag, reason, and budget diagnostics
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

    # Build budget diagnostics for the response
    budget_limit = config.max_passes_per_incident
    budget_remaining = max(0, budget_limit - auto_pass_count)
    budget_diagnostics = (
        DiagnosisBudgetDiagnostic(
            name="review_packet_budget",
            used=auto_pass_count,
            limit=budget_limit,
            remaining=budget_remaining,
            exhausted=auto_pass_count >= budget_limit,
            source="review_packet_artifacts",
            resettable=True,
        ),
    )

    if auto_pass_count >= config.max_passes_per_incident:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason="budget_exhausted",
            status=status.value,
            has_suggested_checks=has_suggested_checks,
            auto_pass_count=auto_pass_count,
            budget_diagnostics=budget_diagnostics,
        )

    return EligibilityResult(
        eligible=True,
        incident_id=incident_id,
        reason="active_incident_with_suggested_checks",
        status=status.value,
        has_suggested_checks=has_suggested_checks,
        auto_pass_count=auto_pass_count,
        budget_diagnostics=budget_diagnostics,
    )

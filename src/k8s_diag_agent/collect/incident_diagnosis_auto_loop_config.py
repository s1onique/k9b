"""Configuration and eligibility model for automatic diagnosis loop.

This module provides:
- AutomaticDiagnosisLoopConfig dataclass with hard budget bounds
- EligibilityResult / DiagnosisBudgetDiagnostic dataclasses
- :func:`evaluate_incident_eligibility` (aggregate-based; lookup-free)
- :func:`check_incident_eligibility` (local-store compatibility wrapper)

The aggregate evaluator accepts a typed :class:`Incident` aggregate
and never re-resolves the incident through the local store; the
compat wrapper exists only for local-mode callers and tests.

ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 added the aggregate
entry point so the scheduler-side processor can pass the typed
``Incident`` from a successful :class:`BackendIncidentFound` directly
to :func:`evaluate_incident_eligibility` without a second incident
lookup.

The gate functions (is_automatic_diagnosis_loop_enabled, etc.)
have been moved to incident_diagnosis_loop_gate.py for better
organization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import IncidentStatus
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    from .incident_diagnosis_review_packet_budget import (
        ReviewPacketCreationBudget,
    )
    from .incident_lifecycle import Incident

__all__ = [
    "AutomaticDiagnosisLoopConfig",
    "DiagnosisBudgetDiagnostic",
    "EligibilityResult",
    "check_incident_eligibility",
    "evaluate_incident_eligibility",
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

    # P4c lab-strict mode: require complete root cause before accepting stop_no_checks_proposed.
    # When True, the diagnosis must contain complete scheduling root cause evidence
    # (shipping, nodeSelector, k9b.dev/otel-lab-node, FailedScheduling) before stopping.
    require_complete_root_cause_before_stop: bool = False

    # R1: per-run review-packet creation budget. The collector-local
    # ``ReviewPacketCreationBudget`` is instantiated with this value as
    # its limit. The collector starts at zero usage regardless of any
    # pre-existing review-packet artifacts on disk.
    max_review_packets: int = 1

    # Per-incident wall-clock budget forwarded to ``HypothesisLoopConfig``
    # by :func:`k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor._process_incident`.
    # Keep the default aligned with
    # ``HypothesisLoopConfig.max_seconds_per_incident`` so the dataclass
    # and the hypothesis loop stay in lock-step.
    max_seconds_per_incident: int = 45

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_incidents_per_run": self.max_incidents_per_run,
            "max_passes_per_incident": self.max_passes_per_incident,
            "max_checks_per_pass": self.max_checks_per_pass,
            "write_stop_path_packets": self.write_stop_path_packets,
            "write_ineligible_packets": self.write_ineligible_packets,
            "require_complete_root_cause_before_stop": self.require_complete_root_cause_before_stop,
            "max_review_packets": self.max_review_packets,
            "max_seconds_per_incident": self.max_seconds_per_incident,
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




def _count_automatic_review_packets(
    *,
    incident_id: str,
    external_analysis_dir: Path | None,
) -> int:
    """Count existing automatic review-packet artifacts for an incident.

    The heuristic is intentionally filesystem-based: it never reaches
    the incident store, never reaches a backend, and never accepts a
    bare ``incident_id`` without the matching aggregate context already
    known to the caller.
    """
    if external_analysis_dir is None or not external_analysis_dir.exists():
        return 0
    prefix = f"auto-{incident_id}-"
    suffix = "-diagnosis-review-packet.json"
    count = 0
    try:
        for path in external_analysis_dir.rglob("*"):
            try:
                if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix):
                    count += 1
            except OSError:
                continue
    except OSError:
        return count
    return count


def evaluate_incident_eligibility(
    *,
    incident: Incident,
    config: AutomaticDiagnosisLoopConfig,
    external_analysis_dir: Path | None = None,
    review_packet_budget: ReviewPacketCreationBudget | None = None,
) -> EligibilityResult:
    """Evaluate automatic-diagnosis eligibility from a typed incident aggregate.

    The evaluator is **lookup-free**: it accepts a typed
    :class:`Incident` and never resolves the incident from the store,
    never calls a backend detail client, and never accepts an
    ``incident_id`` as its only incident input. Filesystem inspection
    for existing review-packet artifacts and budget accounting is
    permitted where the budget lookup is required.

    R1: when ``review_packet_budget`` is supplied, the historical
    filesystem count of review-packet artifacts is NOT consulted; the
    collector-local budget is the authoritative source of truth for
    per-run packet-write exhaustion. The historical
    ``_count_automatic_review_packets`` heuristic is restricted to
    explicit collector-resume reconstruction (see
    :func:`reconstruct_budget_from_existing_packets`) so a fresh
    collector run starts at zero usage regardless of pre-existing
    packet artifacts on disk.

    Production callers reach this function with the incident aggregate
    returned from :class:`BackendIncidentFound` so the same typed
    snapshot drives both domain eligibility and downstream case-file
    construction.

    Args:
        incident: The canonical :class:`Incident` aggregate to evaluate.
            The supplied ``incident_id`` field is the authoritative
            identity for diagnostics and budget counts.
        config: Collector configuration with budget limits.
        external_analysis_dir: Optional path used to count existing
            automatic review packets for the per-incident budget when
            no collector-local budget is supplied.
        review_packet_budget: Optional collector-local
            :class:`ReviewPacketCreationBudget`. When supplied, the
            per-run packet-write exhaustion is decided by the budget's
            ``can_attempt()`` rather than by the historical filesystem
            count.

    Returns:
        :class:`EligibilityResult` with the same closed vocabulary the
        legacy ``check_incident_eligibility` used, so existing
        ``AutoLoopIncidentResult`` projection still works.
    """
    incident_id = str(incident.incident_id)

    # Status checks. SUPPRESSED / DUPLICATE / RESOLVED / READY_FOR_REVIEW
    # remain terminal and emit the legacy ``terminal_status_<value>``
    # reason so the existing skip-reason accounting is preserved.
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

    # Suggested-checks presence: keep the legacy behaviour, sourced
    # from the aggregate's signal list (the canonical heuristic before
    # the ACT).
    suggested_checks = list(getattr(incident, "signals", []) or [])
    has_suggested_checks = len(suggested_checks) > 0

    if review_packet_budget is not None:
        # R1: collector-local budget is authoritative; the historical
        # filesystem count is NOT consulted. A fresh collector always
        # starts at zero usage.
        budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = (
            review_packet_budget.as_diagnostic_for_eligibility(),
        )
        if not review_packet_budget.can_attempt():
            return EligibilityResult(
                eligible=False,
                incident_id=incident_id,
                reason="budget_exhausted",
                status=status.value,
                has_suggested_checks=has_suggested_checks,
                auto_pass_count=review_packet_budget.used,
                budget_diagnostics=budget_diagnostics,
            )
        return EligibilityResult(
            eligible=True,
            incident_id=incident_id,
            reason="active_incident_with_suggested_checks",
            status=status.value,
            has_suggested_checks=has_suggested_checks,
            auto_pass_count=0,
            budget_diagnostics=budget_diagnostics,
        )

    # Per-incident budget: count existing automatic review packets.
    auto_pass_count = _count_automatic_review_packets(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
    )

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


def check_incident_eligibility(
    *,
    incident_id: str,
    config: AutomaticDiagnosisLoopConfig,
    external_analysis_dir: Path | None = None,
) -> EligibilityResult:
    """Resolve an incident from the local store and delegate to the evaluator.

    Compatibility wrapper. ``_process_incident()`` MUST NOT call this
    function after it has already received a typed :class:`Incident`
    from :class:`BackendIncidentFound`; the scheduler-side processor
    must use :func:`evaluate_incident_eligibility` directly with the
    aggregate.

    This wrapper is retained only for local-mode callers and tests
    that exercise the legacy ID-based path. Authority selection
    belongs in the dispatch layer; this wrapper does NOT call any
    backend HTTP client and does NOT attempt to choose between
    authorities.
    """
    store = get_incident_store()
    incident = store.get_incident(incident_id)
    if incident is None:
        return EligibilityResult(
            eligible=False,
            incident_id=incident_id,
            reason="incident_not_found",
        )
    return evaluate_incident_eligibility(
        incident=incident,
        config=config,
        external_analysis_dir=external_analysis_dir,
    )

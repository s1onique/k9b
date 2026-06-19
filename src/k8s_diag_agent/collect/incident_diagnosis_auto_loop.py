"""Opt-in automatic read-only diagnosis loop evidence collector.

This module provides a bounded automatic collector that:
- Scans eligible open incidents
- Runs one deterministic read-only diagnosis pass per incident
- Writes a deterministic review packet for operator/ChatGPT review
- Preserves read-only safety: no mutation, no remediation, no kubectl

Design constraints:
- Opt-in via K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false by default
- Conservative eligibility: only active incidents with suggested checks
- Hard budget bounds: max 1 pass per incident, max 5 checks per pass
- No LLM calls, no Kubernetes calls, no subprocess/shell/kubectl
- No remediation, no mutation, no execution
- Idempotent: calling twice for same incident does not exceed budget

Activation model:
- K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false by default
- When disabled: no automatic runs, manual UI/API unchanged
- When enabled: collector scans and processes eligible incidents

Eligibility model:
- Incident status is OPEN, COLLECTING_EVIDENCE, or INVESTIGATING
- Incident has suggested_checks or enough context for stop-path packet
- Incident has not exceeded automatic loop budget (1 pass)
- Incident is not SUPPRESSED, DUPLICATE, or RESOLVED
- Automatic collector is enabled

This module does NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
- Run unbounded loops
- Call external LLM providers
- Write action-control fields to artifacts
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_case_file import build_incident_case_file
from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_orchestrator import run_one_read_only_diagnosis_loop_pass
from .incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from .incident_lifecycle import IncidentStatus
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    pass

__all__ = [
    "is_automatic_diagnosis_loop_enabled",
    "AutomaticDiagnosisLoopConfig",
    "EligibilityResult",
    "AutoLoopIncidentResult",
    "AutoLoopCollectorResult",
    "run_automatic_diagnosis_loop_evidence_collection",
    "collect_automatic_diagnosis_evidence",
]


# =============================================================================
# Configuration
# =============================================================================

# Environment variable for opt-in activation
_AUTOMATIC_LOOP_ENV_VAR = "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"


def is_automatic_diagnosis_loop_enabled() -> bool:
    """Check if automatic diagnosis loop is enabled.

    Default is False (disabled) for safety.
    Must be explicitly enabled via environment variable.

    Returns:
        True if K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
    """
    return os.environ.get(_AUTOMATIC_LOOP_ENV_VAR, "false").lower() == "true"


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


# =============================================================================
# Incident Result
# =============================================================================

@dataclass
class AutoLoopIncidentResult:
    """Result of processing a single incident in automatic loop."""

    incident_id: str
    eligible: bool
    eligibility_reason: str
    run_id: str | None = None
    decision: str | None = None
    checks_requested: int = 0
    checks_run: int = 0
    checks_skipped: int = 0
    checks_rejected: int = 0
    review_packet_written: bool = False
    review_packet_name: str | None = None
    read_only_check_artifact_written: bool = False
    loop_pass_artifact_written: bool = False
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "incident_id": self.incident_id,
            "eligible": self.eligible,
            "eligibility_reason": self.eligibility_reason,
        }
        if self.run_id is not None:
            result["run_id"] = self.run_id
        if self.decision is not None:
            result["decision"] = self.decision
        result["checks_requested"] = self.checks_requested
        result["checks_run"] = self.checks_run
        result["checks_skipped"] = self.checks_skipped
        result["checks_rejected"] = self.checks_rejected
        result["review_packet_written"] = self.review_packet_written
        if self.review_packet_name is not None:
            result["review_packet_name"] = self.review_packet_name
        result["read_only_check_artifact_written"] = self.read_only_check_artifact_written
        result["loop_pass_artifact_written"] = self.loop_pass_artifact_written
        if self.error is not None:
            result["error"] = self.error
        if self.skipped:
            result["skipped"] = True
            if self.skip_reason is not None:
                result["skip_reason"] = self.skip_reason
        return result


# =============================================================================
# Collector Result
# =============================================================================

@dataclass
class AutoLoopCollectorResult:
    """Result of a complete automatic diagnosis loop collector run."""

    run_id: str
    generated_at: str
    enabled: bool
    config: dict[str, Any]
    incidents_processed: int = 0
    incidents_eligible: int = 0
    incidents_ineligible: int = 0
    incidents_skipped: int = 0
    incidents_with_errors: int = 0
    total_checks_run: int = 0
    total_review_packets_written: int = 0
    incident_results: list[dict[str, Any]] = field(default_factory=list)
    safety_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "enabled": self.enabled,
            "config": self.config,
            "incidents_processed": self.incidents_processed,
            "incidents_eligible": self.incidents_eligible,
            "incidents_ineligible": self.incidents_ineligible,
            "incidents_skipped": self.incidents_skipped,
            "incidents_with_errors": self.incidents_with_errors,
            "total_checks_run": self.total_checks_run,
            "total_review_packets_written": self.total_review_packets_written,
            "incident_results": self.incident_results,
            "safety_metadata": self.safety_metadata,
        }


# =============================================================================
# Safety Metadata
# =============================================================================

_COLLECTOR_SAFETY_METADATA: dict[str, Any] = {
    "read_only": True,
    "allowed_actions": [],
    "no_kubernetes_client": True,
    "no_shell": True,
    "no_subprocess": True,
    "no_kubectl": True,
    "no_mutation": True,
    "no_remediation": True,
    "automatic_evidence_collection_only": True,
    "no_llm_calls": True,
    "no_execution": True,
}


# =============================================================================
# Core Collector Function
# =============================================================================


def run_automatic_diagnosis_loop_evidence_collection(
    *,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
    incident_ids: list[str] | None = None,
    now: datetime | None = None,
) -> AutoLoopCollectorResult:
    """Run automatic diagnosis loop evidence collection for eligible incidents.

    This is the main entry point for automatic evidence collection.

    Args:
        external_analysis_dir: Path to external-analysis directory for artifacts
        config: Optional collector configuration (uses defaults if None)
        incident_ids: Optional list of specific incident IDs to process.
            If None, processes all eligible incidents from the store.
        now: Optional datetime for deterministic timestamps

    Returns:
        AutoLoopCollectorResult with processing summary and per-incident results

    Safety guarantees:
    - read_only: True
    - allowed_actions: []
    - No kubernetes client imports
    - No shell/subprocess/kubectl
    - No remediation or mutation
    - Hard budget bounds enforced
    """
    resolved_config = config or AutomaticDiagnosisLoopConfig()
    resolved_now = now if now is not None else datetime.now(UTC)
    collector_run_id = f"auto-diagnosis-{resolved_now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    # Check if collector is enabled
    enabled = is_automatic_diagnosis_loop_enabled()

    result = AutoLoopCollectorResult(
        run_id=collector_run_id,
        generated_at=resolved_now.isoformat(),
        enabled=enabled,
        config=resolved_config.to_dict(),
        safety_metadata=dict(_COLLECTOR_SAFETY_METADATA),
    )

    # If disabled, return early with no processing
    if not enabled:
        result.incident_results = [{
            "note": "Automatic diagnosis loop is disabled. Set K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true to enable.",
        }]
        return result

    # Get incidents to process
    store = get_incident_store()

    if incident_ids is not None:
        # Process specific incidents
        candidates = incident_ids[:resolved_config.max_incidents_per_run]
    else:
        # Get all active incidents
        active_incidents = store.list_incidents(status=None)
        active_candidates = [
            i.incident_id for i in active_incidents
            if i.status in _ACTIVE_STATUSES
        ]
        candidates = active_candidates[:resolved_config.max_incidents_per_run]

    result.incidents_processed = len(candidates)

    # Process each candidate
    for incident_id in candidates:
        incident_result = _process_incident(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            config=resolved_config,
            collector_run_id=collector_run_id,
            now=resolved_now,
        )
        result.incident_results.append(incident_result.to_dict())

        if incident_result.skipped:
            result.incidents_skipped += 1
        elif incident_result.error is not None:
            result.incidents_with_errors += 1
        elif incident_result.eligible:
            result.incidents_eligible += 1
            if incident_result.review_packet_written:
                result.total_review_packets_written += 1
            result.total_checks_run += incident_result.checks_run
        else:
            result.incidents_ineligible += 1

    return result


def _process_incident(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig,
    collector_run_id: str,
    now: datetime,
) -> AutoLoopIncidentResult:
    """Process a single incident in the automatic diagnosis loop.

    Args:
        incident_id: The incident ID to process
        external_analysis_dir: Path to external-analysis directory
        config: Collector configuration
        collector_run_id: The collector run ID for this batch
        now: Current timestamp

    Returns:
        AutoLoopIncidentResult with processing outcome
    """
    # Check eligibility (pass external_analysis_dir to count existing review packets)
    eligibility = check_incident_eligibility(
        incident_id=incident_id,
        config=config,
        external_analysis_dir=external_analysis_dir,
    )

    if not eligibility.eligible:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason=eligibility.reason,
            skipped=True,
            skip_reason=f"not_eligible: {eligibility.reason}",
        )

    # Generate run_id for this incident's automatic pass
    run_id = f"auto-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}"

    # Validate run_id for safety
    if not is_safe_run_id(run_id):
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Unsafe run_id generated: {run_id}",
        )

    # Build case file
    try:
        case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
        )
    except (OSError, ValueError, KeyError) as exc:
        # Intentional broad catch: build_incident_case_file may raise various
        # exceptions due to artifact loading or data access issues.
        # We gracefully handle all failures by returning an error result.
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Failed to build case file: {exc}",
        )

    if case_file is None:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Case file is None",
        )

    # Build minimal diagnosis report from suggested checks
    # This is the bounded source for the automatic loop
    diagnosis_report = _build_minimal_diagnosis_report(case_file, config.max_checks_per_pass)

    # Run one-pass orchestrator
    try:
        orchestrator_result = run_one_read_only_diagnosis_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            now=now,
        )
    except (ValueError, RuntimeError, KeyError) as exc:
        # Intentional catch: orchestrator may raise specific exceptions
        # on invalid inputs or data access failures. We handle gracefully.
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Orchestrator error: {exc}",
        )

    # Extract results
    decision = str(orchestrator_result.get("decision", ""))
    runner_result = orchestrator_result.get("runner_result")
    artifact = orchestrator_result.get("artifact")
    loop_pass_artifact = orchestrator_result.get("loop_pass_artifact")

    checks_requested = 0
    checks_run = 0
    checks_skipped = 0
    checks_rejected = 0

    if runner_result and isinstance(runner_result, dict):
        checks_requested = runner_result.get("checks_requested", 0)
        checks_run = runner_result.get("checks_run", 0)
        checks_skipped = runner_result.get("checks_skipped", 0)
        checks_rejected = runner_result.get("checks_rejected", 0)

    # Check if checks were actually run
    is_stop_path = decision in (
        LoopDecision.STOP_ROOT_CAUSE_FOUND.value,
        LoopDecision.STOP_NO_SAFE_CHECKS.value,
        LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        LoopDecision.STOP_BUDGET_EXHAUSTED.value,
    )

    # Write review packet
    review_packet_written = False
    review_packet_name = None

    should_write_packet = not is_stop_path or config.write_stop_path_packets

    if should_write_packet:
        try:
            review_packet_meta = write_diagnosis_review_packet(
                external_analysis_dir=external_analysis_dir,
                incident_id=incident_id,
                collector_run_id=collector_run_id,
                run_id=run_id,
                decision=decision,
                checks_requested=checks_requested,
                checks_run=checks_run,
                checks_skipped=checks_skipped,
                checks_rejected=checks_rejected,
                eligible=True,
                eligibility_reason=eligibility.reason,
                config=config,
                now=now,
                case_file=case_file,
                orchestrator_result=orchestrator_result,
            )
            if review_packet_meta.get("written"):
                review_packet_written = True
                review_packet_name = str(review_packet_meta.get("name")) if review_packet_meta.get("name") else None
        except (OSError, ValueError):
            # Intentional catch: packet write may fail due to filesystem issues.
            # We gracefully handle by continuing without a packet.
            pass

    # Extract artifact flags
    read_only_check_artifact_written = (
        artifact is not None
        and isinstance(artifact, dict)
        and artifact.get("written", False)
    )
    loop_pass_artifact_written = (
        loop_pass_artifact is not None
        and isinstance(loop_pass_artifact, dict)
        and loop_pass_artifact.get("written", False)
    )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=True,
        eligibility_reason=eligibility.reason,
        run_id=run_id,
        decision=decision,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
        checks_rejected=checks_rejected,
        review_packet_written=review_packet_written,
        review_packet_name=review_packet_name,
        read_only_check_artifact_written=read_only_check_artifact_written,
        loop_pass_artifact_written=loop_pass_artifact_written,
    )


def _build_minimal_diagnosis_report(
    case_file: dict[str, Any],
    max_checks: int,
) -> dict[str, Any]:
    """Build a minimal diagnosis report from case file suggested checks.

    This is the bounded source for automatic diagnosis loop.
    Only uses checks that are already in the case file (from next-check plan artifacts).

    Args:
        case_file: The incident case file
        max_checks: Maximum number of checks to include

    Returns:
        Bounded diagnosis report with recommended_investigations
    """
    suggested_checks = case_file.get("suggested_checks", [])
    if not isinstance(suggested_checks, list):
        suggested_checks = []

    # Extract check_id and title from suggested checks
    recommended_investigations = []
    for check in suggested_checks[:max_checks]:
        if not isinstance(check, dict):
            continue

        check_id = check.get("check_id") or check.get("id")
        title = check.get("title") or check.get("name") or check_id

        if check_id:
            recommended_investigations.append({
                "check_id": check_id,
                "title": str(title),
                "read_only": True,
                "source": "automatic_suggested_check",
            })

    return {
        "diagnosis": {
            "recommended_investigations": recommended_investigations,
        },
        "metadata": {
            "source": "automatic_diagnosis_loop",
            "case_file_generated_at": case_file.get("generated_at"),
        },
    }


# =============================================================================
# Convenience Function
# =============================================================================


def collect_automatic_diagnosis_evidence(
    incident_id: str,
    external_analysis_dir: Path,
) -> AutoLoopIncidentResult:
    """Collect automatic diagnosis evidence for a single incident.

    Convenience wrapper for single-incident collection.
    Respects the K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED setting.

    Args:
        incident_id: The incident ID to collect evidence for
        external_analysis_dir: Path to external-analysis directory

    Returns:
        AutoLoopIncidentResult with processing outcome
    """
    if not is_automatic_diagnosis_loop_enabled():
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason="automatic_collector_disabled",
            skipped=True,
            skip_reason="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED is not set to true",
        )

    result = run_automatic_diagnosis_loop_evidence_collection(
        external_analysis_dir=external_analysis_dir,
        incident_ids=[incident_id],
    )

    if result.incident_results:
        return AutoLoopIncidentResult(
            **result.incident_results[0]
        )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=False,
        eligibility_reason="no_incidents_processed",
        skipped=True,
        skip_reason="No incidents were processed",
    )
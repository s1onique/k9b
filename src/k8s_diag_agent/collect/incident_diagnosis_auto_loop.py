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

This module does NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
- Run unbounded loops
- Call external LLM providers
- Write action-control fields to artifacts
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_case_file import build_incident_case_file
from .incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    EligibilityResult,
    check_incident_eligibility,
    is_automatic_diagnosis_loop_enabled,
)
from .incident_diagnosis_auto_loop_models import (
    _COLLECTOR_SAFETY_METADATA,
    AutoLoopCollectorResult,
    AutoLoopIncidentResult,
)
from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_runtime import run_policy_enforced_loop_pass
from .incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store import IncidentStore
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
    # collect_automatic_diagnosis_evidence is available via lazy import
    # from .incident_diagnosis_auto_loop_entrypoints
]


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
    from .incident_diagnosis_auto_loop_config import _ACTIVE_STATUSES  # Import here to avoid circular

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

    Note:
        Emits DIAGNOSIS_LOOP_STARTED, DIAGNOSIS_LOOP_COMPLETED, and
        DIAGNOSIS_LOOP_FAILED events to the incident timeline.
    """
    store: IncidentStore = get_incident_store()

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
            budget_diagnostics=eligibility.budget_diagnostics,
        )

    # Generate run_id for this incident's automatic pass
    run_id = f"auto-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}"

    # Validate run_id for safety
    if not is_safe_run_id(run_id):
        # Emit failure event for unsafe run_id
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="unsafe_run_id",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Unsafe run_id generated: {run_id}",
        )

    # Emit DIAGNOSIS_LOOP_STARTED event
    store.mark_diagnosis_loop_started(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
    )

    # Build case file
    try:
        case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
        )
    except (OSError, ValueError, KeyError):
        # Emit failure event for case file build failure
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="case_file_error",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Failed to build case file",
        )

    if case_file is None:
        # Emit failure event for None case file
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="case_file_none",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Case file is None",
        )

    # Build minimal diagnosis report from suggested checks
    diagnosis_report = _build_minimal_diagnosis_report(case_file, config.max_checks_per_pass)

    # Run one-pass orchestrator with policy enforcement
    # This wraps the orchestrator with:
    # - Hard budget limits (max_passes, max_checks)
    # - Safety gates (mutating, sensitive, duplicates)
    # - Pass artifact with exact PASS_ARTIFACT_FIELDS
    # - OTel span emission
    try:
        orchestrator_result = run_policy_enforced_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            now=now,
        )
    except (ValueError, RuntimeError, KeyError):
        # Emit failure event for orchestrator error
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="orchestrator_error",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Orchestrator error",
        )

    # Extract results from policy-enforced result
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
            pass

    # Emit DIAGNOSIS_LOOP_COMPLETED event
    store.mark_diagnosis_loop_completed(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        review_packet_name=review_packet_name,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_rejected=checks_rejected,
        decision=decision if decision else None,
    )

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


# Backwards compatibility import - the single-incident entrypoint was extracted
# to keep this module under the LLM-friendly size limit.
# Import lazily to avoid circular dependency.
def __getattr__(name: str) -> object:
    if name == "collect_automatic_diagnosis_evidence":
        from .incident_diagnosis_auto_loop_entrypoints import collect_automatic_diagnosis_evidence
        return collect_automatic_diagnosis_evidence
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

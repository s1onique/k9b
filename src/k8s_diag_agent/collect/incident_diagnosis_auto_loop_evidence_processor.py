"""Evidence collection processor for automatic diagnosis loop.

This module contains:
- _process_incident(): Process a single incident in the automatic diagnosis loop
- _build_minimal_diagnosis_report(): Build a minimal diagnosis report from case file
- _write_loop_summary(): Write loop summary artifact

These functions handle per-incident processing for the evidence collector.

The backend incident-detail lookup is consumed through the typed
:class:`BackendIncidentLookupOutcome` algebra defined in
:mod:`k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes`.
A successful HTTP 200 response cannot be converted into
``BackendIncidentNotFound`` by any parser/schema/deserialization/
identity failure in this seam.

Authority flow (ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01):

    typed authority lookup
        ↓
    BackendIncidentFound
        ↓
    identity validation (branded id matches request)
        ↓
    evaluate_incident_eligibility(incident=incident_obj, ...)  [no second lookup]
        ↓
    case-file construction from the same aggregate
        ↓
    diagnosis execution
        ↓
    record_diagnosis_loop_{started,failed,completed}(...)  [authority seam]

The processor NEVER reaches ``get_incident_store()`` to re-resolve
the incident or to record a lifecycle transition. Lifecycle writes
route through :mod:`incident_diagnosis_authority_seam` which resolves
the same dispatch configuration the lookup uses.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
R1 follow-up: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from k8s_diag_agent.domain.incident_lifecycle import IncidentId

from .incident_automatic_diagnosis_loop import (
    HypothesisLoopConfig,
    run_automatic_diagnosis_hypothesis_loop,
)
from .incident_case_file import build_incident_case_file
from .incident_diagnosis_authority_seam import (
    LifecycleWriteApplied,
    LifecycleWriteFailed,
    LifecycleWriteOutcome,
    LifecycleWriteRejected,
    LifecycleWriteSkipped,
    evaluate_incident_eligibility,
    record_diagnosis_loop_completed,
    record_diagnosis_loop_failed,
    record_diagnosis_loop_started,
)
from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
from .incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupFailed,
    BackendIncidentNotFound,
)
from .incident_diagnosis_dispatch import (
    fetch_backend_incident_for_diagnosis_typed,
)
from .incident_diagnosis_disposition import (
    diagnosis_failure_reason_for_backend_lookup,
)
from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_runtime import run_policy_enforced_loop_pass
from .incident_diagnosis_review_packet import write_diagnosis_review_packet
from .incident_diagnosis_review_packet_budget import ReviewPacketCreationBudget
from .incident_lifecycle import Incident
from .incident_read_only_check_artifacts import is_safe_run_id

_logger = logging.getLogger(__name__)

__all__ = [
    "HypothesisLoopConfig",
    "run_automatic_diagnosis_hypothesis_loop",
    "_build_minimal_diagnosis_report",
    "_process_incident",
    "_write_loop_summary",
]


def _failure_result_from_outcome(
    incident_id: str,
    outcome: BackendIncidentLookupFailed,
) -> AutoLoopIncidentResult:
    """Translate a typed ``BackendIncidentLookupFailed`` into a legacy result.

    The reason string is the ``.value`` of the typed
    :class:`DiagnosisEvaluationFailureReason` resolved by
    :func:`diagnosis_failure_reason_for_backend_lookup`. Production code
    never rebuilds the mapping itself; the compat layer matches this
    string exactly (no substring), so the round-trip is lossless.
    """
    typed_reason = diagnosis_failure_reason_for_backend_lookup(outcome.failure_code)
    reason_code = typed_reason.value
    diagnostic = outcome.to_diagnostic()
    detail_parts: list[str] = []
    if diagnostic.detail:
        detail_parts.append(diagnostic.detail)
    diagnostic_payload = (
        f"http_status={diagnostic.http_status} "
        f"payload_type={diagnostic.payload_type!r} "
        f"payload_schema_version={diagnostic.payload_schema_version} "
        f"exception_type={diagnostic.exception_type!r}"
    )
    detail_parts.append(diagnostic_payload)
    detail = " | ".join(detail_parts)

    _logger.info(
        "automatic-diagnosis-backend-incident-lookup-failed",
        extra={
            "event": "automatic-diagnosis-backend-incident-lookup-failed",
            "incident_id": incident_id,
            "requested_incident_id": str(outcome.requested_incident_id),
            "reason_code": reason_code,
            "http_status": outcome.http_status,
            "payload_type": outcome.payload_type,
            "payload_schema_version": outcome.payload_schema_version,
            "exception_type": outcome.exception_type,
            "detail": detail,
        },
    )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=False,
        eligibility_reason=reason_code,
        error=detail,
    )


def _emit_eligibility_evaluated_event(
    *,
    incident_id: str,
    incident_source: str,
    eligible: bool,
    reason_code: str,
) -> None:
    """Emit a bounded eligibility-evaluated event after the lookup seam."""
    _logger.info(
        "automatic-diagnosis-incident-eligibility-evaluated",
        extra={
            "event": "automatic-diagnosis-incident-eligibility-evaluated",
            "incident_id": incident_id,
            "incident_source": incident_source,
            "eligible": eligible,
            "reason_code": reason_code,
        },
    )


def _lifecycle_outcome_is_failure(outcome: LifecycleWriteOutcome) -> bool:
    """Return True for any non-Applied lifecycle outcome (excluding Skipped)."""
    return isinstance(
        outcome,
        (LifecycleWriteFailed, LifecycleWriteRejected),
    )


def _process_incident(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig,
    collector_run_id: str,
    now: datetime,
    review_packet_budget: ReviewPacketCreationBudget | None = None,
) -> AutoLoopIncidentResult:
    """Process a single incident in the automatic diagnosis loop.

    The backend incident-detail lookup runs through the canonical
    :func:`fetch_backend_incident_for_diagnosis_typed` helper, which
    returns a typed :class:`BackendIncidentLookupOutcome`. The three
    variants are dispatched exhaustively:

    * ``BackendIncidentNotFound`` → skipped with
      ``skip_reason="incident_not_found"`` and
      ``eligibility_reason="not_found"``.
    * ``BackendIncidentLookupFailed`` → error with the mapped stable
      reason code; never maps to ``incident_not_found``.
    * ``BackendIncidentFound(incident=incident)`` → identity check
      against the requested ID, then the aggregate-based
      :func:`evaluate_incident_eligibility` (no second incident
      lookup), then case-file construction from the same aggregate,
      then authority-routed lifecycle writes.

    Crucially:

    * the eligibility evaluator is invoked with the supplied
      ``Incident`` aggregate; ``get_incident_store()`` is NOT called
      between ``BackendIncidentFound`` and the eligibility decision;
    * lifecycle transitions are routed through
      :func:`record_diagnosis_loop_*`; the local
      ``IncidentStore.mark_diagnosis_loop_*`` methods are NOT called
      from this function.
    """
    branded = IncidentId(incident_id)
    lookup_outcome = fetch_backend_incident_for_diagnosis_typed(branded)

    # Exhaustive dispatch on the three typed variants. The legacy
    # ``AutoLoopIncidentResult`` is the source of truth for the rest of
    # the pipeline; the compat layer maps it back into the typed
    # ``IncidentDiagnosisDisposition`` algebra.
    match lookup_outcome:
        case BackendIncidentNotFound():
            _logger.info(
                "automatic-diagnosis-backend-incident-not-found",
                extra={
                    "event": "automatic-diagnosis-backend-incident-not-found",
                    "incident_id": incident_id,
                    "http_status": lookup_outcome.http_status,
                },
            )
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason="not_found",
                skipped=True,
                skip_reason="incident_not_found",
            )
        case BackendIncidentLookupFailed():
            return _failure_result_from_outcome(incident_id, lookup_outcome)
        case BackendIncidentFound(incident=incident):
            _logger.info(
                "automatic-diagnosis-backend-incident-found",
                extra={
                    "event": "automatic-diagnosis-backend-incident-found",
                    "incident_id": incident_id,
                    "requested_incident_id": incident_id,
                    "http_status": lookup_outcome.http_status,
                    "payload_schema_version": lookup_outcome.payload_schema_version,
                    "payload_type": lookup_outcome.payload_type,
                },
            )
            incident_obj: Incident = incident
            incident_source = lookup_outcome.source.value

    # INV-01: identity invariant. The aggregate's incident_id MUST
    # match the requested branded ID. A mismatch becomes a typed
    # lookup/content failure (we surface it as an evaluation failure,
    # not an ``incident_not_found``) and we never silently fall back
    # to the local store.
    if str(incident_obj.incident_id) != str(branded):
        mismatch_detail = (
            f"backend returned incident_id {str(incident_obj.incident_id)!r} "
            f"but the request was for {str(branded)!r}"
        )
        _logger.warning(
            "automatic-diagnosis-incident-identity-mismatch",
            extra={
                "event": "automatic-diagnosis-incident-identity-mismatch",
                "incident_id": incident_id,
                "returned_incident_id": str(incident_obj.incident_id),
                "reason_code": "identity_mismatch",
                "detail": mismatch_detail,
            },
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason="backend_incident_identity_mismatch",
            error=mismatch_detail,
        )

    # INV-02: aggregate-based eligibility evaluation. The supplied
    # incident is the authoritative snapshot; we do NOT re-resolve
    # through ``get_incident_store()`` here. R1: when the collector
    # supplies a ``review_packet_budget``, that budget is the
    # authoritative accounting source; the historical filesystem count
    # of review-packet artifacts is bypassed so a fresh collector
    # starts at zero usage.
    eligibility = evaluate_incident_eligibility(
        incident=incident_obj,
        config=config,
        external_analysis_dir=external_analysis_dir,
        review_packet_budget=review_packet_budget,
    )

    _emit_eligibility_evaluated_event(
        incident_id=incident_id,
        incident_source=incident_source,
        eligible=eligibility.eligible,
        reason_code=eligibility.reason,
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

    run_id = f"auto-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}"

    if not is_safe_run_id(run_id):
        # INV-08: lifecycle failure must not be swallowed. We record
        # the ``failed`` transition through the seam and surface the
        # outcome to the caller.
        lifecycle = record_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="unsafe_run_id",
        )
        if isinstance(lifecycle, LifecycleWriteFailed):
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason=eligibility.reason,
                run_id=run_id,
                error=(
                    f"Unsafe run_id generated: {run_id} "
                    f"(lifecycle start failed: {lifecycle.reason_code})"
                ),
            )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Unsafe run_id generated: {run_id}",
        )

    # INV-05/INV-08: lifecycle writes are routed through the authority
    # seam. If the start write fails the diagnosis execution MUST NOT
    # begin; we return an unsuccessful result with the bounded
    # reason code.
    started_outcome = record_diagnosis_loop_started(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
    )
    if not isinstance(started_outcome, LifecycleWriteApplied):
        failure_code = _lifecycle_failure_code(started_outcome)
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"diagnosis_lifecycle_start_failed: {failure_code}",
        )

    # Build case file using the original Incident object
    try:
        case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            incident=incident_obj,
        )
    except (OSError, ValueError, KeyError) as exc:
        # INV-08: keep the original failure primary and attach the
        # lifecycle-recording diagnostics when the ``failed`` write
        # itself did not land.
        lifecycle_outcome = _record_failure_with_original(
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
            error=_augment_error_with_lifecycle(
                f"Failed to build case file: {type(exc).__name__}",
                lifecycle_outcome,
            ),
        )

    if case_file is None:
        lifecycle_outcome = _record_failure_with_original(
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
            error=_augment_error_with_lifecycle(
                "Case file is None", lifecycle_outcome
            ),
        )


    # Run hypothesis burst multipass loop
    hypothesis_loop_result: dict[str, Any] | None = None
    try:
        loop_config = HypothesisLoopConfig(
            max_passes_per_incident=min(config.max_passes_per_incident, 2),
            max_checks_per_pass=config.max_checks_per_pass,
            max_total_checks=config.max_checks_per_pass * 2,
            max_seconds_per_incident=config.max_seconds_per_incident,
            min_confidence_to_stop=0.78,
        )

        loop_result = run_automatic_diagnosis_hypothesis_loop(
            incident=incident_obj.to_dict(),
            case_file=case_file,
            external_analysis_dir=external_analysis_dir,
            run_id=run_id,
            collector_run_id=collector_run_id,
            config=loop_config,
            now=now,
        )
        hypothesis_loop_result = loop_result.to_dict()

    except Exception as e:
        _logger.warning(
            "Hypothesis loop failed, continuing with policy-enforced path",
            extra={
                "event": "hypothesis-loop-failed",
                "incident_id": incident_id,
                "run_id": run_id,
                "error": str(e),
            },
        )

    diagnosis_report = _build_minimal_diagnosis_report(case_file, config.max_checks_per_pass)

    try:
        orchestrator_result = run_policy_enforced_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            now=now,
        )
    except (ValueError, RuntimeError, KeyError) as exc:
        lifecycle_outcome = _record_failure_with_original(
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
            error=_augment_error_with_lifecycle(
                f"orchestrator error: {type(exc).__name__}",
                lifecycle_outcome,
            ),
        )


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

    is_stop_path = decision in (
        LoopDecision.STOP_ROOT_CAUSE_FOUND.value,
        LoopDecision.STOP_NO_SAFE_CHECKS.value,
        LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        LoopDecision.STOP_BUDGET_EXHAUSTED.value,
    )

    review_packet_written = False
    review_packet_name = None

    should_write_packet = not is_stop_path or config.write_stop_path_packets
    budget = review_packet_budget
    budget_exhausted_skip = False

    if should_write_packet:
        if budget is not None and not budget.can_attempt():
            budget_exhausted_skip = True
        else:
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
                    review_packet_name = (
                        str(review_packet_meta.get("name"))
                        if review_packet_meta.get("name")
                        else None
                    )
                    if budget is not None and review_packet_name:
                        try:
                            budget.record_successful_write()
                        except RuntimeError:
                            budget_exhausted_skip = True
            except (OSError, ValueError):
                pass
    if budget_exhausted_skip and not review_packet_written:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            skipped=True,
            skip_reason=(
                f"not_eligible: review_packet_budget_exhausted: "
                f"collector={collector_run_id}"
            ),
            budget_diagnostics=(
                (budget.as_diagnostic_for_eligibility(),)
                if budget is not None
                else ()
            ),
        )

    completed_outcome = record_diagnosis_loop_completed(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        review_packet_name=review_packet_name,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_rejected=checks_rejected,
        decision=decision if decision else None,
    )

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

    result = AutoLoopIncidentResult(
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
        hypothesis_loop_result=hypothesis_loop_result,
    )
    if not isinstance(completed_outcome, LifecycleWriteApplied):
        result.error = (
            f"diagnosis_lifecycle_completion_failed: "
            f"{_lifecycle_failure_code(completed_outcome)}"
        )
    return result


def _lifecycle_failure_code(outcome: LifecycleWriteOutcome) -> str:
    """Extract a stable reason code from any non-Applied lifecycle outcome."""
    if isinstance(outcome, LifecycleWriteFailed):
        return outcome.reason_code
    if isinstance(outcome, LifecycleWriteRejected):
        return outcome.reason_code
    if isinstance(outcome, LifecycleWriteSkipped):
        return f"skipped:{outcome.reason}"
    return "unknown"


def _augment_error_with_lifecycle(
    base_error: str,
    lifecycle_outcome: LifecycleWriteOutcome,
) -> str:
    """Keep the original failure primary and attach lifecycle diagnostics.

    INV-08: when recording the ``failed`` transition itself did not
    land (e.g. the backend returned 5xx), the per-incident result must
    surface both the original failure and the lifecycle-persistence
    diagnostics rather than discarding the latter into logs only.

    Example produced shape::

        Failed to build case file: KeyError; \
lifecycle_recording_error=backend_error; http_status=500
    """
    if isinstance(lifecycle_outcome, LifecycleWriteApplied | LifecycleWriteSkipped):
        return base_error
    parts = [base_error, f"lifecycle_recording_error={lifecycle_outcome.reason_code}"]
    http_status = getattr(lifecycle_outcome, "http_status", None)
    if http_status is not None:
        parts.append(f"http_status={http_status}")
    return "; ".join(parts)


def _record_failure_with_original(
    *,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    unavailable_reason: str,
) -> LifecycleWriteOutcome:
    """Record a ``failed`` transition through the authority seam.


    Returns the underlying outcome so callers can attach lifecycle
    persistence diagnostics to the per-incident result when needed.
    """
    return record_diagnosis_loop_failed(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        unavailable_reason=unavailable_reason,
    )


def _build_minimal_diagnosis_report(
    case_file: dict[str, Any],
    max_checks: int,
) -> dict[str, Any]:
    """Build a minimal diagnosis report from case file suggested checks."""
    suggested_checks = case_file.get("suggested_checks", [])
    if not isinstance(suggested_checks, list):
        suggested_checks = []

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


def _write_loop_summary(
    external_analysis_dir: Path,
    collector_run_id: str,
    incidents_seen: int,
    incidents_eligible: int,
    incidents_processed: int,
    hypothesis_bursts_written: int,
    total_passes_completed: int,
    total_checks_executed: int,
    stop_reason: str,
    incident_results: list[dict[str, Any]],
    run_id: str | None = None,
    *,
    skip_reasons: dict[str, int] | None = None,
    ineligible_reasons: dict[str, int] | None = None,
    error_reasons: dict[str, int] | None = None,
    incidents_skipped: int = 0,
    incidents_ineligible: int = 0,
    incidents_with_errors: int = 0,
    eligibility_schema_version: int = 2,
) -> dict[str, Any]:
    """Write loop summary artifact."""
    from .incident_automatic_diagnosis_loop import write_summary_artifact as _write_summary_artifact
    from .incident_diagnosis_authority_run_summary import (
        summarize_incident_results,
    )

    artifact_dir = external_analysis_dir / "automatic-diagnosis"
    effective_run_id = run_id if run_id else f"collector-{collector_run_id}"

    # Authority run-summary accounting (backend lookup / eligibility /
    # lifecycle-write outcomes + the split-authority regression counter)
    # derived deterministically from the per-incident results.
    authority_run_summary = summarize_incident_results(incident_results).to_dict()

    return _write_summary_artifact(
        artifact_dir=artifact_dir,
        run_id=effective_run_id,
        collector_run_id=collector_run_id,
        incidents_seen=incidents_seen,
        incidents_eligible=incidents_eligible,
        incidents_processed=incidents_processed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        stop_reason=stop_reason,
        incident_results=incident_results,
        skip_reasons=skip_reasons,
        ineligible_reasons=ineligible_reasons,
        error_reasons=error_reasons,
        incidents_skipped=incidents_skipped,
        incidents_ineligible=incidents_ineligible,
        incidents_with_errors=incidents_with_errors,
        eligibility_schema_version=eligibility_schema_version,
        authority_run_summary=authority_run_summary,
    )



__all__ = [
    "_process_incident",
    "_build_minimal_diagnosis_report",
    "_write_loop_summary",
]

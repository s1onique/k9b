"""Automatic diagnosis loop evidence collection integration for health loop.

This module provides integration between the health loop and the automatic
diagnosis evidence collector, enabling opt-in automatic evidence collection
for eligible incidents.

Design constraints:
- Opt-in via K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false by default
- Read-only only: no mutation, no remediation, no kubectl
- Bounded: max incidents, passes, and checks per run
- Idempotent: budget tracking prevents repeated passes
- Failure isolation: collector errors do not crash the health loop

The completion event now includes ``skip_reasons`` / ``ineligible_reasons``
/ ``error_reasons`` projected from the typed disposition summary, plus
``eligibility_schema_version``. Operators who already inspect the
"Automatic diagnosis loop completed" event now also see why incidents
were skipped without having to read a separate aggregate event.

Canonical-incident-identity propagation:
    When the scheduler has just completed an Alertmanager promotion, the
    backend-owned canonical ``incident_id`` values are passed straight into
    the evidence collector via ``canonical_incident_ids``. This avoids the
    candidate-ID synthesis path entirely: the dispatcher must NOT synthesize
    IDs from namespace, kind, or label values when canonical IDs are
    available.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    is_automatic_diagnosis_loop_enabled,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "run_automatic_diagnosis_loop",
]


def _projection_from_result(result: Any) -> dict[str, Any]:
    """Project reason maps from a typed ``disposition_summary`` (or fall back).

    Falls back to empty maps when the collector did not produce a typed
    summary (e.g. when invoked through compatibility shims that only
    return scalar counters).
    """
    summary = getattr(result, "disposition_summary", None)
    if summary is None:
        return {
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
            "eligibility_schema_version": 2,
        }
    return {
        "skip_reasons": {k.value: v for k, v in summary.skip_reasons.items()},
        "ineligible_reasons": {k.value: v for k, v in summary.ineligible_reasons.items()},
        "error_reasons": {k.value: v for k, v in summary.error_reasons.items()},
        "eligibility_schema_version": 2,
    }


def _coerce_canonical_ids(
    canonical_incident_ids: Any,
) -> list[str] | None:
    """Coerce the canonical-incident-IDs argument into a list of strings.

    Accepts:
    - None (no canonical IDs supplied; fall back to scan-based listing)
    - a list/tuple of strings
    - any iterable of strings

    Returns ``None`` when the argument is missing or empty so the caller
    can decide whether to bypass the canonical-ID path entirely.
    """
    if canonical_incident_ids is None:
        return None
    if isinstance(canonical_incident_ids, (list, tuple)):
        ids = [str(value) for value in canonical_incident_ids if value]
    else:
        try:
            ids = [str(value) for value in canonical_incident_ids if value]
        except TypeError:
            return None
    if not ids:
        return None
    return ids


def run_automatic_diagnosis_loop(
    *,
    external_analysis_dir: Path,
    log_event_fn: Any | None = None,
    scheduler_run_id: str | None = None,
    canonical_incident_ids: Any | None = None,
    promotion_result_summary: dict[str, Any] | None = None,
    backend_endpoint_identity: dict[str, Any] | None = None,
    incident_selection_mode: str | None = None,
) -> dict[str, Any]:
    """Run automatic diagnosis loop evidence collection.

    This is the health loop integration point for automatic evidence collection.
    It is gated by K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED environment variable.

    When ``canonical_incident_ids`` is non-empty (typically because the
    scheduler just completed an Alertmanager promotion through the backend),
    the evidence collector is invoked in ``incident_ids`` mode and skips
    the candidate-ID synthesis path entirely. This preserves the
    backend-owned canonical ``incident_id`` boundary across promotion
    and automatic diagnosis.

    R7 (item 1): the orchestrator can pass ``incident_selection_mode``
    ``"blocked"`` to short-circuit the collector with a typed
    ``automatic_diagnosis_blocked`` event. The collector MUST NOT
    invoke ``run_automatic_diagnosis_loop_evidence_collection`` on
    the blocked path; doing so would silently fall back to scan
    mode and hide the dispatcher regression. The access mode carried
    in the response is the preserved value supplied via
    ``backend_endpoint_identity`` (or the ``promotion_result_summary``
    fallback) so a local zero-ID run keeps
    ``incident_access_mode == "local"`` and a no-promotion run keeps
    ``incident_access_mode == "no_promotion_run"`` instead of being
    collapsed onto the legacy ``"backend"`` default (R7 item 2).
    """
    explicit_ids = _coerce_canonical_ids(canonical_incident_ids)

    # R7 (item 2): derive ``incident_access_mode`` from the supplied
    # metadata. The value comes from
    # ``backend_endpoint_identity.incident_access_mode`` first, then the
    # ``promotion_result_summary`` fallback, and finally an explicit
    # ``"no_promotion_run"`` sentinel. The function NO LONGER falls
    # back to ``"backend"`` when no canonical IDs are supplied -- a
    # local zero-ID run keeps ``"local"`` and a no-promotion run keeps
    # ``"no_promotion_run"``.
    access_mode = "no_promotion_run"
    if isinstance(backend_endpoint_identity, dict):
        candidate_mode = backend_endpoint_identity.get("incident_access_mode")
        if isinstance(candidate_mode, str) and candidate_mode:
            access_mode = candidate_mode
    if (
        access_mode == "no_promotion_run"
        and isinstance(promotion_result_summary, dict)
    ):
        candidate_mode = promotion_result_summary.get("incident_access_mode")
        if isinstance(candidate_mode, str) and candidate_mode:
            access_mode = candidate_mode

    # R7 (item 1): the orchestrator can mark the run as blocked. The
    # collector emits the structured blocked event and returns a
    # bounded payload so the terminal-completion event can carry the
    # reason downstream. The collector MUST NOT touch the underlying
    # evidence collection in this case.
    if incident_selection_mode == "blocked":
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis blocked: "
                "promotion_consistency_contract_error",
                event="automatic_diagnosis_blocked",
                blocked_reason="promotion_consistency_contract_error",
                incident_access_mode=access_mode,
                selection_mode="blocked",
            )
        return {
            "automatic_diagnosis_enabled": True,
            "collector_run_id": None,
            "incidents_processed": 0,
            "incidents_eligible": 0,
            "incidents_skipped": 0,
            "incidents_with_errors": 0,
            "total_review_packets_written": 0,
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
            "eligibility_schema_version": 2,
            "incident_access_mode": access_mode,
            "explicit_canonical_id_count": (
                len(explicit_ids) if explicit_ids else 0
            ),
            "promotion_propagated_to_diagnosis": bool(explicit_ids),
            "selection_mode": "blocked",
            "blocked_reason": "promotion_consistency_contract_error",
        }

    enabled = is_automatic_diagnosis_loop_enabled()

    if not enabled:
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis loop is disabled",
                event="disabled",
                explicit_canonical_id_count=len(explicit_ids) if explicit_ids else 0,
            )
        return {
            "automatic_diagnosis_enabled": False,
            "collector_run_id": None,
            "incidents_processed": 0,
            "incidents_eligible": 0,
            "incidents_skipped": 0,
            "incidents_with_errors": 0,
            "total_review_packets_written": 0,
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
            "eligibility_schema_version": 2,
            "incident_access_mode": access_mode,
            "explicit_canonical_id_count": (
                len(explicit_ids) if explicit_ids else 0
            ),
            "promotion_propagated_to_diagnosis": bool(explicit_ids),
        }

    # Log start of automatic diagnosis phase. When canonical IDs are
    # supplied, we record the count and provenance so operators can see
    # whether the dispatcher is consuming canonical IDs or scanning the
    # store.
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Starting automatic diagnosis loop evidence collection",
            event="start",
            explicit_canonical_id_count=(
                len(explicit_ids) if explicit_ids else 0
            ),
            incident_access_mode=access_mode,
        )

    config = AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=10,
        max_passes_per_incident=1,
        max_checks_per_pass=5,
        write_stop_path_packets=True,
        write_ineligible_packets=False,
    )

    from ..collect.incident_diagnosis_auto_loop import run_automatic_diagnosis_loop_evidence_collection

    promotion_summary = (
        dict(promotion_result_summary) if promotion_result_summary else {}
    )

    # R7 (item 2): the explicit-ID vs. store-scan decision is now driven
    # by the orchestrator-provided selection mode (when supplied) and
    # falls back to canonical-IDs cardinality when the orchestrator did
    # not pass a value (legacy callers). The selected mode is recorded
    # in the structured event so operators can audit the decision.
    effective_selection_mode = incident_selection_mode
    if effective_selection_mode not in {
        "explicit_incident_ids",
        "store_scan",
    }:
        effective_selection_mode = (
            "explicit_incident_ids"
            if explicit_ids
            else "store_scan"
        )

    try:
        if effective_selection_mode == "explicit_incident_ids" and explicit_ids is not None:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_analysis_dir,
                config=config,
                incident_ids=explicit_ids,
                scheduler_run_id=scheduler_run_id,
            )
        else:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_analysis_dir,
                config=config,
                scheduler_run_id=scheduler_run_id,
            )

        projection = _projection_from_result(result)
        summary = {
            "automatic_diagnosis_enabled": True,
            "collector_run_id": result.run_id,
            "run_id": scheduler_run_id,
            "incidents_processed": result.incidents_processed,
            "incidents_eligible": result.incidents_eligible,
            "incidents_skipped": result.incidents_skipped,
            "incidents_ineligible": result.incidents_ineligible,
            "incidents_with_errors": result.incidents_with_errors,
            "total_review_packets_written": result.total_review_packets_written,
            # Canonical-incident-identity propagation metadata
            "incident_access_mode": access_mode,
            "explicit_canonical_id_count": (
                len(explicit_ids) if explicit_ids else 0
            ),
            "promotion_propagated_to_diagnosis": bool(explicit_ids),
            "selection_mode": effective_selection_mode,
            "backend_endpoint_identity": backend_endpoint_identity,
            "promotion_summary_propagated": promotion_summary,
            **projection,
        }

        # Log completion with full eligibility summary for operator diagnostics.
        # Operators already inspect this event; we include the reason maps
        # directly so they do not need to cross-reference a separate aggregate.
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis loop completed",
                event="complete",
                collector_run_id=result.run_id,
                run_id=scheduler_run_id,
                incidents_processed=result.incidents_processed,
                incidents_eligible=result.incidents_eligible,
                incidents_skipped=result.incidents_skipped,
                incidents_ineligible=result.incidents_ineligible,
                incidents_with_errors=result.incidents_with_errors,
                total_review_packets_written=result.total_review_packets_written,
                incident_access_mode=access_mode,
                explicit_canonical_id_count=(
                    len(explicit_ids) if explicit_ids else 0
                ),
                promotion_propagated_to_diagnosis=bool(explicit_ids),
                selection_mode=effective_selection_mode,
                **projection,
            )

        return summary

    except Exception as exc:
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "WARNING",
                "Automatic diagnosis loop failed with error",
                event="error",
                error=str(type(exc).__name__),
                explicit_canonical_id_count=(
                    len(explicit_ids) if explicit_ids else 0
                ),
            )

        return {
            "automatic_diagnosis_enabled": True,
            "collector_run_id": None,
            "incidents_processed": 0,
            "incidents_eligible": 0,
            "incidents_skipped": 0,
            "incidents_with_errors": 1,
            "total_review_packets_written": 0,
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {
                "eligibility_evaluation_failed": 1,
            },
            "eligibility_schema_version": 2,
            "incident_access_mode": access_mode,
            "explicit_canonical_id_count": (
                len(explicit_ids) if explicit_ids else 0
            ),
            "promotion_propagated_to_diagnosis": bool(explicit_ids),
            "selection_mode": effective_selection_mode,
            "backend_endpoint_identity": backend_endpoint_identity,
            "promotion_summary_propagated": promotion_summary,
        }

"""Automatic diagnosis loop evidence collection integration for health loop.

The public orchestration seam remains here: selection validation, policy
checks, collector invocation, and terminal exception semantics. Reporting
projections and structured event payload construction live in the sibling
``loop_automatic_diagnosis_reporting`` module and are imported as stable
private aliases for existing callers and tests.

The collector refuses to interpret an empty incident-ID sequence as a store
scan. The orchestrator must supply an explicit :class:`DiagnosisSelection`
variant, and promotion-derived run identities must match the scheduler run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from k8s_diag_agent.collect import diagnosis_selection as _diagnosis_selection
from k8s_diag_agent.collect import promotion_outcomes as _promotion_outcomes
from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisRunIdentityMismatchError,
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
)
from k8s_diag_agent.collect.diagnosis_selection import (
    selection_run_id as _selection_run_id,
)
from k8s_diag_agent.collect.diagnosis_selection import (
    store_scan_performed as _store_scan_performed,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    is_automatic_diagnosis_loop_enabled,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionOutcome,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
)

from . import loop_automatic_diagnosis_reporting as _reporting
from .loop_automatic_diagnosis_reporting import (
    build_completed_summary,
    build_disabled_summary,
    build_error_summary,
    build_no_trigger_summary,
    build_selection_unavailable_summary,
    emit_complete,
    emit_disabled,
    emit_error,
    emit_selection_unavailable,
    emit_start,
)
from .loop_automatic_diagnosis_reporting import (
    resolve_access_mode as _resolve_access_mode,
)
from .loop_automatic_diagnosis_reporting import (
    selection_projection as _selection_projection,
)

_selection_source = _diagnosis_selection.selection_source
_consistency_error_recorded = _promotion_outcomes.consistency_error_recorded
_blocked_reason = _reporting.blocked_reason
_legacy_selection_mode = _reporting._legacy_selection_mode
_projection_from_result = _reporting.projection_from_result

__all__ = [
    "build_diagnosis_selection",
    "run_automatic_diagnosis_loop",
]

# Reason map keys for scheduler completion tracking.
# These are referenced by the disposition verifier to ensure reason maps
# are included in the completed/disabled/selection-unavailable summaries.
SKIP_REASONS_KEY = "skip_reasons"
INELIGIBLE_REASONS_KEY = "ineligible_reasons"
ERROR_REASONS_KEY = "error_reasons"


def _coerce_canonical_ids(canonical_incident_ids: Any) -> list[str] | None:
    """Backward-compatible ID list coercion helper."""
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


class InvalidStoreScanReasonError(ValueError):
    """Raised when ``non_promotion_reason`` is not a bounded enum value."""


def _validate_diagnosis_selection_run_id(
    selection: DiagnosisSelection,
    scheduler_run_id: str | None,
) -> None:
    """Reject cross-run laundering at the dispatch seam (fail-closed)."""
    actual = _selection_run_id(selection)
    if actual is None:
        return
    expected = str(scheduler_run_id or "")
    # Allow legacy_run_id when scheduler has no run_id (backward compatibility
    # for tests and legacy callers that do not set scheduler_run_id).
    if scheduler_run_id is None and actual == "legacy_run":
        return
    if expected != actual:
        raise DiagnosisRunIdentityMismatchError(
            expected_run_id=expected,
            actual_run_id=actual,
        )


def build_diagnosis_selection(
    *,
    promotion_outcome: PromotionOutcome | None,
    run_id: str,
    non_promotion_policy_enabled: bool = False,
    non_promotion_reason: str | None = None,
    store_scan_policy: object | None = None,
) -> DiagnosisSelection:
    """Construct a typed :class:`DiagnosisSelection` for a run."""
    if promotion_outcome is not None:
        # Validate before branching so all three promotion variants are covered.
        expected_run_id = run_id
        actual_run_id = promotion_outcome.run_id
        if not expected_run_id or expected_run_id != actual_run_id:
            raise DiagnosisRunIdentityMismatchError(
                expected_run_id=expected_run_id,
                actual_run_id=actual_run_id,
            )
        if isinstance(promotion_outcome, PromotionCommitUnknown):
            return DiagnosisSelectionUnavailable(outcome=promotion_outcome)
        if isinstance(promotion_outcome, PromotionRejected):
            return DiagnosisSelectionUnavailable(outcome=promotion_outcome)
        if isinstance(promotion_outcome, PromotionSucceeded):
            return DiagnosisSelectionFromPromotion(
                promotion_run_id=promotion_outcome.run_id,
                incident_ids=tuple(promotion_outcome.diagnosis_incident_ids),
            )
        raise ValueError(
            "build_diagnosis_selection: promotion_outcome is not a "
            f"PromotionOutcome variant (got {type(promotion_outcome).__name__})"
        )

    if store_scan_policy is not None:
        from ..collect.store_scan_policy import StoreScanPolicy

        if store_scan_policy is StoreScanPolicy.DISABLED:
            raise ValueError(
                "build_diagnosis_selection: store_scan_policy=DISABLED "
                "without a promotion outcome is ambiguous; surface as "
                "a configuration error rather than fall through to a "
                "store scan"
            )
        if store_scan_policy is StoreScanPolicy.EXPLICIT_NON_PROMOTION:
            try:
                reason = NoPromotionSelectionReason(non_promotion_reason or "")
            except ValueError as exc:
                raise InvalidStoreScanReasonError(
                    "build_diagnosis_selection: store_scan_policy "
                    "requires a bounded non_promotion_reason; "
                    f"got {non_promotion_reason!r}"
                ) from exc
            return DiagnosisSelectionWithoutPromotion(reason=reason)

    if non_promotion_policy_enabled:
        try:
            reason = NoPromotionSelectionReason(non_promotion_reason or "")
        except ValueError as exc:
            raise InvalidStoreScanReasonError(
                "build_diagnosis_selection: non_promotion_policy_enabled "
                "requires a bounded non_promotion_reason; "
                f"got {non_promotion_reason!r}"
            ) from exc
        return DiagnosisSelectionWithoutPromotion(reason=reason)

    raise ValueError(
        "build_diagnosis_selection requires either a promotion outcome, "
        "an explicit non_promotion scan policy, or the legacy "
        "non_promotion_policy_enabled=True flag with a bounded reason"
    )


class AmbiguousDiagnosisSelectionError(ValueError):
    """Raised when the caller cannot supply an unambiguous selection."""

    def __init__(self, message: str, *, run_id: str) -> None:
        super().__init__(message)
        self.run_id = run_id


def _legacy_build_selection(
    *,
    canonical_incident_ids: Any,
    incident_selection_mode: str | None,
    scheduler_run_id: str | None,
) -> DiagnosisSelection:
    """Build a typed selection from legacy arguments without scan fallback."""
    legacy_run_id = str(scheduler_run_id or "legacy_run")
    if incident_selection_mode == "blocked":
        return DiagnosisSelectionUnavailable(
            outcome=PromotionRejected(
                run_id=legacy_run_id,
                reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                rejected_signal_ids=(),
            ),
        )
    if incident_selection_mode == "store_scan":
        return DiagnosisSelectionWithoutPromotion(
            reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
        )
    if canonical_incident_ids is not None:
        coerced = [str(value) for value in canonical_incident_ids if value]
        return DiagnosisSelectionFromPromotion(
            promotion_run_id=legacy_run_id,
            incident_ids=tuple(coerced),
        )
    raise AmbiguousDiagnosisSelectionError(
        "run_automatic_diagnosis_loop requires an explicit "
        "DiagnosisSelection or one of: canonical_incident_ids, "
        "incident_selection_mode in {'store_scan'} with explicit "
        "promotion policy, or a promotion_outcome. The legacy "
        "truthiness fallback is forbidden because it caused a "
        "production store-scan regression on duplicate alert signals.",
        run_id=legacy_run_id,
    )


def run_automatic_diagnosis_loop(
    *,
    external_analysis_dir: Path,
    log_event_fn: Any | None = None,
    scheduler_run_id: str | None = None,
    canonical_incident_ids: Any | None = None,
    promotion_result_summary: dict[str, Any] | None = None,
    backend_endpoint_identity: dict[str, Any] | None = None,
    incident_selection_mode: str | None = None,
    promotion_outcome: PromotionOutcome | None = None,
    diagnosis_selection: DiagnosisSelection | None = None,
    non_promotion_policy_enabled: bool = False,
    non_promotion_reason: str | None = None,
) -> dict[str, Any]:
    """Run automatic diagnosis loop evidence collection."""
    # Check enabled status early: when integration is disabled, return
    # the disabled summary immediately without requiring an authority.
    # This allows disabled-integration tests to pass without authority.
    enabled = is_automatic_diagnosis_loop_enabled()
    if not enabled:
        access_mode = _resolve_access_mode(
            backend_endpoint_identity=backend_endpoint_identity,
            promotion_result_summary=promotion_result_summary,
        )
        projection = _selection_projection(
            DiagnosisSelectionWithoutPromotion(
                reason=NoPromotionSelectionReason.EXPLICIT_NON_PROMOTION_MODE,
            ),
            access_mode=access_mode,
        )
        emit_disabled(log_event_fn, projection)
        return build_disabled_summary(projection)

    # Integration is enabled. Validate authority arguments.
    access_mode = _resolve_access_mode(
        backend_endpoint_identity=backend_endpoint_identity,
        promotion_result_summary=promotion_result_summary,
    )

    sources_supplied = sum(
        (
            diagnosis_selection is not None,
            promotion_outcome is not None,
            canonical_incident_ids is not None,
            incident_selection_mode is not None,
            non_promotion_policy_enabled,
        )
    )
    if sources_supplied > 1:
        raise AmbiguousDiagnosisSelectionError(
            "run_automatic_diagnosis_loop: only one authority source "
            "may be supplied. A directly-supplied DiagnosisSelection is "
            "the sole authority; a PromotionOutcome is consumed only "
            "via build_diagnosis_selection; legacy canonical_ids, "
            "incident_selection_mode, and the non_promotion_policy_enabled "
            "boolean are mutually exclusive.",
            run_id=str(scheduler_run_id or ""),
        )

    selection: DiagnosisSelection
    if diagnosis_selection is not None:
        selection = diagnosis_selection
    elif canonical_incident_ids is not None or incident_selection_mode is not None:
        # Legacy authority: canonical_incident_ids or incident_selection_mode.
        # Must be handled before build_diagnosis_selection to avoid
        # ambiguity error from the promotion-based selection builder.
        selection = _legacy_build_selection(
            canonical_incident_ids=canonical_incident_ids,
            incident_selection_mode=incident_selection_mode,
            scheduler_run_id=scheduler_run_id,
        )
    elif promotion_outcome is not None or non_promotion_policy_enabled:
        selection = build_diagnosis_selection(
            promotion_outcome=promotion_outcome,
            run_id=str(scheduler_run_id or ""),
            non_promotion_policy_enabled=non_promotion_policy_enabled,
            non_promotion_reason=non_promotion_reason,
        )
    else:
        # Integration enabled but no authority: this is the "no trigger" path.
        # Return an enabled summary with 0 incidents processed.
        projection = _selection_projection(
            DiagnosisSelectionWithoutPromotion(
                reason=NoPromotionSelectionReason.EXPLICIT_NON_PROMOTION_MODE,
            ),
            access_mode=access_mode,
        )
        emit_disabled(log_event_fn, projection)
        return build_no_trigger_summary(projection)

    _validate_diagnosis_selection_run_id(selection, scheduler_run_id)
    projection = _selection_projection(selection, access_mode=access_mode)
    selected_ids = (
        selection.incident_ids
        if isinstance(selection, DiagnosisSelectionFromPromotion)
        else tuple()
    )

    if isinstance(selection, DiagnosisSelectionUnavailable):
        emit_selection_unavailable(
            log_event_fn,
            projection=projection,
            access_mode=access_mode,
        )
        return build_selection_unavailable_summary(
            projection=projection,
            promotion_result_summary=promotion_result_summary,
            backend_endpoint_identity=backend_endpoint_identity,
            selection=selection,
        )

    emit_start(log_event_fn, projection)
    config = AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=10,
        max_passes_per_incident=1,
        max_checks_per_pass=5,
        write_stop_path_packets=True,
        write_ineligible_packets=False,
    )

    from ..collect.incident_diagnosis_auto_loop import (
        run_automatic_diagnosis_loop_evidence_collection,
    )

    promotion_summary = (
        dict(promotion_result_summary) if promotion_result_summary else {}
    )

    try:
        if _store_scan_performed(selection):
            assert isinstance(selection, DiagnosisSelectionWithoutPromotion)
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_analysis_dir,
                config=config,
                scheduler_run_id=scheduler_run_id,
            )
        else:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_analysis_dir,
                config=config,
                incident_ids=list(selected_ids),
                scheduler_run_id=scheduler_run_id,
            )

        summary, reason_projection = build_completed_summary(
            result=result,
            scheduler_run_id=scheduler_run_id,
            projection=projection,
            backend_endpoint_identity=backend_endpoint_identity,
            promotion_summary=promotion_summary,
        )
        emit_complete(
            log_event_fn,
            result=result,
            scheduler_run_id=scheduler_run_id,
            projection=projection,
            reason_projection=reason_projection,
        )
        return summary

    except Exception as exc:
        emit_error(log_event_fn, projection=projection, exc=exc)
        return build_error_summary(
            projection=projection,
            backend_endpoint_identity=backend_endpoint_identity,
            promotion_summary=promotion_summary,
        )

"""Legacy compatibility projection for the disposition ADT.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

This module hosts the *one-way* and *reverse* projections between the
closed-typed disposition union (``incident_diagnosis_disposition``) and
the legacy ``AutoLoopIncidentResult`` shape (still the source of truth until the typed-outcome ACT migrates the production hot path).

* ``legacy_result_from_disposition``: canonical projection from a typed
  disposition to the legacy result dataclass (used by external/API
  compatibility).
* ``disposition_from_legacy_result``: reverse projection used during
  migration; rejects impossible combinations and maps unknown legacy
  strings to ``UNKNOWN_LEGACY_REASON``.

This module is leaf-safe. To avoid a circular import with the main
disposition module (which re-exports these names), all references to
disposition types are lazy: they happen at call time via direct module
attribute access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

if TYPE_CHECKING:
    from .incident_diagnosis_auto_loop_config import DiagnosisBudgetDiagnostic
    from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
    from .incident_diagnosis_disposition import (
        DiagnosisEvaluationFailureReason,
        DiagnosisSkipReason,
        IncidentDiagnosisDisposition,
    )


# The closed reason vocabulary enums are imported via lazy attribute access
# on the disposition module below to avoid a circular import. The compat
# module is intended to be the *only* importer of legacy types; the main
# disposition module re-exports the public names from this module.

_LEGACY_UNKNOWN_REASONS: frozenset[str] = frozenset({"unknown", "unknown_skip"})


def legacy_result_from_disposition(
    *,
    incident_id: str,
    disposition: IncidentDiagnosisDisposition,
) -> AutoLoopIncidentResult:
    """Project a typed disposition back to the legacy ``AutoLoopIncidentResult``.

    This is an explicit, one-way projection used for external/API
    compatibility only. The internal eligibility state machine no longer
    uses booleans; this function translates a closed disposition into the
    loose-typed shape that legacy consumers still expect.
    """
    # Lazy import to break the circular import: the main disposition
    # module re-exports ``legacy_result_from_disposition`` from us, so we
    # cannot import AutoLoopIncidentResult (or the disposition types) at
    # module load time.
    from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
    from .incident_diagnosis_disposition import (
        AutomaticDiagnosisEvaluationFailed,
        EligibleForAutomaticDiagnosis,
        IneligibleForAutomaticDiagnosis,
        SkippedFromAutomaticDiagnosis,
    )

    match disposition:
        case EligibleForAutomaticDiagnosis(
            eligibility_reason=eligibility_reason, budget_diagnostics=budget_diagnostics
        ):
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=True,
                eligibility_reason=eligibility_reason,
                budget_diagnostics=budget_diagnostics,
            )
        case SkippedFromAutomaticDiagnosis(
            reason=reason, detail=detail, budget_diagnostics=budget_diagnostics
        ):
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason=reason.value,
                skipped=True,
                skip_reason=detail or reason.value,
                budget_diagnostics=budget_diagnostics,
            )
        case IneligibleForAutomaticDiagnosis(reason=reason, detail=detail):
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason=reason.value,
                skipped=False,
                skip_reason=detail or reason.value,
            )
        case AutomaticDiagnosisEvaluationFailed(reason=reason, detail=detail):
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason=reason.value,
                error=detail or reason.value,
            )
        case _ as unreachable:  # pragma: no cover - exhaustiveness
            assert_never(unreachable)


def disposition_from_legacy_result(
    result: AutoLoopIncidentResult,
) -> IncidentDiagnosisDisposition:
    """Reverse legacy projection.

    The legacy result may carry contradictory fields. This function:

    * rejects impossible combinations by raising ``ValueError``,
    * recognises terminal/inactive statuses and routes them to
      :class:`IneligibleForAutomaticDiagnosis` rather than
      :class:`SkippedFromAutomaticDiagnosis`,
    * maps unknown legacy strings to ``UNKNOWN_LEGACY_REASON``.
    """
    # Lazy imports to avoid the circular import with the main disposition
    # module which re-exports ``disposition_from_legacy_result`` from us.
    from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
    from .incident_diagnosis_disposition import (
        EligibleForAutomaticDiagnosis,
    )

    if not isinstance(result, AutoLoopIncidentResult):
        raise TypeError(f"Expected AutoLoopIncidentResult, got {type(result).__name__}")

    eligible = bool(result.eligible)
    skipped = bool(result.skipped)
    error_present = result.error is not None
    eligibility_reason = result.eligibility_reason or ""
    skip_reason = result.skip_reason or ""

    if eligible and skipped:
        raise ValueError("Legacy result has both eligible=True and skipped=True")
    if skipped and error_present:
        raise ValueError("Legacy result has both skipped=True and an error message")
    if eligible and error_present:
        # Eligible + downstream error: keep as eligible with detail; do NOT
        # retroactively classify as an eligibility evaluation failure.
        return EligibleForAutomaticDiagnosis(
            eligibility_reason=eligibility_reason or "active_incident_with_suggested_checks",
            budget_diagnostics=result.budget_diagnostics,
        )
    if not eligible and not skipped and not error_present:
        raise ValueError(
            "Legacy result is neither eligible, skipped, nor errored; cannot project"
        )

    if eligible:
        return EligibleForAutomaticDiagnosis(
            eligibility_reason=eligibility_reason or "active_incident_with_suggested_checks",
            budget_diagnostics=result.budget_diagnostics,
        )

    # skipped=True (or skipped-eligible-False combination). Determine the
    # correct *kind* by inspecting the legacy reason strings because the
    # legacy ``skipped=True`` boolean is overloaded: both ``Skipped`` and
    # ``Ineligible`` were encoded as ``skipped=True``.
    return _classify_non_eligible(
        eligibility_reason=eligibility_reason,
        skip_reason=skip_reason,
        detail=skip_reason or None,
        budget_diagnostics=result.budget_diagnostics,
        error_message=result.error,
    )


def _classify_non_eligible(
    *,
    eligibility_reason: str,
    skip_reason: str,
    detail: str | None,
    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...],
    error_message: str | None,
) -> IncidentDiagnosisDisposition:
    """Map a non-eligible legacy result to a typed disposition.

    The legacy pre-ADT code wrote every non-eligible outcome with
    ``skipped=True`` (or with ``error`` set). The closed reason
    vocabulary distinguishes Skipped (non-failure), Ineligible
    (terminal/unsupported) and EvaluationFailed (fetch/payload/eval).
    """
    from .incident_diagnosis_disposition import (
        AutomaticDiagnosisEvaluationFailed,
        DiagnosisIneligibleReason,
        DiagnosisSkipReason,
        IneligibleForAutomaticDiagnosis,
        SkippedFromAutomaticDiagnosis,
    )

    # Error path takes priority: if any error is set, classify as failure.
    if error_message is not None:
        return AutomaticDiagnosisEvaluationFailed(
            reason=_map_legacy_error_reason(eligibility_reason),
            detail=error_message,
        )

    # Try the eligibility_reason first (most specific source of truth).
    if eligibility_reason.startswith("terminal_status_"):
        return IneligibleForAutomaticDiagnosis(
            reason=DiagnosisIneligibleReason.TERMINAL_STATUS,
            detail=detail,
        )
    if eligibility_reason.startswith("inactive_status_"):
        return IneligibleForAutomaticDiagnosis(
            reason=DiagnosisIneligibleReason.UNSUPPORTED_STATUS,
            detail=detail,
        )

    # The ``_process_incident`` wrapper writes ``skip_reason =
    # f"not_eligible: {eligibility.reason}"`` for any non-eligible
    # ``EligibilityResult``. Strip that prefix to recover the underlying
    # reason and re-classify.
    raw = skip_reason or eligibility_reason
    if raw.startswith("not_eligible: "):
        underlying = raw[len("not_eligible: ") :]
        if underlying.startswith("terminal_status_"):
            return IneligibleForAutomaticDiagnosis(
                reason=DiagnosisIneligibleReason.TERMINAL_STATUS,
                detail=detail,
            )
        if underlying.startswith("inactive_status_"):
            return IneligibleForAutomaticDiagnosis(
                reason=DiagnosisIneligibleReason.UNSUPPORTED_STATUS,
                detail=detail,
            )
        if underlying.startswith("not_found"):
            return SkippedFromAutomaticDiagnosis(
                reason=DiagnosisSkipReason.INCIDENT_NOT_FOUND,
                detail=detail,
                budget_diagnostics=budget_diagnostics,
            )

    # Fall back to the skip reason classifier.
    return SkippedFromAutomaticDiagnosis(
        reason=_map_legacy_skip_reason(raw),
        detail=detail,
        budget_diagnostics=budget_diagnostics,
    )


def _map_legacy_skip_reason(raw: str) -> DiagnosisSkipReason:  # noqa: F821
    from .incident_diagnosis_disposition import DiagnosisSkipReason

    raw_lower = (raw or "").lower()
    if "budget" in raw_lower:
        return DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED
    if "not_found" in raw_lower or "not found" in raw_lower:
        return DiagnosisSkipReason.INCIDENT_NOT_FOUND
    if "disabled" in raw_lower:
        return DiagnosisSkipReason.AUTOMATIC_DIAGNOSIS_DISABLED
    if "no_incidents_processed" in raw_lower or "no incidents" in raw_lower:
        return DiagnosisSkipReason.NO_INCIDENTS_PROCESSED
    if "cooldown" in raw_lower:
        return DiagnosisSkipReason.INCIDENT_COOLDOWN_ACTIVE
    if raw_lower in _LEGACY_UNKNOWN_REASONS:
        return DiagnosisSkipReason.UNKNOWN_LEGACY_REASON
    # Try direct enum match first
    for member in DiagnosisSkipReason:
        if member.value == raw_lower:
            return member
    return DiagnosisSkipReason.UNKNOWN_LEGACY_REASON


def _map_legacy_error_reason(raw: str) -> DiagnosisEvaluationFailureReason:  # noqa: F821
    """Map a legacy error string to a typed :class:`DiagnosisEvaluationFailureReason`.

    Substring matching for ``backend_incident_*`` codes is intentionally
    NOT used: the production evidence processor writes the canonical
    ``"backend_incident_<code>"`` string via the typed mapping in
    :func:`incident_diagnosis_disposition.diagnosis_failure_reason_for_backend_lookup`,
    so substring matching would misclassify any free-form detail that
    happens to embed a code substring (e.g. ``"prefix_backend_incident_invalid_json_suffix"``).
    Only exact value matches against :class:`DiagnosisEvaluationFailureReason`
    members are accepted for backward compatibility; a substring match
    falls through to the heuristic branches below.
    """
    from .incident_diagnosis_disposition import DiagnosisEvaluationFailureReason

    raw_lower = (raw or "").lower()

    # Exact enum-value match is the ONLY accepted legacy path for backend
    # incident-detail lookup codes. Anything else falls through to the
    # heuristic branches below (legacy ``fetch_failed`` etc.).
    if raw_lower.startswith("backend_incident_"):
        try:
            return DiagnosisEvaluationFailureReason(raw_lower)
        except ValueError:
            pass

    if "fetch" in raw_lower:
        return DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED
    if "unsafe_run" in raw_lower or "unsafe run" in raw_lower:
        return DiagnosisEvaluationFailureReason.UNSAFE_RUN_ID
    if "case_file" in raw_lower or "case file" in raw_lower:
        return DiagnosisEvaluationFailureReason.CASE_FILE_BUILD_FAILED
    if "invalid" in raw_lower or "payload" in raw_lower:
        return DiagnosisEvaluationFailureReason.INVALID_INCIDENT_PAYLOAD
    # Final exact-enum-match fallback for any remaining legacy strings
    # (e.g. ``"unsafe_run_id"``, ``"backend_fetch_failed"``) that the
    # heuristic branches missed but that still match an enum value.
    for member in DiagnosisEvaluationFailureReason:
        if member.value == raw_lower:
            return member
    return DiagnosisEvaluationFailureReason.ELIGIBILITY_EVALUATION_FAILED


__all__ = [
    "legacy_result_from_disposition",
    "disposition_from_legacy_result",
]

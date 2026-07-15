"""Automatic diagnosis loop evidence collection integration for health loop.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 contract:

The collector takes a :class:`DiagnosisSelection` variant from the
orchestrator and dispatches through a single, exhaustively-matched
match. The previous contract accepted an optional sequence of canonical
IDs and an ``incident_selection_mode`` string, and silently fell back
to a store scan when the IDs were empty.

That truthiness fallback caused the production regression where a
33-identity-duplicate current run reported zero explicit canonical
IDs and the collector picked an unrelated incident from the global
store. The collector now refuses to interpret an empty sequence as a
fallback signal: the orchestrator must supply an explicit
:class:`DiagnosisSelection` variant that names the source.

Round-10 invariants (R10-1A and R10-1B) further require:

1. Every promotion-derived ``run_id`` carried by the selection
   MUST equal ``scheduler_run_id``. Mismatch is a hard error --
   ``cross-run laundry`` is rejected at the dispatch seam.

2. The validator is **fail-closed**: when ``scheduler_run_id`` is
   absent (``None`` or empty) AND the selection carries a
   promotion-derived ``run_id``, the seam raises. A run that
   cannot produce a comparison target is a configuration error,
   not a no-op.

3. ``build_diagnosis_selection()`` validates ``promotion_outcome.run_id``
   BEFORE branching on the outcome variant, so ``PromotionRejected``
   and ``PromotionCommitUnknown`` are not bypassable through the
   builder. The builder also rejects when ``run_id`` is empty.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    selection_source as _selection_source,
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
from k8s_diag_agent.collect.promotion_outcomes import (
    consistency_error_recorded as _consistency_error_recorded,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "build_diagnosis_selection",
    "run_automatic_diagnosis_loop",
]


def _projection_from_result(result: Any) -> dict[str, Any]:
    """Project reason maps from a typed ``disposition_summary`` (or fall back)."""
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


def _coerce_canonical_ids(canonical_incident_ids: Any) -> list[str] | None:
    """Backward-compatible ID list coercion helper.

    The new selection-algebra path does not consume this directly; the
    orchestrator now supplies a :class:`DiagnosisSelection` variant.
    This helper is preserved because existing test fixtures import it.
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


class InvalidStoreScanReasonError(ValueError):
    """Raised when ``non_promotion_reason`` is not a bounded enum value.

    The previous implementation silently defaulted to
    :class:`NoPromotionSelectionReason.SCHEDULED_SCAN_RUN` whenever
    the supplied reason was not a bounded enum value, which made
    fail-open policy decisions possible. We now raise so the
    orchestrator surfaces the configuration error instead of
    silently enabling a scan.
    """


def _validate_diagnosis_selection_run_id(
    selection: DiagnosisSelection,
    scheduler_run_id: str | None,
) -> None:
    """Reject cross-run laundering at the dispatch seam (fail-closed).

    Round-10 invariant (R10-1B): the validator is fail-closed. Every
    promotion-derived ``run_id`` carried by the selection MUST equal
    ``scheduler_run_id``. When ``scheduler_run_id`` is ``None`` /
    empty AND the selection carries a promotion-derived ``run_id``,
    the seam raises -- the caller cannot prove equality, so the
    cross-run laundry path is forbidden rather than silently
    accepted.

    :class:`DiagnosisSelectionWithoutPromotion` carries no promotion-
    derived ``run_id`` and is allowed through the validator
    regardless of ``scheduler_run_id`` -- it represents a
    non-promotion run, not a missing comparison target.
    """
    actual = _selection_run_id(selection)
    if actual is None:
        return
    expected = str(scheduler_run_id or "")
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
    """Construct the typed :class:`DiagnosisSelection` for a run.

    Round-10 (R10-1A, R10-1B): every promotion-derived ``run_id``
    carried by ``promotion_outcome`` MUST equal the caller-supplied
    ``run_id``. We validate BEFORE branching on the variant type so
    the rule applies uniformly to :class:`PromotionSucceeded`,
    :class:`PromotionRejected`, and :class:`PromotionCommitUnknown`.
    We also reject when ``run_id`` is empty -- a promotion outcome
    cannot be matched against an unknown target, so the builder
    raises rather than synthesizing an identity.

    Resolution order:

    1. ``promotion_outcome is not None`` ->
       :class:`DiagnosisSelectionFromPromotion` /
       :class:`DiagnosisSelectionUnavailable` keyed by the outcome
       variant. The validation chokepoint runs first.
    2. ``store_scan_policy is StoreScanPolicy.EXPLICIT_NON_PROMOTION``
       -> :class:`DiagnosisSelectionWithoutPromotion`.
    3. Legacy ``non_promotion_policy_enabled=True`` accepts only
       bounded :class:`NoPromotionSelectionReason` values; unknown
       reasons raise :class:`InvalidStoreScanReasonError`.
    4. Otherwise raise so the caller surfaces a configuration error
       instead of falling back to scan.
    """
    if promotion_outcome is not None:
        # Validate BEFORE branching on the outcome variant. Every
        # promotion-derived ``run_id`` (Succeeded, Rejected,
        # CommitUnknown) must equal the caller's expected
        # ``run_id``. Empty ``run_id`` is also a configuration
        # error: the caller cannot prove equality when the
        # expected target is unknown.
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
        # A non-conforming typed outcome cannot be projected.
        raise ValueError(
            "build_diagnosis_selection: promotion_outcome is not a "
            f"PromotionOutcome variant (got {type(promotion_outcome).__name__})"
        )

    # Typed policy is the preferred authority.
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
                reason = NoPromotionSelectionReason(
                    non_promotion_reason or ""
                )
            except ValueError as exc:
                raise InvalidStoreScanReasonError(
                    "build_diagnosis_selection: store_scan_policy "
                    "requires a bounded non_promotion_reason; "
                    f"got {non_promotion_reason!r}"
                ) from exc
            return DiagnosisSelectionWithoutPromotion(reason=reason)

    if non_promotion_policy_enabled:
        # Legacy compatibility: the boolean was previously the
        # authority. Now we accept only bounded enum values; an
        # unknown reason raises rather than defaulting to
        # SCHEDULED_SCAN_RUN.
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


def _legacy_selection_mode(selection: DiagnosisSelection) -> str:
    """Map a :class:`DiagnosisSelection` to the legacy string mode."""
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        if selection.incident_ids:
            return "explicit_incident_ids"
        return "current_run_empty"
    if isinstance(selection, DiagnosisSelectionUnavailable):
        carried = selection.outcome
        if isinstance(carried, PromotionCommitUnknown):
            return "commit_unknown"
        return "blocked"
    return "store_scan"


def _selection_projection(
    selection: DiagnosisSelection,
    *,
    access_mode: str,
) -> dict[str, Any]:
    """Compute the typed projection shared by every dispatch path."""
    explicit_count = 0
    selected_incident_count = 0
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        explicit_count = len(selection.incident_ids)
        selected_incident_count = len(selection.incident_ids)
    reconciliation_required = (
        isinstance(selection, DiagnosisSelectionUnavailable)
        and isinstance(selection.outcome, PromotionCommitUnknown)
    )
    # Authoritative zero-work or unavailable selections MUST NOT
    # claim propagation. Only an explicit
    # ``DiagnosisSelectionFromPromotion`` with at least one ID
    # counts as propagation; empty tuples are explicit zero-work.
    propagated = (
        isinstance(selection, DiagnosisSelectionFromPromotion)
        and bool(selection.incident_ids)
    )
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        consistency_error = False
    elif isinstance(selection, DiagnosisSelectionUnavailable):
        consistency_error = _consistency_error_recorded(selection.outcome)
    else:
        consistency_error = False
    return {
        "selection_source": _selection_source(selection).value,
        "selection_mode": _legacy_selection_mode(selection),
        "explicit_canonical_id_count": explicit_count,
        "selected_incident_count": selected_incident_count,
        "store_scan_performed": _store_scan_performed(selection),
        "reconciliation_required": reconciliation_required,
        "promotion_propagated_to_diagnosis": propagated,
        "promotion_consistency_error_recorded": consistency_error,
        "incident_access_mode": access_mode,
    }


def _resolve_access_mode(
    *,
    backend_endpoint_identity: dict[str, Any] | None,
    promotion_result_summary: dict[str, Any] | None,
) -> str:
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
    return access_mode


def _blocked_reason(selection: DiagnosisSelection) -> str | None:
    if not isinstance(selection, DiagnosisSelectionUnavailable):
        return None
    carried = selection.outcome
    if isinstance(carried, PromotionCommitUnknown):
        return "promotion_commit_unknown"
    if isinstance(carried, PromotionRejected):
        return "promotion_rejected"
    return "promotion_unavailable"


class AmbiguousDiagnosisSelectionError(ValueError):
    """Raised when the caller cannot supply an unambiguous :class:`DiagnosisSelection`.

    The legacy no-IDs / no-mode path used to silently fall back to a
    store scan, which is exactly the production regression this ACT
    closed. The error forces the orchestrator to surface a
    configuration error instead of an unexplained incident pivot.
    """

    def __init__(
        self,
        message: str,
        *,
        run_id: str,
    ) -> None:
        super().__init__(message)
        self.run_id = run_id


def _legacy_build_selection(
    *,
    canonical_incident_ids: Any,
    incident_selection_mode: str | None,
    scheduler_run_id: str | None,
) -> DiagnosisSelection:
    """Build a :class:`DiagnosisSelection` from the legacy arguments.

    The previous truthiness fallback is replaced with explicit variants.
    Legacy callers without an explicit selection variant raise so the
    configuration error surfaces instead of silently store-scanning
    (the 33-identity-duplicate regression shape).

    The :class:`DiagnosisSelectionFromPromotion` ``promotion_run_id``
    field carries the legacy run identity so the dispatch seam
    validator can compare it against ``scheduler_run_id``. When
    ``scheduler_run_id`` is ``None`` the legacy synthesises a
    sentinel ``"legacy_run"`` so the validator has a comparison
    target; the orchestrator MUST supply a real ``scheduler_run_id``
    in production for the identity check to be meaningful.
    """
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
    # No legacy IDs and no mode: this used to silently select
    # DiagnosisSelectionWithoutPromotion, which permitted a global
    # store scan. We now refuse the call so the orchestrator surfaces
    # a configuration error instead of an unobserved incident pivot.
    raise AmbiguousDiagnosisSelectionError(
        "run_automatic_diagnosis_loop requires an explicit "
        "DiagnosisSelection or one of: canonical_incident_ids, "
        "incident_selection_mode in {'store_scan'} with explicit "
        "promotion policy, or a promotion_outcome. The legacy "
        "truthiness fallback is forbidden because it caused a "
        "production store-scan regression on duplicate alert "
        "signals.",
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
    """Run automatic diagnosis loop evidence collection.

    Dispatch decision is sourced from an explicit
    :class:`DiagnosisSelection` variant. The legacy
    ``incident_selection_mode`` / ``canonical_incident_ids`` path is
    retained for backward compatibility but raises when it would have
    triggered a truthiness-based store scan fallback.

    P0 invariant (round 10): the dispatch seam runs
    :func:`_validate_diagnosis_selection_run_id` BEFORE telemetry,
    gate evaluation, or collector dispatch. Mismatched or missing
    ``scheduler_run_id`` raises
    :class:`DiagnosisRunIdentityMismatchError` so cross-run laundry
    cannot silently slip past.
    """
    access_mode = _resolve_access_mode(
        backend_endpoint_identity=backend_endpoint_identity,
        promotion_result_summary=promotion_result_summary,
    )

    # P0: reject contradictory selection inputs. The typed
    # :class:`DiagnosisSelection` is the sole authority. A
    # :class:`PromotionOutcome` is an input to ``build_diagnosis_selection``
    # and may NOT outrank a directly-supplied selection. A
    # ``promotion_outcome=PromotionCommitUnknown`` paired with a
    # ``diagnosis_selection=DiagnosisSelectionFromPromotion`` would
    # otherwise silently bypass commit-uncertainty blocking.
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
    elif promotion_outcome is not None or non_promotion_policy_enabled:
        selection = build_diagnosis_selection(
            promotion_outcome=promotion_outcome,
            run_id=str(scheduler_run_id or ""),
            non_promotion_policy_enabled=non_promotion_policy_enabled,
            non_promotion_reason=non_promotion_reason,
        )
    else:
        selection = _legacy_build_selection(
            canonical_incident_ids=canonical_incident_ids,
            incident_selection_mode=incident_selection_mode,
            scheduler_run_id=scheduler_run_id,
        )

    # P0 cross-run-identity guard (round 10). Enforced at the dispatch
    # seam so ALL three sources of selection (direct, build, legacy)
    # are checked uniformly before telemetry, gate evaluation, or
    # collector dispatch. ``build_diagnosis_selection`` already
    # validates its own ``promotion_outcome.run_id`` invariant; this
    # is the redundant check that catches direct
    # ``diagnosis_selection=...`` inputs and the legacy path's implicit
    # ``promotion_run_id`` materialisation. The validator is
    # fail-closed: a missing ``scheduler_run_id`` for a
    # promotion-derived selection is rejected.
    _validate_diagnosis_selection_run_id(selection, scheduler_run_id)

    projection = _selection_projection(selection, access_mode=access_mode)
    selected_ids = (
        selection.incident_ids
        if isinstance(selection, DiagnosisSelectionFromPromotion)
        else tuple()
    )

    if isinstance(selection, DiagnosisSelectionUnavailable):
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis selection unavailable",
                event="automatic_diagnosis_selection_unavailable",
                selection_source=projection["selection_source"],
                selection_mode=projection["selection_mode"],
                reconciliation_required=projection["reconciliation_required"],
                promotion_consistency_error_recorded=projection[
                    "promotion_consistency_error_recorded"
                ],
                incident_access_mode=access_mode,
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
            **projection,
            "promotion_summary_propagated": (
                dict(promotion_result_summary) if promotion_result_summary else {}
            ),
            "backend_endpoint_identity": backend_endpoint_identity,
            "blocked_reason": _blocked_reason(selection),
        }

    enabled = is_automatic_diagnosis_loop_enabled()

    if not enabled:
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis loop is disabled",
                event="disabled",
                **projection,
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
            **projection,
        }

    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Starting automatic diagnosis loop evidence collection",
            event="start",
            **projection,
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

        reason_projection = _projection_from_result(result)
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
            **projection,
            "backend_endpoint_identity": backend_endpoint_identity,
            "promotion_summary_propagated": promotion_summary,
            **reason_projection,
        }

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
                **projection,
                **reason_projection,
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
                **projection,
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
            **projection,
            "backend_endpoint_identity": backend_endpoint_identity,
            "promotion_summary_propagated": promotion_summary,
        }

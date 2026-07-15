"""Alert signal ingestion for Alertmanager snapshot collection.

This module handles the conversion of Alertmanager snapshots into AlertSignal
domain objects and their promotion to incidents.

This module is intentionally isolated from collection logic to keep the
ingestion path testable independently.

R1 hardening:

* The promotion dispatcher returns typed ``PromotionRecord`` values via
  ``promote_alert_signals_for_accumulator``. We translate those records
  directly into ``RunPromotionAccumulator.add_record`` calls so we never
  smuggle ``IncidentPromotionResult`` instances through a heterogeneous
  ``dict``.
* The accumulated records are observable to the rest of the run via
  the same accumulator instance, replacing the legacy
  ``directories["__last_promotion_result__"]`` smuggling.

Promotion routing:
- K9B_INCIDENT_PROMOTION_MODE=local: Direct store promotion (memory/file backends)
- K9B_INCIDENT_PROMOTION_MODE=backend-api: POST to backend internal API (sqlite backend)
- K9B_INCIDENT_PROMOTION_MODE=auto: Automatically selects based on role/backend

Hard constraints:
- NO scheduler direct SQLite writes
- NO remediation actions
- NO LLM calls from the promotion transport layer
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..collect.current_run_promotion_workset import (
        CurrentRunPromotionWorkset,
    )
    from ..collect.incident_promotion_accumulator import RunPromotionAccumulator
    from ..collect.incident_store import IncidentStore
    from ..collect.promotion_outcomes import PromotionOutcome
    from ..external_analysis.alertmanager_discovery import AlertmanagerSource
    from ..external_analysis.alertmanager_snapshot import AlertmanagerSnapshot


def _calculate_identity_collapse_count(
    *,
    raw_reference_count: int,
    unique_workset_signal_count: int,
) -> int:
    """Compute the current-batch identity-collapse count.

    ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 contract:

    The collapse count equals ``raw_reference_count -
    unique_workset_signal_count``. A violation of the cardinality
    invariant (``unique_workset_signal_count > raw_reference_count``)
    indicates a contract breach in the producer -- not a benign
    data observation -- and is raised as
    :class:`CurrentRunWorksetCardinalityError` rather than being
    silently clamped to zero. Clamping via ``max(0, ...)`` would
    hide a future regression in the factory contract.

    The helper is intentionally exposed at module scope and
    imported nowhere else -- it exists so a regression test can
    invoke the *actual* production arithmetic, not a manual raise
    of the exception, proving the metric site would fail closed
    under any contract regression that decoupled the metric from
    the factory invariant.
    """
    from ..collect.current_run_promotion_workset import (
        CurrentRunWorksetCardinalityError,
    )

    if unique_workset_signal_count > raw_reference_count:
        raise CurrentRunWorksetCardinalityError(
            raw=raw_reference_count,
            unique=unique_workset_signal_count,
        )
    return raw_reference_count - unique_workset_signal_count


def _build_scoped_request_payload(
    *,
    run_id: str,
    source_identity: str,
    signal_ids: tuple[str, ...],
) -> dict[str, object]:
    """Build the deterministic scoped-request payload used for fingerprinting.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 contract:

    * The payload is the exact logical request that was dispatched to
      the promotion backend (``runId`` / ``sourceIdentity`` /
      ``signalIds``).
    * ``signal_ids`` is sourced from ``current_run_workset.signal_ids``
      so the fingerprint is computed against the authoritative
      collapsed membership rather than the raw observation list.
    * The key order is deterministic (insertion order); the fingerprint
      helper sorts on JSON serialization so this is a defensive
      redundancy.

    Returns a dict suitable for passing to
    :func:`classify_promotion_dispatch_result` as
    ``requested_signal_payload``.
    """
    return {
        "runId": run_id,
        "sourceIdentity": source_identity,
        "signalIds": list(signal_ids),
    }


@dataclass(frozen=True, slots=True)
class AlertSignalPromotionDispatchResult:
    """Immutable result returned by :func:`_ingest_alert_signals`.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 invariant:
    every successful ingest of a scoped promotion attempt MUST
    surface its classified typed outcome through this envelope even
    when the caller does not supply a run-scoped accumulator. The
    production flow therefore returns ``(workset, outcome)`` so the
    typed outcome is never lost.

    The ``workset`` field is the authoritative current-run promotion
    workset that drove the dispatch request. The ``outcome`` field
    is the typed :class:`PromotionOutcome` produced by
    :func:`classify_promotion_dispatch_result` -- ``None`` if no
    dispatch was attempted (empty snapshot).
    """

    workset: CurrentRunPromotionWorkset | None
    outcome: PromotionOutcome | None


def _ingest_alert_signals(
    snapshot: AlertmanagerSnapshot,
    selected_source: AlertmanagerSource,
    snapshot_path: Path | None,
    directories: dict[str, Path],
    incident_store: IncidentStore | None,
    log_event: Callable[..., None],
    run_id: str,
    run_label: str,
    effective_cluster_context: str | None,
    promotion_accumulator: RunPromotionAccumulator | None = None,
) -> AlertSignalPromotionDispatchResult:
    """Ingest Alertmanager alerts as AlertSignal artifacts and promote to incidents.

    This function:
    1. Converts NormalizedAlert objects to AlertSignal domain model
    2. Persists alert signal artifacts for idempotency
    3. Promotes firing alerts into IncidentStore when available

    R1 contract:

    * Pass ``promotion_accumulator`` (typed run-scoped handoff) so the
      canonical incident IDs propagate to the diagnosis dispatcher.
    * Translates the dispatcher's typed ``PromotionRecord`` values
      directly into ``RunPromotionAccumulator.add_record`` calls.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 contract:

    * The real scoped dispatcher result (or typed :class:`Exception`)
      is captured at the dispatch boundary.
    * :func:`classify_promotion_dispatch_result` is invoked exactly
      once per attempted promotion with the exact
      ``current_run_workset.signal_ids`` and the deterministic
      request payload. The authoritative ``batch.promotion_records``
      are passed in so the typed outcome retains every per-candidate
      record rather than just the bare result.
    * The resulting typed :class:`PromotionOutcome` is recorded on the
      accumulator via :meth:`RunPromotionAccumulator.record_promotion_outcome`
      when the accumulator is provided.
    * The function returns an
      :class:`AlertSignalPromotionDispatchResult` so the typed
      outcome is NEVER lost when the caller does not supply an
      accumulator -- the return value carries the classified
      authority result for callers that need it.
    * Process-termination exceptions (``KeyboardInterrupt``,
      ``SystemExit``, ``GeneratorExit``) propagate BEFORE any
      classifier side effect (reconciliation-token construction,
      fingerprinting, logging, normalization).
    * Telemetry projection fields
      (``promotion_outcome``, ``promotion_outcome_reason``,
      ``diagnosis_handoff_available``,
      ``diagnosis_handoff_incident_count``,
      ``diagnosis_invoked``, ``requested_signal_count``, ...) are
      derived from the typed outcome and emitted alongside the
      existing success / failure log line.

    Args:
        snapshot: The Alertmanager snapshot with normalized alerts
        selected_source: The selected Alertmanager source
        snapshot_path: Path to the snapshot artifact for linking
        directories: Output directories dict
        incident_store: Optional IncidentStore for promotion
        log_event: Logging callback
        run_id: Run identifier
        run_label: Run label
        effective_cluster_context: Cluster context for logging
        promotion_accumulator: Optional typed run-scoped accumulator
            that captures canonical incident IDs for the diagnosis
            dispatcher. When ``None``, the scheduler still promotes
            but the canonical incident IDs are NOT propagated to
            automatic diagnosis; the typed outcome is returned
            via :class:`AlertSignalPromotionDispatchResult` so the
            caller can record it elsewhere.

    Returns:
        An :class:`AlertSignalPromotionDispatchResult` carrying the
        workset and the typed outcome (or ``None`` when no
        promotion was attempted).
    """
    from ..incident_alert_signal_snapshot_adapter import (
        adapt_snapshot_to_alert_signals,
        persist_alert_signals,
    )

    # Get canonical source instance ID (not alias URL)
    source_instance = selected_source.source_id

    # Parse received_at from snapshot
    received_at: dt | None = None
    if snapshot.captured_at:
        try:
            captured = snapshot.captured_at
            if captured.endswith("Z"):
                captured = f"{captured[:-1]}+00:00"
            received_at = dt.fromisoformat(captured)
        except (ValueError, AttributeError):
            received_at = dt.now(UTC)

    # Compute raw payload artifact ID for linking
    raw_payload_artifact_id = snapshot.artifact_id if snapshot.artifact_id else None

    # Adapt snapshot to alert signals
    signals, adapt_result = adapt_snapshot_to_alert_signals(
        snapshot=snapshot,
        source_instance=source_instance,
        received_at=received_at,
        raw_payload_artifact_id=raw_payload_artifact_id,
    )

    log_event(
        "alertmanager-snapshot",
        "DEBUG",
        "Alert signal adaptation completed",
        event="alert-signal-adapted",
        run_id=run_id,
        run_label=run_label,
        source_identity=source_instance,
        total_alerts=adapt_result.total_alerts,
        firing_signals=adapt_result.firing_signals_count,
        resolved_signals=adapt_result.resolved_signals_count,
        skipped=adapt_result.skipped_count,
        errors=len(adapt_result.errors),
        cluster_context=effective_cluster_context,
    )

    # Empty snapshot: no workset, no dispatch, no outcome. Return an
    # empty envelope so callers can rely on the return shape.
    if not signals:
        return AlertSignalPromotionDispatchResult(
            workset=None,
            outcome=None,
        )

    # Persist alert signals
    root = directories["root"]
    persist_result, written_signals = persist_alert_signals(
        signals=signals,
        root=root,
        raw_payload_artifact_id=raw_payload_artifact_id,
    )

    log_event(
        "alertmanager-snapshot",
        "INFO",
        "Alert signal artifacts written",
        event="alert-signals-written",
        run_id=run_id,
        run_label=run_label,
        source_identity=source_instance,
        signals_written=persist_result.signals_written,
        signals_duplicates=persist_result.signals_skipped_duplicates,
        signals_failed=persist_result.signals_failed,
        cluster_context=effective_cluster_context,
    )

    # Promote firing signals to incidents via the dispatcher.
    # The scheduler ingestion is the current-run scoped path; the
    # backend NEVER falls back to a global firing-signal scan.
    # The scoped promotion endpoint reads the artifact by its
    # deterministic identity (SHA256-derived), NOT the in-memory
    # ``signal.signal_id`` UUID. Passing the UUID would fail closed
    # with ``signal <uuid> is not present in the current-run
    # scope`` for every non-empty scoped request.
    #
    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 contract:
    #
    # The current-run workset is sourced from the typed
    # ``persistence_outcomes`` field of the adapter result.
    # ``SignalInserted`` and ``SignalIdentityMatched`` outcomes
    # are admitted; ``SignalIdentityConflict`` and
    # ``SignalPersistenceFailed`` outcomes are excluded. The
    # 33-identity-duplicate production regression is fixed
    # because identity-matched observations now enter the
    # workset instead of being silently counted as
    # ``signals_skipped_duplicates``.
    from ..collect.current_run_promotion_workset import (
        CurrentRunSignalProvenance,
        CurrentRunSignalRef,
        build_current_run_workset,
    )
    from ..collect.signal_persistence_outcomes import (
        SignalIdentityMatched as _OutcomeIdentityMatched,
    )
    from ..collect.signal_persistence_outcomes import (
        SignalInserted as _OutcomeSignalInserted,
    )

    # ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 contract:
    #
    # ``workset_refs`` is the raw observation boundary: one
    # ``CurrentRunSignalRef`` per promotable outcome. Repeated
    # references for the same canonical signal identity are
    # expected in this list -- e.g. when an alert appears twice
    # in the snapshot. The validated factory collapses them.
    workset_refs: list[CurrentRunSignalRef] = []
    for outcome in persist_result.promotable_outcomes:
        if isinstance(outcome, _OutcomeSignalInserted):
            provenance = CurrentRunSignalProvenance.INSERTED
            signal_id = outcome.signal_id
        elif isinstance(outcome, _OutcomeIdentityMatched):
            provenance = CurrentRunSignalProvenance.IDENTITY_MATCHED
            signal_id = outcome.signal_id
        else:
            continue
        workset_refs.append(
            CurrentRunSignalRef(
                run_id=run_id,
                signal_id=str(signal_id),
                provenance=provenance,
            )
        )
    # Build a typed workset from the promotable outcomes. The
    # workset is the AUTHORITATIVE source of the backend request:
    # ``workset.signal_ids`` is what we send, not the raw list of
    # persisted writes (which may include artifacts whose storage
    # key collided but whose canonical identity actually agrees).
    # ``build_current_run_workset`` collapses repeated same-id
    # references before constructing the immutable aggregate, so
    # ``current_run_workset.signal_ids`` is unique by construction.
    current_run_workset: CurrentRunPromotionWorkset = build_current_run_workset(
        run_id=run_id,
        source_identity=source_instance,
        references=tuple(workset_refs),
    )
    # ``workset.signal_ids`` is the deterministic, validated
    # current-run scope. Every signal ID we send to the backend
    # is admitted from a typed
    # :class:`SignalInserted` or
    # :class:`SignalIdentityMatched` outcome, run-bound, and free
    # of conflicts / failures.
    current_run_signal_ids: tuple[str, ...] = tuple(
        current_run_workset.signal_ids
    )
    artifact_write_duplicate_count = (
        persist_result.signals_skipped_duplicates
    )
    # ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 collapse
    # metric: the raw reference count is the factory input length,
    # NOT ``promotable_signal_ids`` (a legacy projection) or any
    # written artifact list. After collapse the unique workset
    # membership count is ``workset.total_count``. The collapse
    # count is therefore exactly ``raw - unique``.
    #
    # The cardinality invariant ``unique <= raw`` MUST hold
    # structurally; a violation indicates a contract breach in
    # the producer and is raised via
    # :class:`CurrentRunWorksetCardinalityError` instead of
    # being silently clamped. Clamping via ``max(0, ...)`` would
    # hide a future regression in the factory contract.
    #
    # The calculation lives in a focused helper so it can be
    # regression-tested directly; see
    # ``tests/unit/test_loop_alertmanager_identity_collapse.py``.
    current_batch_identity_collapse_count = (
        _calculate_identity_collapse_count(
            raw_reference_count=len(workset_refs),
            unique_workset_signal_count=current_run_workset.total_count,
        )
    )
    duplicate_count = current_batch_identity_collapse_count
    unique_artifact_identities = list(current_run_signal_ids)

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # capture the real dispatcher result / typed exception AND the
    # authoritative batch records so the classifier sees the
    # production-authoritative envelope. ``BaseException``
    # subclasses (``KeyboardInterrupt``, ``SystemExit``,
    # ``GeneratorExit``) are NOT caught here -- they propagate
    # immediately so process termination cannot be masked by a
    # malformed payload or a regression in the dispatch path.
    from ..collect.incident_identity_hardening import PromotionRecord
    from ..collect.incident_promotion_dispatch import (
        IncidentPromotionResult,
    )

    dispatch_result: IncidentPromotionResult | Exception | None = None
    batch: Any = None
    authoritative_records: tuple[PromotionRecord, ...] | None = None
    try:
        from ..collect.incident_promotion_dispatch import (
            promote_alert_signals_scoped_for_accumulator,
        )

        # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
        # The dispatcher MUST be transport-only at this seam: the
        # accumulator is None here so ``accumulator.add_batch(...)`` is
        # a no-op. The compatibility handoff is a single explicit
        # call AFTER classification, gated on
        # ``is_succeeded(promotion_outcome)`` -- so a single accumulator
        # accepts exactly one materially distinct scoped outcome and
        # any subsequent dispatch against a different outcome is
        # rejected without legacy mutation.
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=root,
            health_run_id=run_id,
            source_identity=source_instance,
            signal_ids=current_run_signal_ids,
            accumulator=None,
            cluster_context=effective_cluster_context,
        )
        dispatch_result = batch.promotion_result
        # Carry the batch's authoritative per-candidate records
        # into the classifier. The batch is the only authoritative
        # envelope in production; ``IncidentPromotionResult.promotion_records``
        # may be a subset (or empty) in test stubs. An EMPTY batch
        # record tuple is still authoritative -- the sentinel
        # ``authoritative_records=None`` means "no batch envelope
        # was produced".
        authoritative_records = tuple(batch.promotion_records)
    except Exception as exc:
        # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
        # the typed exception is captured so the classifier can
        # map it to a ``PromotionCommitUnknown`` outcome. We emit
        # a NON-AUTHORITATIVE transport fact BEFORE classification
        # so the dispatcher-level error string is visible to
        # operators without claiming a commit status that has not
        # yet been classified. The classified typed outcome
        # (``promotion_outcome_event_fields``) is emitted AFTER
        # the classifier runs and is the sole authority for any
        # claim about rejection, failure, or commit state.
        dispatch_result = exc
        log_event(
            "alertmanager-snapshot",
            "DEBUG",
            "Alert signal promotion dispatch exception captured",
            event="promotion-dispatch-exception-captured",
            run_id=run_id,
            run_label=run_label,
            source_identity=source_instance,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            cluster_context=effective_cluster_context,
        )
        # Non-fatal: dispatch exception should not crash the run

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # Classify the real dispatcher result into a typed
    # ``PromotionOutcome`` BEFORE any handoff or authority-bearing
    # telemetry. The classifier is invoked exactly once per attempt;
    # the request payload is the deterministic scoped request that
    # was actually dispatched (``runId`` / ``sourceIdentity`` /
    # ``signalIds`` from the current-run workset).
    try:
        from ..collect.promotion_dispatch_outcome import (
            classify_promotion_dispatch_result,
        )

        requested_signal_payload = _build_scoped_request_payload(
            run_id=run_id,
            source_identity=source_instance,
            signal_ids=current_run_signal_ids,
        )
        promotion_outcome: PromotionOutcome = (
            classify_promotion_dispatch_result(
                run_id=run_id,
                requested_signal_ids=current_run_signal_ids,
                requested_signal_payload=requested_signal_payload,
                outcome=dispatch_result,
                authoritative_records=authoritative_records,
            )
        )
    except BaseException:
        # Process-termination exceptions must propagate BEFORE we
        # record or emit any outcome telemetry. Re-raise without
        # touching the accumulator or logging.
        raise

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # Record the outcome on the accumulator. The recorder returns
    # whether the recording was NEW or IDEMPOTENT so we can gate
    # the compatibility handoff: an identical retry must NOT repeat
    # the handoff (which would duplicate counters, records, and events).
    from ..collect.incident_promotion_outcome_recorder import (
        PromotionOutcomeRecording,
    )

    recording = PromotionOutcomeRecording.NEW
    if promotion_accumulator is not None:
        recording = promotion_accumulator.record_promotion_outcome(
            promotion_outcome
        )

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # Only ``PromotionSucceeded`` may enter the compatibility handoff.
    # ``PromotionRejected`` and ``PromotionCommitUnknown`` are
    # pre-commit / commit-unknown -- no mutation has been confirmed,
    # so the handoff MUST NOT execute and the legacy
    # "alert-signals-promoted" event MUST NOT be emitted.
    from ..collect.promotion_outcomes import is_succeeded as _is_succeeded

    handoff_propagated = False
    handoff_error: str | None = None
    promotion_mode_value: str = ""
    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # Only ``PromotionSucceeded`` may enter the compatibility handoff,
    # AND only when the outcome was NEW (not an idempotent retry).
    # The accumulator received the typed outcome via
    # ``record_promotion_outcome`` above; we now propagate the batch so
    # the canonical IDs and per-candidate records reach the run
    # accumulator. The dispatcher previously would have done this via
    # ``add_batch(batch)`` -- we now do it AFTER classification, on
    # the typed outcome's success path, so legacy state cannot be
    # contaminated by a future classifier failure.
    # Idempotent retries skip the handoff so the snapshot and event
    # counts remain unchanged after the second identical ingestion.
    if (
        _is_succeeded(promotion_outcome)
        and batch is not None
        and recording is PromotionOutcomeRecording.NEW
    ):
        from ..collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        promotion_mode_value = batch.promotion_mode
        log_event_name = (
            "alert-signals-promoted-via-backend"
            if promotion_mode_value == "backend-api"
            else "alert-signals-promoted"
        )

        error_messages = list(batch.error_messages)
        bounded_error_messages = error_messages[:5]

        # Read actionable_incident_ids from the typed outcome
        # (authoritative after classification) rather than from the
        # raw batch envelope.
        actionable = list(promotion_outcome.diagnosis_incident_ids)  # type: ignore[union-attr]

        observation_refreshed_count = len(
            getattr(batch.promotion_result, "observation_refreshed_incident_ids", ())
        )
        unchanged_count = len(
            getattr(batch.promotion_result, "unchanged_incident_ids", ())
        )

        try:
            if promotion_accumulator is not None:
                propagation_result = propagate_promotion_result_to_run(
                    batch=batch,
                    accumulator=promotion_accumulator,
                    source="alertmanager",
                )
                handoff_propagated = True
                log_event(
                    "alertmanager-snapshot",
                    "DEBUG",
                    "Promotion handoff completed",
                    event="promotion-handoff-completed",
                    run_id=run_id,
                    run_label=run_label,
                    source_identity=source_instance,
                    handoff_source=propagation_result.source,
                    actionable_count=propagation_result.total_actionable,
                    added_count=propagation_result.added_count,
                    duplicate_count=propagation_result.duplicate_count,
                    workset_state=promotion_accumulator.workset_state.value,
                    cluster_context=effective_cluster_context,
                )
        except Exception as handoff_exc:
            from ..collect.promotion_diagnosis_handoff import (
                PromotionDiagnosisHandoffError,
            )

            if isinstance(handoff_exc, PromotionDiagnosisHandoffError):
                handoff_error = (
                    f"{handoff_exc.reason_code.value}: {str(handoff_exc)}"
                )
            else:
                handoff_error = str(handoff_exc)
            log_event(
                "alertmanager-snapshot",
                "WARNING",
                "Promotion handoff failed - diagnosis may be affected",
                event="promotion-handoff-failed",
                run_id=run_id,
                run_label=run_label,
                source_identity=source_instance,
                severity_reason=handoff_error,
                reason="handoff-failure",
                promotion_propagated_to_diagnosis=False,
                workset_state=(
                    promotion_accumulator.workset_state.value
                    if promotion_accumulator is not None
                    else "unknown"
                ),
                cluster_context=effective_cluster_context,
            )

        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alert signals promoted to incidents",
            event=log_event_name,
            run_id=run_id,
            run_label=run_label,
            source_identity=source_instance,
            promotion_scope="explicit_current_run_signal_ids",
            promotion_scan_scope=batch.promotion_scan_scope,
            requested_signal_count=len(current_run_signal_ids),
            persisted_signal_count=len(written_signals),
            unique_artifact_signal_count=len(unique_artifact_identities),
            artifact_write_duplicate_count=artifact_write_duplicate_count,
            current_batch_identity_collapse_count=current_batch_identity_collapse_count,
            duplicate_artifact_count=duplicate_count,
            scanned_signal_count=batch.scanned,
            opened_incident_count=batch.opened_incidents,
            materially_changed_incident_count=batch.updated_incidents,
            observation_refreshed_incident_count=observation_refreshed_count,
            unchanged_incident_count=unchanged_count,
            actionable_incident_count=len(actionable),
            skipped_signal_count=batch.skipped_duplicates,
            failure_count=batch.errors,
            incident_access_mode=batch.incident_access_mode,
            promotion_mode=promotion_mode_value,
            unique_candidate_count=batch.unique_candidate_count,
            promotion_record_count=len(batch.promotion_records),
            # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
            # ``promotion_propagated_to_diagnosis`` is FALSE during
            # Item 3. Diagnosis invocation is Item 4. The
            # compatibility-handoff-success flag is named
            # ``promotion_handoff_to_run_completed`` so the legacy
            # field is not asserted prematurely.
            promotion_handoff_to_run_completed=handoff_propagated,
            promotion_propagated_to_diagnosis=False,
            cluster_context=effective_cluster_context,
            error_messages=bounded_error_messages,
        )
    else:
        # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
        # Non-success typed outcomes do NOT trigger the legacy
        # "promoted" event nor the handoff. The classified outcome
        # alone is the authority for any downstream telemetry.
        from ..collect.promotion_outcomes import (
            PromotionRejected,
        )

        if isinstance(promotion_outcome, PromotionRejected):
            log_event(
                "alertmanager-snapshot",
                "INFO",
                "Alert signal promotion rejected by dispatcher",
                event="alert-signal-promotion-rejected",
                run_id=run_id,
                run_label=run_label,
                source_identity=source_instance,
                rejection_reason=promotion_outcome.reason.value,
                rejected_signal_count=len(promotion_outcome.rejected_signal_ids),
                cluster_context=effective_cluster_context,
            )
        # else: ``PromotionCommitUnknown`` -- no promoted event; the
        # outcome-classified telemetry below is the authority.

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01:
    # Emit the typed outcome projection. The classified outcome is
    # the single source of truth for every authority-bearing
    # field on this event.
    from ..collect.promotion_dispatch_outcome import (
        promotion_outcome_event_fields,
    )

    outcome_projection = promotion_outcome_event_fields(promotion_outcome)
    log_event(
        "alertmanager-snapshot",
        "DEBUG",
        "Promotion dispatch outcome classified",
        event="promotion-dispatch-outcome-classified",
        run_id=run_id,
        run_label=run_label,
        source_identity=source_instance,
        promotion_outcome=outcome_projection["promotion_outcome"],
        promotion_outcome_reason=outcome_projection[
            "promotion_outcome_reason"
        ],
        promotion_may_have_committed=outcome_projection[
            "promotion_may_have_committed"
        ],
        diagnosis_handoff_available=outcome_projection[
            "diagnosis_handoff_available"
        ],
        diagnosis_handoff_incident_count=outcome_projection[
            "diagnosis_handoff_incident_count"
        ],
        diagnosis_invoked=outcome_projection["diagnosis_invoked"],
        promotion_consistency_error_recorded=outcome_projection[
            "promotion_consistency_error_recorded"
        ],
        promotion_outcome_available=outcome_projection[
            "promotion_outcome_available"
        ],
        reconciliation_required=outcome_projection[
            "reconciliation_required"
        ],
        requested_signal_count=outcome_projection["requested_signal_count"],
        canonical_incident_id_count=outcome_projection[
            "canonical_incident_id_count"
        ],
        promotion_record_count=outcome_projection["promotion_record_count"],
        promotion_outcome_variant=(
            promotion_accumulator.promotion_outcome_variant_label()
            if promotion_accumulator is not None
            else "synthesised"
        ),
        cluster_context=effective_cluster_context,
    )

    return AlertSignalPromotionDispatchResult(
        workset=current_run_workset,
        outcome=promotion_outcome,
    )
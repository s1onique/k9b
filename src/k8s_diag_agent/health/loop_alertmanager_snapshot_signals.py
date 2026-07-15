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
from datetime import UTC
from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..collect.incident_promotion_accumulator import RunPromotionAccumulator
    from ..collect.incident_store import IncidentStore
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
) -> None:
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
        promotion_accumulator: Typed run-scoped accumulator that captures
            canonical incident IDs for the diagnosis dispatcher. When
            ``None``, the scheduler still promotes but the canonical
            incident IDs are NOT propagated to automatic diagnosis.
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

    # Persist alert signals
    if signals:
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
        current_run_workset = build_current_run_workset(
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
        try:
            from ..collect.incident_promotion_dispatch import (
                promote_alert_signals_scoped_for_accumulator,
            )

            batch = promote_alert_signals_scoped_for_accumulator(
                runs_dir=root,
                health_run_id=run_id,
                source_identity=source_instance,
                signal_ids=current_run_signal_ids,
                accumulator=promotion_accumulator,
                cluster_context=effective_cluster_context,
            )

            promotion_mode = batch.promotion_mode
            log_event_name = (
                "alert-signals-promoted-via-backend"
                if promotion_mode == "backend-api"
                else "alert-signals-promoted"
            )

            error_messages = list(batch.error_messages)
            bounded_error_messages = error_messages[:5]

            # SEAM01: Use canonical handoff helper instead of direct extraction
            # Read actionable_incident_ids from promotion_result (not from batch)
            promotion_result = batch.promotion_result
            actionable = list(promotion_result.actionable_incident_ids)

            # R2: read the typed category counts from the batch result so
            # the log line is scope-honest; the previous implementation
            # hard-coded both fields to zero.
            observation_refreshed_count = len(
                getattr(promotion_result, "observation_refreshed_incident_ids", ())
            )
            unchanged_count = len(
                getattr(promotion_result, "unchanged_incident_ids", ())
            )

            # SEAM01: Propagate to accumulator via canonical handoff
            # This is the ONLY allowed production path for promotion-to-diagnosis
            from ..collect.promotion_diagnosis_handoff import (
                propagate_promotion_result_to_run,
            )

            handoff_propagated = False
            handoff_error: str | None = None
            try:
                if promotion_accumulator is not None:
                    propagation_result = propagate_promotion_result_to_run(
                        batch=batch,
                        accumulator=promotion_accumulator,
                        source="alertmanager",
                    )
                    handoff_propagated = True
                    # SEAM01 R2: Log propagation telemetry from captured result
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
                # SEAM01: Handoff failure is distinct from execution failure
                # Log handoff failure but DO NOT conflate with promotion failure
                # SEAM01 R2: State is already set on accumulator by handoff function
                from ..collect.promotion_diagnosis_handoff import (
                    PromotionDiagnosisHandoffError,
                )

                if isinstance(handoff_exc, PromotionDiagnosisHandoffError):
                    handoff_error = f"{handoff_exc.reason_code.value}: {str(handoff_exc)}"
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
                    promotion_may_have_committed=True,
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
                # R3: surface the two distinct duplicate metrics so the
                # audit log can attribute each duplicate to either the
                # raw persistence layer (already-existing artifacts on
                # disk) or the current-batch identity collapse step
                # (stable-deduplication before posting).
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
                promotion_mode=promotion_mode,
                unique_candidate_count=batch.unique_candidate_count,
                promotion_record_count=len(batch.promotion_records),
                # SEAM01: Handoff propagation telemetry
                promotion_propagated_to_diagnosis=handoff_propagated,
                promotion_may_have_committed=True,  # Promotion succeeded
                cluster_context=effective_cluster_context,
                error_messages=bounded_error_messages,
            )
        except Exception as exc:
            # SEAM01: Promotion execution failure is DISTINCT from handoff failure
            # A returned promotion result must never later be logged as execution failure
            log_event(
                "alertmanager-snapshot",
                "WARNING",
                "Alert signal promotion failed",
                event="alert-signal-promotion-failed",
                run_id=run_id,
                run_label=run_label,
                source_identity=source_instance,
                severity_reason=str(exc),
                reason="promotion-execution-failed",
                promotion_may_have_committed=False,
                promotion_propagated_to_diagnosis=False,
                cluster_context=effective_cluster_context,
            )
            # Non-fatal: promotion failure should not crash the run

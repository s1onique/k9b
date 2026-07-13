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
        # R3: stable-deduplicate the artifact workset before posting.
        # ``PersistAlertSignal`` includes already-existing duplicate
        # artifacts (retry/rebuild semantics). The scoped backend
        # contract rejects duplicate ``signalIds`` via
        # ``PromoteAlertSignalsRequest`` so we MUST collapse repeated
        # artifact identities into a unique tuple. The two duplicate
        # counts are exposed as separate metrics so the audit log can
        # distinguish between raw persistence duplicates (skipped
        # writes to disk) and the current-batch identity collapse
        # (collapse caused by stable-deduplication before posting).
        unique_artifact_identities: list[str] = list(
            dict.fromkeys(
                str(persisted.artifact_identity) for persisted in written_signals
            )
        )
        # ``artifact_write_duplicate_count`` is the raw persistence
        # duplicate count reported by ``persist_alert_signals``. It is
        # the number of artifacts that were already on disk from a
        # previous run and therefore were NOT re-persisted this run.
        artifact_write_duplicate_count = int(
            getattr(persist_result, "signals_skipped_duplicates", 0) or 0
        )
        # ``current_batch_identity_collapse_count`` is the difference
        # between the raw persisted count and the unique
        # artifact-identity count. It represents the number of
        # duplicates collapsed by the stable-deduplication step
        # before posting to the scoped backend.
        current_batch_identity_collapse_count = max(
            0,
            len(written_signals) - len(unique_artifact_identities),
        )
        # ``duplicate_artifact_count`` is preserved for back-compat
        # with the legacy log field but now reflects the current-batch
        # identity collapse metric (the value callers have historically
        # inferred).
        duplicate_count = current_batch_identity_collapse_count
        current_run_signal_ids: tuple[str, ...] = tuple(unique_artifact_identities)
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
            actionable = list(batch.canonical_incident_ids())
            # R2: read the typed category counts from the batch result so
            # the log line is scope-honest; the previous implementation
            # hard-coded both fields to zero.
            promotion_result = batch.promotion_result
            observation_refreshed_count = len(
                getattr(promotion_result, "observation_refreshed_incident_ids", ())
            )
            unchanged_count = len(
                getattr(promotion_result, "unchanged_incident_ids", ())
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
                cluster_context=effective_cluster_context,
                error_messages=bounded_error_messages,
            )
        except Exception as exc:
            log_event(
                "alertmanager-snapshot",
                "WARNING",
                "Alert signal promotion failed",
                event="alert-signal-promotion-failed",
                run_id=run_id,
                run_label=run_label,
                source_identity=source_instance,
                severity_reason=str(exc),
                reason="promotion-error",
                cluster_context=effective_cluster_context,
            )
            # Non-fatal: promotion failure should not crash the run

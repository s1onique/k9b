"""Alert signal ingestion for Alertmanager snapshot collection.

This module handles the conversion of Alertmanager snapshots into AlertSignal
domain objects and their promotion to incidents.

This module is intentionally isolated from collection logic to keep the
ingestion path testable independently.

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
) -> None:
    """Ingest Alertmanager alerts as AlertSignal artifacts and promote to incidents.

    This function:
    1. Converts NormalizedAlert objects to AlertSignal domain model
    2. Persists alert signal artifacts for idempotency
    3. Promotes firing alerts into IncidentStore when available

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

        # Promote firing signals to incidents
        # The dispatcher selects the appropriate path (local vs backend-api) based on config.
        # In backend-api mode, we scan artifacts and POST to backend internal API.
        # In local mode, we use the provided incident_store directly.
        try:
            # Import dispatcher at runtime to avoid circular imports
            from ..collect.incident_promotion_dispatch import (
                promote_alert_signals_from_artifacts,
            )

            # Use the dispatcher which handles both local and backend-api modes
            promotion_result = promote_alert_signals_from_artifacts(
                runs_dir=root,
                snapshot_bundle_id=None,
            )

            # Map dispatcher result to log format - use actual promotion_mode
            log_event_name = (
                "alert-signals-promoted-via-backend"
                if promotion_result.promotion_mode == "backend-api"
                else "alert-signals-promoted"
            )
            log_event(
                "alertmanager-snapshot",
                "INFO",
                "Alert signals promoted to incidents",
                event=log_event_name,
                run_id=run_id,
                run_label=run_label,
                source_identity=source_instance,
                scanned=promotion_result.scanned,
                firing=promotion_result.firing,
                opened_incidents=promotion_result.opened_incidents,
                updated_incidents=promotion_result.updated_incidents,
                skipped_duplicates=promotion_result.skipped_duplicates,
                errors=promotion_result.errors,
                cluster_context=effective_cluster_context,
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

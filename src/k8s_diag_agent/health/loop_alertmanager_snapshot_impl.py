"""Alertmanager snapshot collection orchestrator.

This module orchestrates the collection process using helpers from
loop_alertmanager_snapshot_collection.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .loop_alertmanager_snapshot_collection import (
    determine_port_forward_need,
    fetch_alertmanager_snapshot,
    select_eligible_source,
    write_snapshot_artifacts,
)
from .loop_alertmanager_snapshot_signals import _ingest_alert_signals

if TYPE_CHECKING:
    from ..collect.incident_promotion_accumulator import RunPromotionAccumulator
    from ..collect.incident_store import IncidentStore
    from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory


def run_alertmanager_snapshot_collection(
    inventory: AlertmanagerSourceInventory | None,
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
    directories: dict[str, Path],
    start_port_forward: Callable[..., tuple[subprocess.Popen[str], int]],
    stop_port_forward: Callable[..., None],
    incident_store: IncidentStore | None = None,
    promotion_accumulator: RunPromotionAccumulator | None = None,
) -> None:
    """Collect Alertmanager snapshot and compact artifacts for tracked sources.

    This function runs after Alertmanager discovery has populated the inventory
    with verified/tracked sources.

    Selection rule: Query the first eligible source (by deterministic order:
    MANUAL > AUTO_TRACKED). Excludes DISCOVERED, DEGRADED, and MISSING sources.
    Skip if no eligible sources exist.

    For cluster-internal endpoints (e.g., alertmanager-operated.monitoring:9093),
    this function uses the provided port-forward callable to reach the service
    when running outside the cluster network.

    This is non-fatal: fetch failures are logged but do not stop the run.

    Alert signal ingestion:
    - Fetches /api/v2/alerts from tracked Alertmanager sources
    - Normalizes alerts into AlertSignal objects
    - Persists alert signal artifacts for incident promotion
    - Promotes firing alerts into IncidentStore when available

    Args:
        inventory: Alertmanager source inventory from discovery (may be None).
        run_id: Run identifier for artifact naming.
        run_label: Run label for logging.
        log_event: Callback for structured logging (component, severity, message, **metadata).
        directories: Dict with "root" key pointing to health run directory.
        start_port_forward: Callable to start kubectl port-forward.
            Signature: (namespace, service_name, context) -> (process, local_port)
        stop_port_forward: Callable to stop port-forward process.
            Signature: (process, local_port) -> None
        incident_store: Optional IncidentStore for alert-to-incident promotion.
    """
    # Log start of snapshot collection
    log_event(
        "alertmanager-snapshot",
        "INFO",
        "Alertmanager snapshot collection started",
        event="alertmanager-snapshot-start",
        run_id=run_id,
        run_label=run_label,
    )

    if inventory is None:
        log_event(
            "alertmanager-snapshot",
            "WARNING",
            "Alertmanager inventory not available (discovery may have failed)",
            event="alertmanager-snapshot-skipped",
            run_id=run_id,
            run_label=run_label,
            reason="no_inventory",
        )
        return

    # Select eligible source
    selected_source, effective_cluster_context = select_eligible_source(
        inventory=inventory,
        log_event=log_event,
        run_id=run_id,
        run_label=run_label,
    )

    if selected_source is None:
        # No eligible sources - logged in select_eligible_source
        return

    endpoint = selected_source.endpoint

    # Determine port-forward need and extract service name
    needs_port_forward, service_name_for_pf = determine_port_forward_need(
        endpoint=endpoint,
        selected_source=selected_source,
    )

    # Validate service name extraction
    if needs_port_forward and not service_name_for_pf:
        log_event(
            "alertmanager-snapshot",
            "DEBUG",
            "Alertmanager endpoint appears cluster-internal but cannot derive service name",
            event="alertmanager-snapshot-source-selected",
            run_id=run_id,
            source_identity=selected_source.source_id,
            reason="no_service_name_for_port_forward",
        )
        needs_port_forward = False

    # Attempt to establish port-forward if needed
    port_forward_process: subprocess.Popen[str] | None = None
    local_port: int | None = None

    if needs_port_forward:
        assert selected_source.namespace is not None
        assert service_name_for_pf is not None
        # Use source context, fall back to inventory context if not set
        context = selected_source.cluster_context or inventory.cluster_context
        try:
            port_forward_process, local_port = start_port_forward(
                namespace=selected_source.namespace,
                service_name=service_name_for_pf,
                context=context,
            )
        except RuntimeError as exc:
            # Port-forward startup failed, but this is non-fatal
            # Log the error and continue with error snapshot
            log_event(
                "alertmanager-snapshot",
                "WARNING",
                "Alertmanager port-forward startup failed, proceeding with direct fetch",
                event="alertmanager-portforward-failed-non-fatal",
                run_id=run_id,
                run_label=run_label,
                source_identity=selected_source.source_id,
                severity_reason=str(exc),
                reason="portforward-startup-failed",
                cluster_context=effective_cluster_context,
            )
            # Continue to fetch without port-forward; will likely fail but that's non-fatal
            needs_port_forward = False
            port_forward_process = None
            local_port = None

    # Fetch alerts from the selected source
    snapshot = fetch_alertmanager_snapshot(
        endpoint=endpoint,
        selected_source=selected_source,
        local_port=local_port,
        log_event=log_event,
        run_id=run_id,
        run_label=run_label,
        effective_cluster_context=effective_cluster_context,
    )

    # Always clean up port-forward if it was started
    if port_forward_process is not None:
        stop_port_forward(port_forward_process, local_port)

    # Write artifacts
    snapshot_path, compact_path = write_snapshot_artifacts(
        snapshot=snapshot,
        selected_source=selected_source,
        directories=directories,
        run_id=run_id,
        run_label=run_label,
        log_event=log_event,
        effective_cluster_context=effective_cluster_context,
    )

    # --- Alert Signal Ingestion ---
    # Convert snapshot alerts to AlertSignal artifacts and promote to incidents.
    # The ``promotion_accumulator`` is the typed run-scoped handoff that
    # captures canonical ``incident_id`` values emitted by the dispatcher
    # so the orchestrator can aggregate them deterministically without
    # relying on the legacy ``directories["__last_promotion_result__"]``
    # sentinel.
    _ingest_alert_signals(
        snapshot=snapshot,
        selected_source=selected_source,
        snapshot_path=snapshot_path,
        directories=directories,
        incident_store=incident_store,
        log_event=log_event,
        run_id=run_id,
        run_label=run_label,
        effective_cluster_context=effective_cluster_context,
        promotion_accumulator=promotion_accumulator,
    )

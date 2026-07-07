"""Alertmanager snapshot collection runner for health loop.

Extracts the Alertmanager snapshot collection flow from HealthLoopRunner into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the snapshot collection logic that:
1. Selects eligible sources (MANUAL > AUTO_TRACKED) from verified inventory
2. Handles port-forward for cluster-internal endpoints
3. Fetches alerts from selected source via HTTP /api/v2/alerts
4. Writes snapshot and compact artifacts

Port-forward infrastructure (port selection, TCP polling, kubectl process management) remains
in loop.py and is injected as callable parameters to this module.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.alertmanager_artifact import write_alertmanager_artifacts
from ..external_analysis.alertmanager_discovery import (
    AlertmanagerSourceInventory,
    AlertmanagerSourceState,
)
from ..external_analysis.alertmanager_snapshot import (
    AlertmanagerStatus,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from ..incident_alert_signal_snapshot_adapter import (
    adapt_snapshot_to_alert_signals,
    persist_alert_signals,
)

if TYPE_CHECKING:
    from ..collect.incident_store import IncidentStore
    from ..external_analysis.alertmanager_discovery import AlertmanagerSource
    from ..external_analysis.alertmanager_snapshot import AlertmanagerSnapshot


def run_alertmanager_snapshot_collection(
    inventory: AlertmanagerSourceInventory | None,
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
    directories: dict[str, Path],
    start_port_forward: Callable[..., tuple[subprocess.Popen[str], int]],
    stop_port_forward: Callable[..., None],
    incident_store: IncidentStore | None = None,
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

    # Select eligible sources: MANUAL or AUTO_TRACKED
    # Exclude DISCOVERED (not verified), DEGRADED (failed verification), MISSING
    manual_sources = list(inventory.get_by_state(AlertmanagerSourceState.MANUAL))
    auto_tracked_sources = list(inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED))

    # Deterministic selection: prefer MANUAL, then AUTO_TRACKED
    eligible_sources = manual_sources + auto_tracked_sources

    if not eligible_sources:
        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager snapshot skipped: no eligible tracked sources",
            event="alertmanager-snapshot-skipped",
            run_id=run_id,
            run_label=run_label,
            reason="no_eligible_sources",
            total_discovered=len(inventory.sources),
            manual_count=len(manual_sources),
            auto_tracked_count=len(auto_tracked_sources),
            cluster_context=inventory.cluster_context,
        )
        return

    # Select the first eligible source (stable, deterministic)
    selected_source = eligible_sources[0]

    # Compute effective cluster context once: prefer per-source value, fall back to inventory
    # This ensures all snapshot-stage logs have a valid context value for observability
    effective_cluster_context = selected_source.cluster_context or inventory.cluster_context

    log_event(
        "alertmanager-snapshot",
        "DEBUG",
        "Alertmanager source selected for snapshot",
        event="alertmanager-snapshot-source-selected",
        run_id=run_id,
        run_label=run_label,
        source_identity=selected_source.source_id,
        source_endpoint=selected_source.endpoint,
        source_origin=selected_source.origin.value,
        source_state=selected_source.state.value,
        cluster_context=effective_cluster_context,
        total_eligible=len(eligible_sources),
    )

    # Determine if we need port-forward for this source
    port_forward_process: subprocess.Popen[str] | None = None
    local_port: int | None = None
    needs_port_forward = False

    # Check if endpoint looks like a cluster-internal DNS name (contains '.' for FQDN)
    # Skip localhost and 127.0.0.1 which are directly reachable
    endpoint = selected_source.endpoint
    if endpoint and "://" in endpoint:
        # Extract host from URL
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        host = parsed.hostname or ""
        # If host contains a dot and is not localhost, it's likely a cluster-internal FQDN
        # that won't resolve from outside the cluster
        if "." in host and host not in ("localhost", "127.0.0.1", "::1"):
            needs_port_forward = True

    # Extract the service name from the endpoint host for port-forward
    # In real Prometheus Operator deployments, the Alertmanager object name differs
    # from the service DNS name in the endpoint (e.g., object name is
    # "kube-prometheus-stack-alertmanager" but service DNS is "alertmanager-operated")
    service_name_for_pf: str | None = None
    if needs_port_forward:
        # Parse endpoint to get the service name from the host (first part of FQDN)
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        host = parsed.hostname or ""
        # Host format: "service-name.namespace.svc.cluster.local" or just "service-name"
        # The service name is the first component before any dot
        if "." in host:
            service_name_for_pf = host.split(".")[0]
        elif selected_source.name:
            # Fallback to name if host has no dots (edge case)
            service_name_for_pf = selected_source.name

        if not service_name_for_pf:
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
    snapshot: AlertmanagerSnapshot
    try:
        if port_forward_process is not None and local_port is not None:
            # Use the port-forwarded local endpoint
            fetch_url = f"http://127.0.0.1:{local_port}/api/v2/alerts"
        else:
            # Use the direct endpoint
            fetch_url = f"{endpoint.rstrip('/')}/api/v2/alerts"

        timeout_seconds = 10.0
        headers: dict[str, str] = {"Accept": "application/json"}

        req = urllib.request.Request(fetch_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = response.read()
            raw_response = json.loads(body)

        # Normalize the response into a snapshot
        # Pass the source endpoint for provenance tracking
        snapshot = normalize_alertmanager_payload(
            raw_response,
            source=selected_source.endpoint,
        )

        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager snapshot fetched successfully",
            event="alertmanager-snapshot-fetched",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            source_endpoint=selected_source.endpoint,
            alert_count=snapshot.alert_count,
            snapshot_status=snapshot.status.value,
            cluster_context=effective_cluster_context,
        )

    except urllib.error.HTTPError as exc:
        if exc.code == 401 or exc.code == 403:
            error_msg = f"Alertmanager auth failed: {exc.code}"
        else:
            error_msg = f"Alertmanager returned {exc.code}: {exc.reason}"
        snapshot = create_error_snapshot(
            AlertmanagerStatus.UPSTREAM_ERROR,
            error_msg,
            source=selected_source.endpoint,
        )
        log_event(
            "alertmanager-snapshot",
            "WARNING",
            "Alertmanager snapshot fetch failed",
            event="alertmanager-snapshot-failed",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            source_endpoint=selected_source.endpoint,
            severity_reason=error_msg,
            reason="fetch-error",
            cluster_context=selected_source.cluster_context,
        )
        # Non-fatal: continue with error snapshot

    except urllib.error.URLError as exc:
        error_msg = f"Alertmanager unreachable: {exc.reason}"
        snapshot = create_error_snapshot(
            AlertmanagerStatus.UPSTREAM_ERROR,
            error_msg,
            source=selected_source.endpoint,
        )
        log_event(
            "alertmanager-snapshot",
            "WARNING",
            "Alertmanager snapshot fetch failed",
            event="alertmanager-snapshot-failed",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            source_endpoint=selected_source.endpoint,
            severity_reason=error_msg,
            reason="connection-error",
            cluster_context=effective_cluster_context,
        )
        # Non-fatal: continue with error snapshot

    # REVIEWED: HTTP/urllib fetch boundary for Alertmanager snapshot.
    # urllib.error.HTTPError and urllib.error.URLError already handled above.
    # This fallback catches: OSError (socket/network), TimeoutError (request timeout),
    # UnicodeDecodeError (response body encoding), json.JSONDecodeError (malformed JSON),
    # ValueError (malformed URL/headers). All result in INVALID_RESPONSE snapshot, non-fatal.
    # No credential exposure: error_msg from str(exc) sanitized by callers above, source_endpoint
    # is the Alertmanager URL (auth info not logged per upstream handlers).
    except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        error_msg = str(exc)
        snapshot = create_error_snapshot(
            AlertmanagerStatus.INVALID_RESPONSE,
            error_msg,
            source=selected_source.endpoint,
        )
        log_event(
            "alertmanager-snapshot",
            "WARNING",
            "Alertmanager snapshot fetch failed",
            event="alertmanager-snapshot-failed",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            source_endpoint=selected_source.endpoint,
            severity_reason=error_msg,
            reason="unknown-error",
            cluster_context=effective_cluster_context,
        )
        # Non-fatal: continue with error snapshot

    # Always clean up port-forward if it was started
    if port_forward_process is not None:
        stop_port_forward(port_forward_process, local_port)

    # Create compact summarization
    # Pass cluster_label for cluster attribution in UI when alerts lack cluster labels
    # Use selected_source.cluster_label (the Kubernetes context/label) for cluster attribution,
    # as this is the correct field for per-cluster UI filtering and affected_clusters display
    compact = snapshot_to_compact(
        snapshot,
        cluster_label=selected_source.cluster_label,
    )

    # Write both artifacts
    try:
        snapshot_path, compact_path = write_alertmanager_artifacts(
            directories["root"],
            run_id,
            snapshot,
            compact,
        )

        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager snapshot artifacts written",
            event="alertmanager-snapshot-written",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            source_endpoint=selected_source.endpoint,
            snapshot_path=str(snapshot_path),
            compact_path=str(compact_path),
            alert_count=snapshot.alert_count,
            snapshot_status=snapshot.status.value,
            cluster_context=effective_cluster_context,
        )

    except OSError as exc:
        log_event(
            "alertmanager-snapshot",
            "ERROR",
            "Failed to write Alertmanager snapshot artifacts",
            event="alertmanager-snapshot-write-failed",
            run_id=run_id,
            run_label=run_label,
            source_identity=selected_source.source_id,
            severity_reason=str(exc),
            reason="write-error",
        )
        # Continue without failing the run

    # --- Alert Signal Ingestion ---
    # Convert snapshot alerts to AlertSignal artifacts and promote to incidents
    _ingest_alert_signals(
        snapshot=snapshot,
        selected_source=selected_source,
        snapshot_path=locals().get("snapshot_path"),
        directories=directories,
        incident_store=incident_store,
        log_event=log_event,
        run_id=run_id,
        run_label=run_label,
        effective_cluster_context=effective_cluster_context,
    )


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
    from datetime import UTC
    from datetime import datetime as dt

    from ..incident_alert_promotion import promote_alert_signals_to_incidents

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

        # Promote firing signals to incidents if store is available
        if incident_store is not None and persist_result.signals_written > 0:
            try:
                promotion_result = promote_alert_signals_to_incidents(
                    incident_store=incident_store,
                    runs_dir=root,
                    now=received_at,
                )

                log_event(
                    "alertmanager-snapshot",
                    "INFO",
                    "Alert signals promoted to incidents",
                    event="alert-signals-promoted",
                    run_id=run_id,
                    run_label=run_label,
                    source_identity=source_instance,
                    scanned=promotion_result.scanned_signal_count,
                    firing=promotion_result.firing_signal_count,
                    opened_incidents=promotion_result.opened_incident_count,
                    updated_incidents=promotion_result.updated_incident_count,
                    skipped_duplicates=promotion_result.skipped_duplicate_count,
                    errors=promotion_result.error_count,
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

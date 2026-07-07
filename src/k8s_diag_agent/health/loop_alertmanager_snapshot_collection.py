"""Low-level collection helpers for Alertmanager snapshot collection.

This module contains standalone helper functions that can be tested independently:
- Source selection logic
- Port-forward need detection
- HTTP fetching with error handling
- Artifact writing

These functions are injected into the main orchestrator via parameters
to keep the collection logic testable.
"""

from __future__ import annotations

import json
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
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)

if TYPE_CHECKING:
    from ..external_analysis.alertmanager_discovery import AlertmanagerSource


def select_eligible_source(
    inventory: AlertmanagerSourceInventory,
    log_event: Callable[..., None],
    run_id: str,
    run_label: str,
) -> tuple[AlertmanagerSource | None, str | None]:
    """Select the first eligible Alertmanager source for snapshot collection.

    Selection rule: Query the first eligible source (by deterministic order:
    MANUAL > AUTO_TRACKED). Excludes DISCOVERED, DEGRADED, and MISSING sources.
    Returns None if no eligible sources exist.

    Args:
        inventory: Alertmanager source inventory from discovery.
        log_event: Logging callback for debug messages.
        run_id: Run identifier for logging.
        run_label: Run label for logging.

    Returns:
        Tuple of (selected_source, effective_cluster_context) or (None, None) if no eligible sources.
    """
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
        return None, None

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

    return selected_source, effective_cluster_context


def determine_port_forward_need(
    endpoint: str,
    selected_source: AlertmanagerSource,
) -> tuple[bool, str | None]:
    """Determine if port-forward is needed for the given endpoint.

    Args:
        endpoint: The Alertmanager endpoint URL.
        selected_source: The source object for fallback name extraction.

    Returns:
        Tuple of (needs_port_forward, service_name_for_pf) or (False, None) if not needed.
    """
    from urllib.parse import urlparse

    # Check if endpoint looks like a cluster-internal DNS name (contains '.' for FQDN)
    # Skip localhost and 127.0.0.1 which are directly reachable
    if endpoint and "://" in endpoint:
        parsed = urlparse(endpoint)
        host = parsed.hostname or ""
        # If host contains a dot and is not localhost, it's likely a cluster-internal FQDN
        # that won't resolve from outside the cluster
        if "." in host and host not in ("localhost", "127.0.0.1", "::1"):
            needs_port_forward = True
        else:
            return False, None
    else:
        return False, None

    # Extract the service name from the endpoint host for port-forward
    # In real Prometheus Operator deployments, the Alertmanager object name differs
    # from the service DNS name in the endpoint (e.g., object name is
    # "kube-prometheus-stack-alertmanager" but service DNS is "alertmanager-operated")
    service_name_for_pf: str | None = None
    if needs_port_forward:
        # Parse endpoint to get the service name from the host (first part of FQDN)
        parsed = urlparse(endpoint)
        host = parsed.hostname or ""
        # Host format: "service-name.namespace.svc.cluster.local" or just "service-name"
        # The service name is the first component before any dot
        if "." in host:
            service_name_for_pf = host.split(".")[0]
        elif selected_source.name:
            # Fallback to name if host has no dots (edge case)
            service_name_for_pf = selected_source.name

    return needs_port_forward, service_name_for_pf


def fetch_alertmanager_snapshot(
    endpoint: str,
    selected_source: AlertmanagerSource,
    local_port: int | None,
    log_event: Callable[..., None],
    run_id: str,
    run_label: str,
    effective_cluster_context: str | None,
) -> AlertmanagerSnapshot:
    """Fetch alerts from Alertmanager source via HTTP.

    Args:
        endpoint: The source endpoint URL.
        selected_source: The selected Alertmanager source.
        local_port: Local port if using port-forward, None otherwise.
        log_event: Logging callback.
        run_id: Run identifier.
        run_label: Run label.
        effective_cluster_context: Cluster context for logging.

    Returns:
        AlertmanagerSnapshot from successful fetch or error snapshot on failure.
    """
    snapshot: AlertmanagerSnapshot
    try:
        if local_port is not None:
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

    return snapshot


def write_snapshot_artifacts(
    snapshot: AlertmanagerSnapshot,
    selected_source: AlertmanagerSource,
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
    effective_cluster_context: str | None,
) -> tuple[Path | None, Path | None]:
    """Write Alertmanager snapshot and compact artifacts.

    Args:
        snapshot: The normalized Alertmanager snapshot.
        selected_source: The selected Alertmanager source.
        directories: Output directories dict with "root" key.
        run_id: Run identifier for artifact naming.
        run_label: Run label for logging.
        log_event: Logging callback.
        effective_cluster_context: Cluster context for logging.

    Returns:
        Tuple of (snapshot_path, compact_path) or (None, None) on failure.
    """
    # Create compact summarization
    # Pass cluster_label for cluster attribution in UI when alerts lack cluster labels
    # Use selected_source.cluster_label (the Kubernetes context/label) for cluster attribution,
    # as this is the correct field for per-cluster UI filtering and affected_clusters display
    compact = snapshot_to_compact(
        snapshot,
        cluster_label=selected_source.cluster_label,
    )

    # Write both artifacts
    snapshot_path: Path | None = None
    compact_path: Path | None = None
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

    return snapshot_path, compact_path

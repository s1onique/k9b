"""Alertmanager source review packet and debug packet handlers.

This module contains the GET handlers for Alertmanager source review packets,
debug packets, and promotion review.

Functions here accept the request handler instance as the first argument.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


def handle_alertmanager_sources_review_packet(
    handler: HealthUIRequestHandler, run_id: str
) -> None:
    """Generate and return the Alertmanager sources review packet.

    Route: GET /api/runs/{run_id}/alertmanager-sources/review-packet

    The review packet explains WHY K9B discovered multiple Alertmanager sources
    and whether they are genuinely distinct or service aliases pointing to the same backend.

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
    """
    # Load context for the specific run_id from the URL path
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

    # Get sources view
    sources_view = context.alertmanager_sources
    if sources_view is None:
        handler._send_json({"error": "Alertmanager sources not available"}, 400)
        return

    # Build review packet response directly
    sources_data: list[dict[str, Any]] = []
    for source in sources_view.sources:
        sources_data.append({
            "source_id": source.source_id,
            "name": source.name,
            "namespace": source.namespace,
            "endpoint": source.endpoint,
            "origin": source.origin,
            "state": source.state,
            "runtime": {
                "probe_attempted": False,
                "ready": getattr(source, "ready", False),
                "healthy": getattr(source, "healthy", False),
                "alertmanager_version": getattr(source, "verified_version", None),
            },
            "kubernetes": {
                "service_uid": getattr(source, "service_uid", None),
                "service_type": getattr(source, "service_type", None),
                "labels": getattr(source, "labels", {}),
                "annotations_redacted": getattr(source, "annotations_redacted", {}),
                "selector": getattr(source, "selector", {}),
                "ports": getattr(source, "ports", []),
                "owner_references": getattr(source, "owner_references", []),
            },
            "endpoint_info": {
                "endpoint_uid": getattr(source, "endpoint_uid", None),
                "addresses": getattr(source, "addresses", []),
                "not_ready_addresses": getattr(source, "not_ready_addresses", []),
                "ports": getattr(source, "endpoint_ports", []),
            },
            "duplicate_analysis": {
                "is_duplicate": False,
                "duplicate_of": None,
                "evidence": [],
                "action": "requires_manual_review",
                "explanation": "Individual source analysis required",
            },
            "discovered_at": getattr(source, "discovered_at", None),
        })

    # Build the response
    response = {
        "schema_version": "k9b.alertmanager_sources.review_packet.v1",
        "artifact_id": f"review-{context.run.run_id}",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": context.run.run_id,
        "cluster_label": sources_view.cluster_context or "unknown",
        "summary": {
            "total_sources": len(sources_data),
            "unique_logical_sources": len(sources_data),
            "duplicate_count": 0,
            "cluster_context": sources_view.cluster_context or "unknown",
            "discovery_run_id": context.run.run_id,
            "discovery_timestamp": datetime.now(UTC).isoformat(),
        },
        "sources": sources_data,
    }

    handler._send_json(response)


def handle_alertmanager_source_debug_packet(
    handler: HealthUIRequestHandler, run_id: str, source_key: str, *, probe_now: bool = False
) -> None:
    """Generate and return a debug packet for a single Alertmanager source.

    Route: GET /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet
    Route: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe (probe_now=true)

    The debug packet provides:
    - Probe now: Re-run runtime probes (/-/healthy, /-/ready, /api/v2/status)
    - Download JSON: Get the full debug packet as downloadable JSON
    - Why discovered?: Understand why this source was found

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
        source_key: The source key (URL-decoded source_id) from the URL path
        probe_now: If True, run a live probe instead of using cached data
    """
    from urllib.parse import unquote

    # Decode URL-encoded source_id
    source_key = unquote(source_key)

    # Load context
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

    # Find the source
    sources_view = context.alertmanager_sources
    if sources_view is None:
        handler._send_json({"error": "Alertmanager sources not available"}, 400)
        return

    source_view = None
    for s in sources_view.sources:
        if s.source_id == source_key:
            source_view = s
            break

    if source_view is None:
        handler._send_json({"error": f"Source not found: {source_key}"}, 404)
        return

    # Build http_probes structure - populate from live probe if requested
    http_probes: dict[str, dict[str, Any]] = {
        "healthy": {"url": f"{source_view.endpoint}/-/healthy", "status_code": None, "latency_ms": None, "error": None},
        "ready": {"url": f"{source_view.endpoint}/-/ready", "status_code": None, "latency_ms": None, "error": None},
        "status": {"url": f"{source_view.endpoint}/api/v2/status", "status_code": None, "latency_ms": None, "error": None},
    }

    # Wire probe_now to actual probe seam
    probe_result = None
    probe_error: str | None = None
    if probe_now:
        try:
            from ..external_analysis.alertmanager_source_probe import probe_alertmanager

            probe_result = probe_alertmanager(source_view.endpoint)
            # Populate http_probes with actual probe results
            # Correctly map: healthy probe to healthy key, ready probe to ready key
            http_probes["healthy"] = {
                "url": probe_result.healthy.url,
                "status_code": probe_result.healthy.status_code,
                "latency_ms": probe_result.healthy.latency_ms,
                "error": probe_result.healthy.error,
            }
            http_probes["ready"] = {
                "url": probe_result.ready.url,
                "status_code": probe_result.ready.status_code,
                "latency_ms": probe_result.ready.latency_ms,
                "error": probe_result.ready.error,
            }
            http_probes["status"] = {
                "url": probe_result.status.url,
                "status_code": probe_result.status.status_code,
                "latency_ms": probe_result.status.latency_ms,
                "error": probe_result.status.error,
            }
        except Exception as exc:  # noqa: BLE001
            # Preserve failure evidence rather than silently swallowing
            from ..security import sanitize_exception_message

            probe_error = sanitize_exception_message(exc)

    # Build response directly
    response: dict[str, Any] = {
        "schema_version": "k9b.alertmanager_source.debug_packet.v1",
        "artifact_id": f"debug-{source_key}-{context.run.run_id}",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": context.run.run_id,
        "cluster_label": sources_view.cluster_context or "unknown",
        "source_id": source_key,
        "name": source_view.name,
        "namespace": source_view.namespace,
        "endpoint": source_view.endpoint,
        "origin": source_view.origin,
        "state": source_view.state,
        "probe_attempted": probe_now,
        "probe_error": probe_error,  # Preserved failure evidence
        "http_probes": http_probes,
        "kubernetes": {
            "service": getattr(source_view, "service_data", {}),
            "endpoints": getattr(source_view, "endpoints_data", {}),
            "endpoint_slices": getattr(source_view, "endpoint_slices_data", []),
            "pods": getattr(source_view, "pods_data", []),
            "alertmanager_cr_matches": getattr(source_view, "cr_matches", []),
            "statefulset_matches": getattr(source_view, "statefulset_matches", []),
        },
        "discovery_reason": {
            "method": getattr(source_view, "discovery_method", "unknown"),
            "matched_pattern": getattr(source_view, "matched_pattern", None),
            "owner_reference_kind": getattr(source_view, "owner_reference_kind", None),
            "owner_reference_name": getattr(source_view, "owner_reference_name", None),
        },
    }

    # Add runtime identity fields from probe result if available
    if probe_result is not None:
        response["runtime_identity"] = {
            "endpoint": probe_result.endpoint,
            "probe_attempted": True,
            "healthy": probe_result.healthy.status_code == 200,  # Fixed: correct mapping
            "ready": probe_result.ready.status_code == 200,  # Fixed: correct mapping
            "is_healthy_and_ready": probe_result.is_healthy,
            "alertmanager_version": probe_result.version,
            "cluster_status": probe_result.cluster_status,
            "peer_count": probe_result.peer_count,
            "config_sha256": probe_result.config_sha256,
            "receiver_count": probe_result.receiver_count,
            "silence_count": probe_result.silence_count,
            "alert_group_count": probe_result.alert_group_count,
            "probed_at": probe_result.probed_at.isoformat(),
        }

    handler._send_json(response)


def handle_alertmanager_source_promotion_review(
    handler: HealthUIRequestHandler, run_id: str, source_key: str
) -> None:
    """Generate a pre-promotion review for an Alertmanager source.

    Route: GET /api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review

    The promotion review assesses the risk of promoting this source to manual,
    including checking for duplicate/manual sources that might conflict.

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
        source_key: The source key (URL-decoded source_id) from the URL path
    """
    from urllib.parse import unquote

    # Decode URL-encoded source_id
    source_key = unquote(source_key)

    # Load context
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

    # Find the source
    sources_view = context.alertmanager_sources
    if sources_view is None:
        handler._send_json({"error": "Alertmanager sources not available"}, 400)
        return

    source_view = None
    for s in sources_view.sources:
        if s.source_id == source_key:
            source_view = s
            break

    if source_view is None:
        handler._send_json({"error": f"Source not found: {source_key}"}, 404)
        return

    # Build response directly
    response: dict[str, Any] = {
        "schema_version": "k9b.alertmanager_source.promotion_review.v1",
        "artifact_id": f"promotion-review-{source_key}-{context.run.run_id}",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": context.run.run_id,
        "cluster_label": sources_view.cluster_context or "unknown",
        "source_id": source_key,
        "name": source_view.name,
        "namespace": source_view.namespace,
        "endpoint": source_view.endpoint,
        "promotion_target": "manual",
    }

    # Check for duplicate manual sources
    duplicate_manual = None
    if not source_view.is_manual:
        for s in sources_view.sources:
            if s.source_id != source_key and s.is_manual:
                if s.endpoint == source_view.endpoint:
                    duplicate_manual = s
                    break

    if duplicate_manual:
        response["risk"] = {
            "risk_level": "medium",
            "duplicate_risk": f"Endpoint {source_view.endpoint} already tracked by manual source {duplicate_manual.source_id}",
            "existing_manual_source": duplicate_manual.source_id,
        }
        response["tracked_source_if_duplicate"] = {
            "source_id": duplicate_manual.source_id,
            "endpoint": duplicate_manual.endpoint,
            "namespace": duplicate_manual.namespace,
            "name": duplicate_manual.name,
            "origin": duplicate_manual.origin,
            "state": duplicate_manual.state,
        }
    else:
        response["risk"] = {
            "risk_level": "low",
            "duplicate_risk": None,
            "existing_manual_source": None,
        }
        response["tracked_source_if_duplicate"] = None

    handler._send_json(response)

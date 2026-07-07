"""Alertmanager source review packet and debug packet handlers.

This module contains the GET handlers for Alertmanager source review packets,
debug packets, and promotion review.

Functions here accept the request handler instance as the first argument.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.

CANONICAL WIRE SCHEMA:
- k9b.alertmanager_sources.review_packet.v1
- k9b.alertmanager_source.debug_packet.v1
- k9b.alertmanager_source.promotion_review.v1

All handlers produce responses conforming to these schemas using canonical
dataclass to_dict() methods from external_analysis modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


def _find_likely_aliases(
    source_view: Any, sources_view: Any, source_key: str
) -> list[tuple[str, str]]:
    """Find likely aliases based on runtime identity signals."""
    likely_aliases: list[tuple[str, str]] = []
    source_config_hash = getattr(source_view, "config_sha256", None)
    source_version = getattr(source_view, "verified_version", None)
    source_cluster_status = getattr(source_view, "cluster_status", None)
    source_peer_count = getattr(source_view, "peer_count", 0)

    for s in sources_view.sources:
        if s.source_id == source_key or s.is_manual:
            continue
        alias_reasons: list[str] = []
        other_config_hash = getattr(s, "config_sha256", None)
        other_version = getattr(s, "verified_version", None)
        other_cluster_status = getattr(s, "cluster_status", None)
        other_peer_count = getattr(s, "peer_count", 0)

        if source_config_hash and other_config_hash and source_config_hash == other_config_hash:
            alias_reasons.append("same config hash")
        if source_version and other_version and source_version == other_version:
            alias_reasons.append("same version")
        if source_cluster_status and other_cluster_status and source_cluster_status == other_cluster_status:
            alias_reasons.append("same cluster status")
        if source_peer_count > 0 and source_peer_count == other_peer_count:
            alias_reasons.append("same peer count")

        if len(alias_reasons) >= 2:
            likely_aliases.append((s.source_id, f"likely alias: {', '.join(alias_reasons)}"))

    return likely_aliases


def _find_duplicate_manual(source_view: Any, sources_view: Any, source_key: str) -> Any:
    """Find a manual source that duplicates the given source's endpoint."""
    if source_view.is_manual:
        return None
    for s in sources_view.sources:
        if s.source_id != source_key and s.is_manual and s.endpoint == source_view.endpoint:
            return s
    return None


def handle_alertmanager_sources_review_packet(
    handler: HealthUIRequestHandler, run_id: str
) -> None:
    """Generate and return the Alertmanager sources review packet.

    Route: GET /api/runs/{run_id}/alertmanager-sources/review-packet

    The review packet explains WHY K9B discovered multiple Alertmanager sources
    and whether they are genuinely distinct or service aliases pointing to the same backend.

    Schema: k9b.alertmanager_sources.review_packet.v1

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
    """
    from ..external_analysis.alertmanager_sources_review_packet import (
        AlertmanagerSourcesReviewPacket,
        KubernetesIdentity,
        RuntimeIdentity,
        SourceEntry,
        Summary,
    )

    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

    sources_view = context.alertmanager_sources
    if sources_view is None:
        handler._send_json({"error": "Alertmanager sources not available"}, 400)
        return

    source_entries: list[SourceEntry] = []
    for source in sources_view.sources:
        runtime_identity = RuntimeIdentity(
            probe_attempted=getattr(source, "probe_attempted", False),
            ready=getattr(source, "ready", False),
            healthy=getattr(source, "healthy", False),
            alertmanager_version=getattr(source, "verified_version", None),
            cluster_status=getattr(source, "cluster_status", None),
            cluster_peer_count=getattr(source, "peer_count", 0),
            config_sha256=getattr(source, "config_sha256", None),
            receiver_count=getattr(source, "receiver_count", None),
            silence_count=getattr(source, "silence_count", None),
            alert_group_count=getattr(source, "alert_group_count", None),
        )

        kubernetes_identity = KubernetesIdentity(
            service_uid=getattr(source, "service_uid", None),
            service_type=getattr(source, "service_type", None),
            labels=getattr(source, "labels", {}),
            annotations_redacted=getattr(source, "annotations_redacted", {}),
            selector=getattr(source, "selector", {}),
            ports=list(getattr(source, "ports", [])),
            owner_references=list(getattr(source, "owner_references", [])),
        )

        from ..external_analysis.alertmanager_sources_review_packet import EndpointIdentity

        endpoint_identity = EndpointIdentity(
            endpoint_slices=list(getattr(source, "endpoint_slices", [])),
            target_pod_uids=list(getattr(source, "target_pod_uids", [])),
            target_pod_names=list(getattr(source, "target_pod_names", [])),
            target_owner_refs=list(getattr(source, "target_owner_refs", [])),
        )

        source_entry = SourceEntry(
            source_id=source.source_id,
            state=source.state,
            origin=source.origin,
            provenance=getattr(source, "provenance", source.origin),
            namespace=source.namespace,
            service_name=source.name,
            endpoint_url=source.endpoint,
            cluster=source.cluster_label,
            kubernetes_identity=kubernetes_identity,
            endpoint_identity=endpoint_identity,
            runtime_identity=runtime_identity,
        )
        source_entries.append(source_entry)

    summary = Summary(
        total=len(source_entries),
        tracked=sum(1 for s in sources_view.sources if s.is_tracking),
        manual=sources_view.manual_count,
        degraded=sources_view.degraded_count,
        missing=sources_view.missing_count,
        duplicate_groups=0,
    )

    packet = AlertmanagerSourcesReviewPacket(sources=tuple(source_entries), summary=summary)
    response = packet.to_dict()
    response["run_id"] = context.run.run_id
    response["cluster_label"] = sources_view.cluster_context or "unknown"
    response["summary"]["cluster_context"] = sources_view.cluster_context or "unknown"
    response["summary"]["discovery_run_id"] = context.run.run_id
    response["summary"]["discovery_timestamp"] = datetime.now(UTC).isoformat()

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

    Schema: k9b.alertmanager_source.debug_packet.v1

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
        source_key: The source key (URL-decoded source_id) from the URL path
        probe_now: If True, run a live probe instead of using cached data
    """
    from urllib.parse import unquote

    from ..external_analysis.alertmanager_source_debug_packet import (
        AlertmanagerSourceDebugPacket,
        DiscoveryReason,
        HttpProbeResult,
        HttpProbeResults,
        KubernetesProbeData,
    )
    from ..external_analysis.alertmanager_source_probe import probe_alertmanager

    source_key = unquote(source_key)
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

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

    probe_result = None
    probe_error: str | None = None
    http_probes: HttpProbeResults

    if probe_now:
        try:
            probe_result = probe_alertmanager(source_view.endpoint)
            http_probes = HttpProbeResults(
                healthy=probe_result.healthy, ready=probe_result.ready, status=probe_result.status
            )
        except Exception as exc:  # noqa: BLE001
            from ..security import sanitize_exception_message

            probe_error = sanitize_exception_message(exc)
            http_probes = HttpProbeResults(
                healthy=HttpProbeResult(
                    url=f"{source_view.endpoint}/-/healthy", status_code=None, latency_ms=None, error=probe_error
                ),
                ready=HttpProbeResult(
                    url=f"{source_view.endpoint}/-/ready", status_code=None, latency_ms=None, error=probe_error
                ),
                status=HttpProbeResult(
                    url=f"{source_view.endpoint}/api/v2/status", status_code=None, latency_ms=None, error=probe_error
                ),
            )
    else:
        http_probes = HttpProbeResults(
            healthy=HttpProbeResult(url=f"{source_view.endpoint}/-/healthy"),
            ready=HttpProbeResult(url=f"{source_view.endpoint}/-/ready"),
            status=HttpProbeResult(url=f"{source_view.endpoint}/api/v2/status"),
        )

    discovery_reason = DiscoveryReason(
        matched_heuristic=getattr(source_view, "discovery_method", None),
        matched_fields=list(getattr(source_view, "matched_fields", [])),
        confidence="unknown",
    )

    kubernetes_probe = KubernetesProbeData(
        service=dict(getattr(source_view, "service_data", {})),
        endpoints=dict(getattr(source_view, "endpoints_data", {})),
        endpoint_slices=list(getattr(source_view, "endpoint_slices_data", [])),
        pods=list(getattr(source_view, "pods_data", [])),
        alertmanager_cr_matches=list(getattr(source_view, "cr_matches", [])),
        statefulset_matches=list(getattr(source_view, "statefulset_matches", [])),
    )

    errors: list[str] = []
    if probe_error:
        errors.append(probe_error)

    packet = AlertmanagerSourceDebugPacket(
        source_id=source_key,
        discovery_reason=discovery_reason,
        kubernetes_probe=kubernetes_probe,
        http_probe=http_probes,
        errors=errors,
    )

    response = packet.to_dict()
    response["run_id"] = context.run.run_id
    response["cluster_label"] = sources_view.cluster_context or "unknown"
    response["name"] = source_view.name
    response["namespace"] = source_view.namespace
    response["endpoint"] = source_view.endpoint
    response["origin"] = source_view.origin
    response["state"] = source_view.state
    response["probe_attempted"] = probe_now
    response["probe_error"] = probe_error

    if probe_result is not None:
        response["runtime_identity"] = {
            "endpoint": probe_result.endpoint,
            "probe_attempted": True,
            "healthy": probe_result.healthy.status_code == 200,
            "ready": probe_result.ready.status_code == 200,
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

    Schema: k9b.alertmanager_source.promotion_review.v1

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
        source_key: The source key (URL-decoded source_id) from the URL path
    """
    from urllib.parse import unquote

    from ..external_analysis.alertmanager_source_promotion_review import (
        AlertmanagerSourcePromotionReview,
        PromotionRisk,
        TrackedSourceSpec,
    )

    source_key = unquote(source_key)
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return

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

    # Check for duplicate manual sources
    duplicate_manual = _find_duplicate_manual(source_view, sources_view, source_key)

    # Check for likely aliases based on runtime identity
    likely_aliases = _find_likely_aliases(source_view, sources_view, source_key)

    # Determine if promotable based on source state
    promotable = not source_view.is_manual and source_view.state in ("auto-tracked", "discovered")

    # Compute identity_hash from runtime identity if available
    source_config_hash = getattr(source_view, "config_sha256", None)
    source_version = getattr(source_view, "verified_version", None)
    source_cluster_status = getattr(source_view, "cluster_status", None)
    source_peer_count = getattr(source_view, "peer_count", 0)

    identity_hash = source_config_hash or (
        f"{source_version}:{source_cluster_status}:{source_peer_count}" if source_version else None
    )

    will_create: TrackedSourceSpec | None = None
    if promotable:
        will_create = TrackedSourceSpec(
            endpoint_url=source_view.endpoint,
            identity_hash=identity_hash,
            cluster=sources_view.cluster_context,
            namespace=source_view.namespace,
            name=source_view.name,
        )

    # Build risks based on duplicate detection
    risks: list[PromotionRisk] = []
    if duplicate_manual:
        risks.append(
            PromotionRisk(
                risk_id="duplicate_tracking",
                severity="warning",
                description=f"Endpoint {source_view.endpoint} already tracked by manual source {duplicate_manual.source_id}",
                mitigation=f"Consider disabling or promoting {duplicate_manual.source_id} instead",
            )
        )
    elif likely_aliases:
        alias_info = "; ".join([f"{sid} ({reason})" for sid, reason in likely_aliases])
        risks.append(
            PromotionRisk(
                risk_id="duplicate_tracking_or_alias_risk",
                severity="warning",
                description=f"Other discovered sources share same Alertmanager cluster identity: {alias_info}",
                mitigation="Consider collapsing as aliases or promoting the canonical source instead",
            )
        )
    elif identity_hash is None:
        risks.append(
            PromotionRisk(
                risk_id="insufficient_identity_evidence",
                severity="info",
                description="No runtime probe data available. Unable to verify cluster identity.",
                mitigation="Run probe to gather runtime identity before promoting",
            )
        )
    else:
        risks.append(
            PromotionRisk(
                risk_id="no_conflicts",
                severity="info",
                description="No duplicate manual sources found and no likely aliases detected",
                mitigation=None,
            )
        )

    packet = AlertmanagerSourcePromotionReview(
        source_id=source_key,
        promotable=promotable,
        will_create=will_create,
        aliases=(),
        risks=tuple(risks),
    )

    response = packet.to_dict()
    response["run_id"] = context.run.run_id
    response["cluster_label"] = sources_view.cluster_context or "unknown"
    response["name"] = source_view.name
    response["namespace"] = source_view.namespace
    response["endpoint"] = source_view.endpoint
    response["promotion_target"] = "manual"

    if duplicate_manual:
        response["tracked_source_if_duplicate"] = {
            "source_id": duplicate_manual.source_id,
            "endpoint": duplicate_manual.endpoint,
            "namespace": duplicate_manual.namespace,
            "name": duplicate_manual.name,
            "origin": duplicate_manual.origin,
            "state": duplicate_manual.state,
        }
    else:
        response["tracked_source_if_duplicate"] = None

    handler._send_json(response)

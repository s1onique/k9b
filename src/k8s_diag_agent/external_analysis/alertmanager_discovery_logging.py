"""Structured logging for Alertmanager sources discovery.

This module provides structured log events for Alertmanager source discovery,
enabling backend logs to reconstruct the sources table without UI screenshots.

Log format:
    alertmanager.discovery.<event_name> [key=value]...

Events:
- run_started: Discovery run has begun
- service_candidate_found: A potential Alertmanager service was found
- endpoints_resolved: EndpointSlice/pod resolution completed
- runtime_probe_ok: HTTP probe to Alertmanager succeeded
- identity_grouped: Sources grouped as aliases
- run_finished: Discovery run completed

Example log lines:
    alertmanager.discovery.run_started run_id=abc123 context=in-cluster
    alertmanager.discovery.service_candidate_found run_id=abc123 source_id=monitoring/alertmanager-main namespace=monitoring service=alertmanager-operated
    alertmanager.discovery.endpoints_resolved run_id=abc123 source_id=monitoring/alertmanager-main pod_uids=[pod-uid-1,pod-uid-2]
    alertmanager.discovery.runtime_probe_ok run_id=abc123 source_id=monitoring/alertmanager-main ready=true healthy=true version=0.27.1 config_sha256=abc123
    alertmanager.discovery.identity_grouped run_id=abc123 group_id=group-1 source_ids=[source-1,source-2] reason=same_target_pods_same_config
    alertmanager.discovery.run_finished run_id=abc123 total=2 duplicate_groups=1 degraded=0
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Module logger
_logger = logging.getLogger(__name__)


# Component name for structured logs
COMPONENT = "alertmanager-discovery"


def log_run_started(
    run_id: str,
    context: str = "in-cluster",
    cluster_context: str | None = None,
) -> None:
    """Log that an Alertmanager discovery run has started.
    
    Args:
        run_id: Unique identifier for this discovery run
        context: Discovery context ("in-cluster", "external")
        cluster_context: Kubernetes context being used for discovery
    """
    _logger.info(
        "alertmanager.discovery.run_started run_id=%s context=%s",
        run_id,
        context,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.run_started",
            "run_id": run_id,
            "context": context,
            "cluster_context": cluster_context,
        },
    )


def log_service_candidate_found(
    run_id: str,
    source_id: str,
    namespace: str,
    service: str,
    origin: str,
) -> None:
    """Log that a potential Alertmanager service candidate was found.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Canonical source identifier
        namespace: Kubernetes namespace
        service: Service name
        origin: Discovery origin (alertmanager-crd, service-heuristic, etc.)
    """
    _logger.debug(
        "alertmanager.discovery.service_candidate_found run_id=%s source_id=%s namespace=%s service=%s",
        run_id,
        source_id,
        namespace,
        service,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.service_candidate_found",
            "run_id": run_id,
            "source_id": source_id,
            "namespace": namespace,
            "service": service,
            "origin": origin,
        },
    )


def log_endpoints_resolved(
    run_id: str,
    source_id: str,
    pod_uids: list[str],
    endpoint_slices: list[str] | None = None,
) -> None:
    """Log that endpoint resolution completed for a source.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Canonical source identifier
        pod_uids: List of backing pod UIDs
        endpoint_slices: List of EndpointSlice names
    """
    _logger.debug(
        "alertmanager.discovery.endpoints_resolved run_id=%s source_id=%s pod_uids=%s",
        run_id,
        source_id,
        json.dumps(pod_uids),
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.endpoints_resolved",
            "run_id": run_id,
            "source_id": source_id,
            "pod_uids": pod_uids,
            "endpoint_slices": endpoint_slices or [],
        },
    )


def log_runtime_probe_ok(
    run_id: str,
    source_id: str,
    ready: bool,
    healthy: bool,
    version: str | None = None,
    config_sha256: str | None = None,
    cluster_status: str | None = None,
    peer_count: int = 0,
) -> None:
    """Log that an HTTP probe to Alertmanager succeeded.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Canonical source identifier
        ready: Whether /-/ready returned success
        healthy: Whether /-/healthy returned success
        version: Alertmanager version from /api/v2/status
        config_sha256: SHA256 hash of config
        cluster_status: Cluster status from /api/v2/status
        peer_count: Number of peers in cluster
    """
    _logger.debug(
        "alertmanager.discovery.runtime_probe_ok run_id=%s source_id=%s ready=%s healthy=%s version=%s",
        run_id,
        source_id,
        ready,
        healthy,
        version,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.runtime_probe_ok",
            "run_id": run_id,
            "source_id": source_id,
            "ready": ready,
            "healthy": healthy,
            "version": version,
            "config_sha256": config_sha256,
            "cluster_status": cluster_status,
            "peer_count": peer_count,
        },
    )


def log_runtime_probe_failed(
    run_id: str,
    source_id: str,
    error: str,
    endpoint: str | None = None,
) -> None:
    """Log that an HTTP probe to Alertmanager failed.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Canonical source identifier
        error: Error message
        endpoint: Endpoint that failed
    """
    _logger.warning(
        "alertmanager.discovery.runtime_probe_failed run_id=%s source_id=%s error=%s",
        run_id,
        source_id,
        error,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.runtime_probe_failed",
            "run_id": run_id,
            "source_id": source_id,
            "error": error,
            "endpoint": endpoint,
        },
    )


def log_identity_grouped(
    run_id: str,
    group_id: str,
    source_ids: list[str],
    reason: str,
    same_target_pods: bool = False,
    same_config: bool = False,
    same_cluster: bool = False,
) -> None:
    """Log that sources were grouped as aliases.
    
    Args:
        run_id: Unique identifier for this discovery run
        group_id: Group identifier
        source_ids: List of source IDs in the group
        reason: Grouping reason
        same_target_pods: Whether sources share same target pods
        same_config: Whether sources have same config hash
        same_cluster: Whether sources are in same cluster
    """
    _logger.info(
        "alertmanager.discovery.identity_grouped run_id=%s group_id=%s source_ids=%s reason=%s",
        run_id,
        group_id,
        json.dumps(source_ids),
        reason,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.identity_grouped",
            "run_id": run_id,
            "group_id": group_id,
            "source_ids": source_ids,
            "reason": reason,
            "same_target_pods": same_target_pods,
            "same_config": same_config,
            "same_cluster": same_cluster,
        },
    )


def log_run_finished(
    run_id: str,
    total: int,
    duplicate_groups: int,
    degraded: int,
    tracked: int = 0,
    manual: int = 0,
    missing: int = 0,
) -> None:
    """Log that an Alertmanager discovery run has finished.
    
    Args:
        run_id: Unique identifier for this discovery run
        total: Total number of sources discovered
        duplicate_groups: Number of duplicate groups found
        degraded: Number of degraded sources
        tracked: Number of auto-tracked sources
        manual: Number of manual sources
        missing: Number of missing sources
    """
    _logger.info(
        "alertmanager.discovery.run_finished run_id=%s total=%s duplicate_groups=%s degraded=%s",
        run_id,
        total,
        duplicate_groups,
        degraded,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.run_finished",
            "run_id": run_id,
            "total": total,
            "duplicate_groups": duplicate_groups,
            "degraded": degraded,
            "tracked": tracked,
            "manual": manual,
            "missing": missing,
        },
    )


def log_review_packet_generated(
    run_id: str,
    artifact_id: str,
    source_count: int,
    duplicate_groups: int,
) -> None:
    """Log that a review packet was generated.
    
    Args:
        run_id: Unique identifier for this discovery run
        artifact_id: Artifact ID of the generated packet
        source_count: Number of sources in the packet
        duplicate_groups: Number of duplicate groups in the packet
    """
    _logger.info(
        "alertmanager.discovery.review_packet_generated run_id=%s artifact_id=%s source_count=%s duplicate_groups=%s",
        run_id,
        artifact_id,
        source_count,
        duplicate_groups,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.review_packet_generated",
            "run_id": run_id,
            "artifact_id": artifact_id,
            "source_count": source_count,
            "duplicate_groups": duplicate_groups,
        },
    )


def log_debug_packet_generated(
    run_id: str,
    source_id: str,
    artifact_id: str,
) -> None:
    """Log that a debug packet was generated.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Source ID for the debug packet
        artifact_id: Artifact ID of the generated packet
    """
    _logger.debug(
        "alertmanager.discovery.debug_packet_generated run_id=%s source_id=%s artifact_id=%s",
        run_id,
        source_id,
        artifact_id,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.debug_packet_generated",
            "run_id": run_id,
            "source_id": source_id,
            "artifact_id": artifact_id,
        },
    )


def log_promotion_review_generated(
    run_id: str,
    source_id: str,
    artifact_id: str,
    promotable: bool,
    alias_count: int,
) -> None:
    """Log that a promotion review packet was generated.
    
    Args:
        run_id: Unique identifier for this discovery run
        source_id: Source ID for the promotion review
        artifact_id: Artifact ID of the generated packet
        promotable: Whether the source is promotable
        alias_count: Number of aliases that would be affected
    """
    _logger.info(
        "alertmanager.discovery.promotion_review_generated run_id=%s source_id=%s promotable=%s alias_count=%s",
        run_id,
        source_id,
        promotable,
        alias_count,
        extra={
            "component": COMPONENT,
            "event": "alertmanager.discovery.promotion_review_generated",
            "run_id": run_id,
            "source_id": source_id,
            "artifact_id": artifact_id,
            "promotable": promotable,
            "alias_count": alias_count,
        },
    )


__all__ = [
    "COMPONENT",
    "log_run_started",
    "log_service_candidate_found",
    "log_endpoints_resolved",
    "log_runtime_probe_ok",
    "log_runtime_probe_failed",
    "log_identity_grouped",
    "log_run_finished",
    "log_review_packet_generated",
    "log_debug_packet_generated",
    "log_promotion_review_generated",
]

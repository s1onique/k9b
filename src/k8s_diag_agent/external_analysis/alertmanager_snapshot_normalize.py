"""Normalization logic for Alertmanager payload processing.

This module contains:
- Payload parsing and coercion
- Timestamp/label/annotation normalization
- State extraction helpers
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..identity.artifact import new_artifact_id
from .alertmanager_snapshot_contract import (
    SENSITIVE_KEY_PATTERNS,
    AlertmanagerCompact,
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    ClusterAlertSummary,
    NormalizedAlert,
)


def _truncate_string(s: str | None, max_len: int) -> str | None:
    """Truncate string to max length."""
    if s is None:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _compute_deterministic_fingerprint(labels_sorted: tuple[tuple[str, str], ...]) -> str:
    """Compute deterministic fingerprint from sorted labels tuple using MD5.
    
    This is the single source of truth for deterministic synthetic fingerprint generation.
    Used when Alertmanager does not provide an explicit fingerprint.
    """
    raw = json.dumps(dict(labels_sorted), sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:32]


def _is_sensitive_key(key: str) -> bool:
    """Check if an annotation key is sensitive and should be redacted.
    
    Redacts keys containing patterns like password, secret, token, etc.
    to prevent leaking credentials through alert artifacts.
    """
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_KEY_PATTERNS)


def _extract_state(alert_raw: Mapping[str, Any], labels_raw: Mapping[str, Any], max_len: int) -> str:
    """Extract alert state with robust precedence handling.
    
    Precedence:
    1. alert_raw["status"]["state"] if status is a mapping
    2. alert_raw["status"] if it is a string
    3. alert_raw["state"] if present
    4. labels_raw["state"] as fallback
    5. "inactive" as deterministic default
    """
    # 1. Check nested status.state (if status is a mapping)
    status = alert_raw.get("status")
    if isinstance(status, Mapping) and "state" in status:
        state_val = status.get("state")
        if isinstance(state_val, str):
            return _truncate_string(state_val, max_len) or "inactive"
    
    # 2. Check string status
    if isinstance(status, str):
        return _truncate_string(status, max_len) or "inactive"
    
    # 3. Check top-level state field
    state = alert_raw.get("state")
    if isinstance(state, str) and state:
        return _truncate_string(state, max_len) or "inactive"
    
    # 4. Check labels state
    label_state = labels_raw.get("state")
    if isinstance(label_state, str) and label_state:
        return _truncate_string(label_state, max_len) or "inactive"
    
    # 5. Deterministic fallback
    return "inactive"


def _extract_receiver(alert_raw: Mapping[str, Any]) -> str | None:
    """Extract receiver name from alert.
    
    Handles both:
    - Scalar receiver field (from webhook payloads): alert_raw["receiver"]
    - Array receivers field (from /api/v2/alerts): alert_raw["receivers"]
    
    Returns the first receiver name deterministically, or None if not present.
    """
    # First check scalar receiver (from webhook payloads)
    receiver = alert_raw.get("receiver")
    if isinstance(receiver, str) and receiver:
        return receiver
    
    # Then check receivers array (from /api/v2/alerts API)
    receivers = alert_raw.get("receivers")
    if isinstance(receivers, (list, tuple)) and receivers:
        # Receivers can be strings or dicts with "name" field
        first = receivers[0]
        if isinstance(first, str):
            return first
        if isinstance(first, Mapping):
            name = first.get("name")
            if isinstance(name, str) and name:
                return name
    
    return None


def _normalize_alert(
    alert_raw: Mapping[str, Any],
    labels_raw: Mapping[str, Any],
    config_max_string_length: int,
) -> NormalizedAlert:
    """Normalize a single alert from raw Alertmanager payload."""
    labels_sorted = tuple(sorted(
        (str(k), str(v)) for k, v in labels_raw.items()
    ))
    # Use deterministic MD5 fingerprint if not provided
    fingerprint = _truncate_string(labels_raw.get("fingerprint"), 64)
    if not fingerprint:
        fingerprint = _compute_deterministic_fingerprint(labels_sorted)
    
    # Extract full annotations (ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1)
    annotations_raw = alert_raw.get("annotations", {})
    annotations_sorted: tuple[tuple[str, str], ...] = ()
    if isinstance(annotations_raw, Mapping):
        # Bound annotations to prevent unbounded growth
        annotations_list: list[tuple[str, str]] = []
        for k, v in sorted(annotations_raw.items()):
            k_str = str(k)
            v_str = str(v)
            # Skip empty keys and secret-like values
            if not k_str:
                continue
            if _is_sensitive_key(k_str):
                v_str = "[REDACTED]"
            # Bound value length
            if len(v_str) > config_max_string_length:
                v_str = v_str[:config_max_string_length - 3] + "..."
            annotations_list.append((k_str, v_str))
        annotations_sorted = tuple(annotations_list)
    
    return NormalizedAlert(
        fingerprint=fingerprint,
        alertname=_truncate_string(labels_raw.get("alertname"), config_max_string_length) or "unknown",
        state=_extract_state(alert_raw, labels_raw, config_max_string_length),
        severity=_truncate_string(labels_raw.get("severity"), config_max_string_length) or "info",
        cluster=labels_raw.get("cluster"),
        namespace=labels_raw.get("namespace"),
        service=labels_raw.get("service"),
        instance=labels_raw.get("instance"),
        starts_at=alert_raw.get("startsAt") or alert_raw.get("starts_at"),
        summary=_truncate_string(
            annotations_raw.get("summary", labels_raw.get("summary")) 
            if isinstance(annotations_raw, Mapping) 
            else labels_raw.get("summary"), 
            config_max_string_length
        ),
        labels=labels_sorted,
        # Extended fields (ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1)
        annotations=annotations_sorted,
        generator_url=_truncate_string(
            alert_raw.get("generatorURL") or alert_raw.get("generator_url"), 
            512
        ),
        ends_at=alert_raw.get("endsAt") or alert_raw.get("ends_at"),
        updated_at=alert_raw.get("updatedAt") or alert_raw.get("updated_at"),
        receiver=_extract_receiver(alert_raw),  # Handles both scalar and array format
    )


def normalize_alertmanager_payload(
    raw: Any,
    config_max_alerts: int = 200,
    config_max_string_length: int = 200,
    source: str | None = None,
) -> AlertmanagerSnapshot:
    """Normalize raw Alertmanager API response into snapshot.
    
    Handles two Alertmanager API response formats:
    1. Top-level list: [{"labels": {...}, ...}, ...]  (direct from /api/v2/alerts)
    2. Wrapped format: {"data": {"alerts": [...]}}  (some proxy responses)
    
    Args:
        raw: Raw API response from Alertmanager.
        config_max_alerts: Maximum number of alerts to include in snapshot.
        config_max_string_length: Maximum length for string fields.
        source: Source endpoint URL (optional, for provenance tracking).
    """
    captured_at = datetime.now(UTC).isoformat()
    if raw is None:
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=source,
            alert_count=0,
            alerts=(),
            errors=("Received null/empty response",),
        )
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return AlertmanagerSnapshot(
                status=AlertmanagerStatus.INVALID_RESPONSE,
                captured_at=captured_at,
                source=source,
                alert_count=0,
                alerts=(),
                errors=(f"Failed to parse JSON: {raw[:200]}",),
            )
    
    # Handle top-level list format (Alertmanager API v2 returns list directly)
    if isinstance(raw, list):
        alerts_raw: Any = raw
    elif isinstance(raw, Mapping):
        # Try to extract from nested data structure
        data = raw.get("data")
        if isinstance(data, Mapping):
            alerts_raw = data.get("alerts")
        else:
            alerts_raw = raw.get("alerts")
        if alerts_raw is None:
            alerts_raw = []
    else:
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=source,
            alert_count=0,
            alerts=(),
            errors=(f"Expected list or dict response, got {type(raw).__name__}",),
        )
    
    if not isinstance(alerts_raw, list):
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=source,
            alert_count=0,
            alerts=(),
            errors=("Alerts field is not a list",),
        )
    
    total_count = len(alerts_raw)
    truncated = total_count > config_max_alerts
    alerts_to_process = alerts_raw[:config_max_alerts]
    alerts: list[NormalizedAlert] = []
    for alert_raw in alerts_to_process:
        if not isinstance(alert_raw, Mapping):
            continue
        labels_raw = alert_raw.get("labels", {})
        if not isinstance(labels_raw, Mapping):
            labels_raw = {}
        alert = _normalize_alert(alert_raw, labels_raw, config_max_string_length)
        alerts.append(alert)
    
    status = AlertmanagerStatus.OK
    if not alerts:
        status = AlertmanagerStatus.EMPTY
    return AlertmanagerSnapshot(
        status=status,
        captured_at=captured_at,
        source=source,
        alert_count=total_count,
        alerts=tuple(alerts),
        errors=(),
        truncated=truncated,
    )


def snapshot_to_compact(
    snapshot: AlertmanagerSnapshot,
    max_alerts: int = 20,
    cluster_label: str | None = None,
) -> AlertmanagerCompact:
    """Convert normalized snapshot to compact LLM-ready JSON.
    
    Args:
        snapshot: The normalized Alertmanager snapshot.
        max_alerts: Maximum number of top alerts to include.
        cluster_label: Optional cluster label (context/label) from the source
                       for cluster attribution when alerts lack cluster labels.
                       This is the cluster_label field used for per-cluster UI filtering.
    """
    severity_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    alert_names: dict[str, int] = {}
    namespaces: set[str] = set()
    clusters: set[str] = set()
    services: set[str] = set()
    # Per-cluster aggregation for cluster-scoped UI panels
    cluster_data: dict[str, dict[str, Any]] = {}
    
    for alert in snapshot.alerts:
        sev = alert.severity or "unknown"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        state = alert.state or "unknown"
        state_counts[state] = state_counts.get(state, 0) + 1
        name = alert.alertname or "unknown"
        alert_names[name] = alert_names.get(name, 0) + 1
        if alert.namespace:
            namespaces.add(alert.namespace)
        # Use cluster label from alert, fallback to cluster_label for provenance
        # when alerts lack cluster labels (e.g., alerts from a single Alertmanager instance
        # that doesn't emit cluster labels but runs in a known cluster context)
        cluster = alert.cluster or cluster_label or "_none_"
        clusters.add(cluster)
        if alert.service:
            services.add(alert.service)
        
        # Per-cluster aggregation
        if cluster not in cluster_data:
            cluster_data[cluster] = {
                "alert_count": 0,
                "severity_counts": {},
                "state_counts": {},
                "alert_names": {},
                "namespaces": set(),
                "services": set(),
            }
        cd = cluster_data[cluster]
        cd["alert_count"] += 1
        cd["severity_counts"][sev] = cd["severity_counts"].get(sev, 0) + 1
        cd["state_counts"][state] = cd["state_counts"].get(state, 0) + 1
        cd["alert_names"][name] = cd["alert_names"].get(name, 0) + 1
        if alert.namespace:
            cd["namespaces"].add(alert.namespace)
        if alert.service:
            cd["services"].add(alert.service)
    
    # Build per-cluster summaries
    by_cluster: list[ClusterAlertSummary] = []
    for cluster, cd in sorted(cluster_data.items()):
        if cluster == "_none_":
            continue  # Skip alerts without cluster label in by_cluster
        top_cluster_alerts = sorted(cd["alert_names"].items(), key=lambda x: (-x[1], x[0]))[:max_alerts]
        by_cluster.append(ClusterAlertSummary(
            cluster=cluster,
            alert_count=cd["alert_count"],
            severity_counts=tuple(sorted(cd["severity_counts"].items())),
            state_counts=tuple(sorted(cd["state_counts"].items())),
            top_alert_names=tuple(name for name, _ in top_cluster_alerts),
            affected_namespaces=tuple(sorted(cd["namespaces"]))[:max_alerts],
            affected_services=tuple(sorted(cd["services"]))[:max_alerts],
        ))
    
    top_alerts = sorted(alert_names.items(), key=lambda x: (-x[1], x[0]))[:max_alerts]
    top_alert_names = tuple(name for name, _ in top_alerts)
    affected_namespaces = tuple(sorted(namespaces))[:max_alerts]
    # Filter out "_none_" placeholder from affected_clusters for backward compatibility
    affected_clusters = tuple(sorted(c for c in clusters if c != "_none_"))[:max_alerts]
    affected_services = tuple(sorted(services))[:max_alerts]
    return AlertmanagerCompact(
        status=snapshot.status.value,
        alert_count=snapshot.alert_count,
        severity_counts=tuple(sorted(severity_counts.items())),
        state_counts=tuple(sorted(state_counts.items())),
        top_alert_names=top_alert_names,
        affected_namespaces=affected_namespaces,
        affected_clusters=affected_clusters,
        affected_services=affected_services,
        truncated=snapshot.truncated,
        captured_at=snapshot.captured_at,
        by_cluster=tuple(by_cluster),
        # Compact gets its own artifact_id - it is a separate artifact instance
        artifact_id=new_artifact_id(),
    )


def create_error_snapshot(
    status: AlertmanagerStatus,
    error: str,
    source: str | None = None,
) -> AlertmanagerSnapshot:
    """Create an error snapshot for non-ok paths."""
    return AlertmanagerSnapshot(
        status=status,
        captured_at=datetime.now(UTC).isoformat(),
        source=source,
        alert_count=0,
        alerts=(),
        errors=(error,),
        truncated=False,
    )

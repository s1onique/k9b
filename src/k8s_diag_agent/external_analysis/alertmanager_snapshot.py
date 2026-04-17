"""Normalized Alertmanager snapshot and compact summarizer for run artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AlertmanagerStatus(StrEnum):
    """Status values for Alertmanager snapshot."""
    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    UPSTREAM_ERROR = "upstream_error"
    DISABLED = "disabled"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class NormalizedAlert:
    """Normalized alert fields suitable for storage and debugging."""
    fingerprint: str
    alertname: str
    state: str
    severity: str
    cluster: str | None = None
    namespace: str | None = None
    service: str | None = None
    instance: str | None = None
    starts_at: str | None = None
    summary: str | None = None
    labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "fingerprint": self.fingerprint,
            "alertname": self.alertname,
            "state": self.state,
            "severity": self.severity,
        }
        if self.cluster is not None:
            result["cluster"] = self.cluster
        if self.namespace is not None:
            result["namespace"] = self.namespace
        if self.service is not None:
            result["service"] = self.service
        if self.instance is not None:
            result["instance"] = self.instance
        if self.starts_at is not None:
            result["starts_at"] = self.starts_at
        if self.summary is not None:
            result["summary"] = self.summary
        if self.labels:
            result["labels"] = {k: v for k, v in self.labels}
        return result


@dataclass(frozen=True)
class AlertmanagerSnapshot:
    """Normalized Alertmanager snapshot for run artifact storage."""
    status: AlertmanagerStatus
    captured_at: str
    source: str | None
    alert_count: int
    alerts: tuple[NormalizedAlert, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "captured_at": self.captured_at,
            "source": self.source,
            "alert_count": self.alert_count,
            "alerts": [alert.to_dict() for alert in self.alerts],
            "errors": list(self.errors),
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> AlertmanagerSnapshot:
        status_raw = str(raw.get("status") or AlertmanagerStatus.INVALID_RESPONSE.value)
        try:
            status = AlertmanagerStatus(status_raw)
        except ValueError:
            status = AlertmanagerStatus.INVALID_RESPONSE
        captured_at = str(raw.get("captured_at") or datetime.now(UTC).isoformat())
        source = str(raw.get("source")) if raw.get("source") else None
        alert_count = int(raw.get("alert_count") or 0)
        alerts_raw = raw.get("alerts") or []
        alerts: list[NormalizedAlert] = []
        if isinstance(alerts_raw, list):
            for alert_raw in alerts_raw:
                if isinstance(alert_raw, Mapping):
                    fingerprint = str(alert_raw.get("fingerprint", ""))
                    alertname = str(alert_raw.get("alertname", "unknown"))
                    state = str(alert_raw.get("state", ""))
                    severity = str(alert_raw.get("severity", ""))
                    labels_raw = alert_raw.get("labels")
                    labels: list[tuple[str, str]] = []
                    if isinstance(labels_raw, dict):
                        labels = [(k, str(v)) for k, v in sorted(labels_raw.items())]
                    alerts.append(NormalizedAlert(
                        fingerprint=fingerprint,
                        alertname=alertname,
                        state=state,
                        severity=severity,
                        cluster=alert_raw.get("cluster"),
                        namespace=alert_raw.get("namespace"),
                        service=alert_raw.get("service"),
                        instance=alert_raw.get("instance"),
                        starts_at=alert_raw.get("starts_at"),
                        summary=alert_raw.get("summary"),
                        labels=tuple(labels),
                    ))
        errors_raw = raw.get("errors") or []
        errors: list[str] = []
        if isinstance(errors_raw, list):
            errors = [str(e) for e in errors_raw]
        return cls(
            status=status,
            captured_at=captured_at,
            source=source,
            alert_count=alert_count,
            alerts=tuple(alerts),
            errors=tuple(errors),
            truncated=bool(raw.get("truncated")),
        )


@dataclass(frozen=True)
class AlertmanagerCompact:
    """Compact deterministic JSON summarization for LLM prompts."""
    status: str
    alert_count: int
    severity_counts: tuple[tuple[str, int], ...]
    state_counts: tuple[tuple[str, int], ...]
    top_alert_names: tuple[str, ...]
    affected_namespaces: tuple[str, ...]
    affected_clusters: tuple[str, ...]
    affected_services: tuple[str, ...]
    truncated: bool
    captured_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "alert_count": self.alert_count,
            "severity_counts": {k: v for k, v in self.severity_counts},
            "state_counts": {k: v for k, v in self.state_counts},
            "top_alert_names": list(self.top_alert_names),
            "affected_namespaces": list(self.affected_namespaces),
            "affected_clusters": list(self.affected_clusters),
            "affected_services": list(self.affected_services),
            "truncated": self.truncated,
            "captured_at": self.captured_at,
        }

    def to_json_bytes(self) -> bytes:
        """Return deterministic JSON bytes for same input."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _truncate_string(s: str | None, max_len: int) -> str | None:
    """Truncate string to max length."""
    if s is None:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def normalize_alertmanager_payload(
    raw: Any,
    config_max_alerts: int = 200,
    config_max_string_length: int = 200,
) -> AlertmanagerSnapshot:
    """Normalize raw Alertmanager API response into snapshot."""
    captured_at = datetime.now(UTC).isoformat()
    if raw is None:
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=None,
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
                source=None,
                alert_count=0,
                alerts=(),
                errors=(f"Failed to parse JSON: {raw[:200]}",),
            )
    if not isinstance(raw, Mapping):
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=None,
            alert_count=0,
            alerts=(),
            errors=(f"Expected dict response, got {type(raw).__name__}",),
        )
    alerts_raw = raw.get("data", {}).get("alerts") if isinstance(raw.get("data"), Mapping) else raw.get("alerts")
    if alerts_raw is None:
        alerts_raw = []
    if not isinstance(alerts_raw, list):
        return AlertmanagerSnapshot(
            status=AlertmanagerStatus.INVALID_RESPONSE,
            captured_at=captured_at,
            source=None,
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
        labels_sorted = tuple(sorted(
            (str(k), str(v)) for k, v in labels_raw.items()
        ))
        alert = NormalizedAlert(
            fingerprint=_truncate_string(labels_raw.get("fingerprint"), 64) or str(hash(str(labels_raw)) % 10**12),
            alertname=_truncate_string(labels_raw.get("alertname"), config_max_string_length) or "unknown",
            state=_truncate_string(alert_raw.get("status") or labels_raw.get("state"), config_max_string_length) or "inactive",
            severity=_truncate_string(labels_raw.get("severity"), config_max_string_length) or "info",
            cluster=labels_raw.get("cluster"),
            namespace=labels_raw.get("namespace"),
            service=labels_raw.get("service"),
            instance=labels_raw.get("instance"),
            starts_at=alert_raw.get("startsAt") or alert_raw.get("starts_at"),
            summary=_truncate_string(alert_raw.get("annotations", {}).get("summary", labels_raw.get("summary")), config_max_string_length),
            labels=labels_sorted,
        )
        alerts.append(alert)
    status = AlertmanagerStatus.OK
    if not alerts:
        status = AlertmanagerStatus.EMPTY
    return AlertmanagerSnapshot(
        status=status,
        captured_at=captured_at,
        source=None,
        alert_count=total_count,
        alerts=tuple(alerts),
        errors=(),
        truncated=truncated,
    )


def snapshot_to_compact(
    snapshot: AlertmanagerSnapshot,
    max_alerts: int = 20,
) -> AlertmanagerCompact:
    """Convert normalized snapshot to compact LLM-ready JSON."""
    severity_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    alert_names: dict[str, int] = {}
    namespaces: set[str] = set()
    clusters: set[str] = set()
    services: set[str] = set()
    for alert in snapshot.alerts:
        sev = alert.severity or "unknown"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        state = alert.state or "unknown"
        state_counts[state] = state_counts.get(state, 0) + 1
        name = alert.alertname or "unknown"
        alert_names[name] = alert_names.get(name, 0) + 1
        if alert.namespace:
            namespaces.add(alert.namespace)
        if alert.cluster:
            clusters.add(alert.cluster)
        if alert.service:
            services.add(alert.service)
    top_alerts = sorted(alert_names.items(), key=lambda x: (-x[1], x[0]))[:max_alerts]
    top_alert_names = tuple(name for name, _ in top_alerts)
    affected_namespaces = tuple(sorted(namespaces))[:max_alerts]
    affected_clusters = tuple(sorted(clusters))[:max_alerts]
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
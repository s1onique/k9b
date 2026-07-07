"""Contract definitions for Alertmanager snapshot types.

This module contains:
- Enums and status values
- Dataclasses for normalized alerts and snapshots
- Type aliases and constants
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..identity.artifact import new_artifact_id


class AlertmanagerStatus(StrEnum):
    """Status values for Alertmanager snapshot."""
    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    UPSTREAM_ERROR = "upstream_error"
    DISABLED = "disabled"
    INVALID_RESPONSE = "invalid_response"


# Sensitive key patterns for annotation redaction (ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1)
SENSITIVE_KEY_PATTERNS = (
    "password",
    "secret",
    "token",
    "bearer",
    "auth",
    "credential",
    "private",
    "key",
    "api_key",
    "apikey",
    "access_key",
    "aws_access",
    "gcp_",
    "azure_",
)


@dataclass(frozen=True)
class NormalizedAlert:
    """Normalized alert fields suitable for storage and debugging.
    
    Extended in ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1 to preserve:
    - annotations: full annotation key-value pairs
    - generator_url: link to alert source
    - ends_at: when alert is expected to end
    - updated_at: when alert was last updated
    - receiver: Alertmanager receiver that received this alert
    """
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
    # Extended fields for richer evidence preservation
    annotations: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # ACT-R1
    generator_url: str | None = None  # ACT-R1
    ends_at: str | None = None  # ACT-R1
    updated_at: str | None = None  # ACT-R1
    receiver: str | None = None  # ACT-R1

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
        # Extended fields - only serialize if non-empty/non-None for backward compat
        if self.annotations:
            result["annotations"] = {k: v for k, v in self.annotations}
        if self.generator_url is not None:
            result["generator_url"] = self.generator_url
        if self.ends_at is not None:
            result["ends_at"] = self.ends_at
        if self.updated_at is not None:
            result["updated_at"] = self.updated_at
        if self.receiver is not None:
            result["receiver"] = self.receiver
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
    # Immutable artifact instance identity (UUIDv7)
    # Generated for new snapshots; None for legacy artifacts (backward compat)
    artifact_id: str | None = field(default_factory=new_artifact_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "captured_at": self.captured_at,
            "source": self.source,
            "alert_count": self.alert_count,
            "alerts": [alert.to_dict() for alert in self.alerts],
            "errors": list(self.errors),
            "truncated": self.truncated,
            "artifact_id": self.artifact_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> AlertmanagerSnapshot:
        """Deserialize from dict with backward compatibility for legacy artifacts.
        
        Extended in ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1 to handle:
        - annotations field (may be absent in legacy snapshots)
        - generator_url field (may be absent in legacy snapshots)
        - ends_at field (may be absent in legacy snapshots)
        - updated_at field (may be absent in legacy snapshots)
        - receiver field (may be absent in legacy snapshots)
        
        Note: Explicitly sets artifact_id=None for legacy artifacts to preserve
        the distinction between new runtime snapshots (generated ID) and
        legacy deserialized snapshots (None).
        """
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
                    # Parse annotations - backward compat: may be absent in legacy
                    annotations_raw = alert_raw.get("annotations")
                    annotations: list[tuple[str, str]] = []
                    if isinstance(annotations_raw, dict):
                        annotations = [(str(k), str(v)) for k, v in sorted(annotations_raw.items())]
                    elif isinstance(annotations_raw, list):
                        # Handle list format if present
                        for item in annotations_raw:
                            if isinstance(item, (list, tuple)) and len(item) == 2:
                                annotations.append((str(item[0]), str(item[1])))
                        annotations.sort()
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
                        # Extended fields (ACT-R1) - backward compat: may be absent
                        annotations=tuple(annotations) if annotations else (),
                        generator_url=alert_raw.get("generator_url"),
                        ends_at=alert_raw.get("ends_at"),
                        updated_at=alert_raw.get("updated_at"),
                        receiver=alert_raw.get("receiver"),
                    ))
        errors_raw = raw.get("errors") or []
        errors: list[str] = []
        if isinstance(errors_raw, list):
            errors = [str(e) for e in errors_raw]
        # artifact_id: None for legacy, or explicit value if present
        artifact_id: str | None = None
        if raw.get("artifact_id"):
            artifact_id = str(raw["artifact_id"])
        return cls(
            status=status,
            captured_at=captured_at,
            source=source,
            alert_count=alert_count,
            alerts=tuple(alerts),
            errors=tuple(errors),
            truncated=bool(raw.get("truncated")),
            artifact_id=artifact_id,
        )


@dataclass(frozen=True)
class ClusterAlertSummary:
    """Per-cluster alert summary within AlertmanagerCompact.by_cluster."""
    cluster: str
    alert_count: int
    severity_counts: tuple[tuple[str, int], ...]
    state_counts: tuple[tuple[str, int], ...]
    top_alert_names: tuple[str, ...]
    affected_namespaces: tuple[str, ...]
    affected_services: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster": self.cluster,
            "alert_count": self.alert_count,
            "severity_counts": {k: v for k, v in self.severity_counts},
            "state_counts": {k: v for k, v in self.state_counts},
            "top_alert_names": list(self.top_alert_names),
            "affected_namespaces": list(self.affected_namespaces),
            "affected_services": list(self.affected_services),
        }


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
    # Per-cluster breakdown for cluster-scoped UI panels
    by_cluster: tuple[ClusterAlertSummary, ...] = field(default_factory=tuple)
    # Immutable artifact instance identity (UUIDv7); separate from source snapshot identity
    artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
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
        if self.by_cluster:
            result["by_cluster"] = [s.to_dict() for s in self.by_cluster]
        # Include artifact_id if present (for new artifacts)
        if self.artifact_id is not None:
            result["artifact_id"] = self.artifact_id
        return result

    def to_json_bytes(self) -> bytes:
        """Return deterministic JSON bytes for same input."""
        import json
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")

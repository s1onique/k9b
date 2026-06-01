"""vmalert rule-state data models.

Moved from vmalert_rule_state.py as a focused extraction seam.
These models represent vmalert's alerting state as read-only diagnostic context.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .vmalert_rule_state_normalize import (  # noqa: F401 - re-exported for backward compatibility
    _MAX_STRING_LENGTH,
    _truncate_string,
)


class AlertState(StrEnum):
    """Alert state values from vmalert."""

    FIRING = "firing"
    PENDING = "pending"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VmalertRuleGroup:
    """Normalized representation of a vmalert rule group.

    A rule group contains related alerting/recording rules that share
    evaluation interval and other configuration.
    """

    name: str
    file: str | None = None
    interval: str | None = None
    # Source tracking
    source_endpoint: str | None = None
    # Count of rules in this group
    rule_count: int = 0
    # Count of firing alerts in this group
    firing_alert_count: int = 0
    # Count of rules with errors
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "rule_count": self.rule_count,
            "firing_alert_count": self.firing_alert_count,
            "error_count": self.error_count,
        }
        if self.file is not None:
            result["file"] = self.file
        if self.interval is not None:
            result["interval"] = self.interval
        if self.source_endpoint is not None:
            result["source_endpoint"] = self.source_endpoint
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> VmalertRuleGroup:
        return cls(
            name=str(raw.get("name", "")),
            file=str(raw.get("file")) if raw.get("file") else None,
            interval=str(raw.get("interval")) if raw.get("interval") else None,
            source_endpoint=str(raw.get("source_endpoint")) if raw.get("source_endpoint") else None,
            rule_count=int(raw.get("rule_count", 0)),
            firing_alert_count=int(raw.get("firing_alert_count", 0)),
            error_count=int(raw.get("error_count", 0)),
        )


@dataclass(frozen=True)
class VmalertRule:
    """Normalized representation of a vmalert rule within a group.

    Captures rule identity, state, and evaluation context.
    """

    name: str
    # Rule type: "alerting" or "recording"
    type: str | None = None
    # Health status: "ok" or "err" with optional error message
    health: str | None = None
    last_error: str | None = None
    # Expression that triggered the rule
    query: str | None = None
    # Source tracking
    source_endpoint: str | None = None
    group_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
        }
        if self.type is not None:
            result["type"] = self.type
        if self.health is not None:
            result["health"] = self.health
        if self.last_error is not None:
            result["last_error"] = _truncate_string(self.last_error, _MAX_STRING_LENGTH)
        if self.query is not None:
            result["query"] = _truncate_string(self.query, _MAX_STRING_LENGTH)
        if self.source_endpoint is not None:
            result["source_endpoint"] = self.source_endpoint
        if self.group_name is not None:
            result["group_name"] = self.group_name
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> VmalertRule:
        return cls(
            name=str(raw.get("name", "")),
            type=str(raw.get("type")) if raw.get("type") else None,
            health=str(raw.get("health")) if raw.get("health") else None,
            last_error=str(raw.get("last_error")) if raw.get("last_error") else None,
            query=str(raw.get("query")) if raw.get("query") else None,
            source_endpoint=str(raw.get("source_endpoint")) if raw.get("source_endpoint") else None,
            group_name=str(raw.get("group_name")) if raw.get("group_name") else None,
        )


@dataclass(frozen=True)
class VmalertAlertSignal:
    """Normalized alert signal from vmalert for diagnostic context.

    This is a read-only representation suitable for:
    - Incident report context
    - Operator triage worklist items
    - Cross-signal correlation

    Does NOT model:
    - Silences (Alertmanager concept)
    - Inhibition rules (Alertmanager concept)
    - Notification state (Alertmanager concept)
    """

    # Core identity
    alertname: str
    state: AlertState

    # Labels for correlation and filtering
    labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Derived diagnostic fields
    severity: str | None = None
    cluster_label: str | None = None
    namespace: str | None = None
    workload: str | None = None
    pod: str | None = None
    instance: str | None = None

    # Annotations
    summary: str | None = None
    description: str | None = None

    # Temporal
    active_at: str | None = None
    starts_at: str | None = None

    # Alert value at evaluation time
    value: str | None = None
    # Expression that triggered
    expression: str | None = None

    # Source tracking
    source_endpoint: str | None = None
    source_id: str | None = None
    group_name: str | None = None
    rule_name: str | None = None

    def __post_init__(self) -> None:
        # Normalize severity to lowercase if present
        if self.severity is not None:
            object.__setattr__(self, 'severity', self.severity.lower())

    @property
    def is_firing(self) -> bool:
        """Return True if alert is in firing state."""
        return self.state == AlertState.FIRING

    @property
    def is_pending(self) -> bool:
        """Return True if alert is pending."""
        return self.state == AlertState.PENDING

    @property
    def is_critical(self) -> bool:
        """Return True if severity is critical."""
        return self.severity == "critical"

    @property
    def labels_dict(self) -> dict[str, str]:
        """Return labels as dict for easier access."""
        return dict(self.labels)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "alertname": self.alertname,
            "state": self.state.value,
        }
        # Labels
        if self.labels:
            result["labels"] = dict(self.labels)
        # Derived fields
        if self.severity is not None:
            result["severity"] = self.severity
        if self.cluster_label is not None:
            result["cluster_label"] = self.cluster_label
        if self.namespace is not None:
            result["namespace"] = self.namespace
        if self.workload is not None:
            result["workload"] = self.workload
        if self.pod is not None:
            result["pod"] = self.pod
        if self.instance is not None:
            result["instance"] = self.instance
        # Annotations
        if self.summary is not None:
            result["summary"] = _truncate_string(self.summary, _MAX_STRING_LENGTH)
        if self.description is not None:
            result["description"] = _truncate_string(self.description, _MAX_STRING_LENGTH)
        # Temporal
        if self.active_at is not None:
            result["active_at"] = self.active_at
        if self.starts_at is not None:
            result["starts_at"] = self.starts_at
        # Values
        if self.value is not None:
            result["value"] = self.value
        if self.expression is not None:
            result["expression"] = _truncate_string(self.expression, _MAX_STRING_LENGTH)
        # Source
        if self.source_endpoint is not None:
            result["source_endpoint"] = self.source_endpoint
        if self.source_id is not None:
            result["source_id"] = self.source_id
        if self.group_name is not None:
            result["group_name"] = self.group_name
        if self.rule_name is not None:
            result["rule_name"] = self.rule_name
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> VmalertAlertSignal:
        # Parse state
        state_raw = str(raw.get("state", "unknown"))
        try:
            state = AlertState(state_raw)
        except ValueError:
            state = AlertState.UNKNOWN

        # Parse labels
        labels_raw = raw.get("labels")
        labels: tuple[tuple[str, str], ...] = ()
        if isinstance(labels_raw, dict):
            labels = tuple(sorted((str(k), str(v)) for k, v in labels_raw.items()))

        return cls(
            alertname=str(raw.get("alertname", "unknown")),
            state=state,
            labels=labels,
            severity=str(raw.get("severity")) if raw.get("severity") else None,
            cluster_label=str(raw.get("cluster_label")) if raw.get("cluster_label") else None,
            namespace=str(raw.get("namespace")) if raw.get("namespace") else None,
            workload=str(raw.get("workload")) if raw.get("workload") else None,
            pod=str(raw.get("pod")) if raw.get("pod") else None,
            instance=str(raw.get("instance")) if raw.get("instance") else None,
            summary=str(raw.get("summary")) if raw.get("summary") else None,
            description=str(raw.get("description")) if raw.get("description") else None,
            active_at=str(raw.get("active_at")) if raw.get("active_at") else None,
            starts_at=str(raw.get("starts_at")) if raw.get("starts_at") else None,
            value=str(raw.get("value")) if raw.get("value") else None,
            expression=str(raw.get("expression")) if raw.get("expression") else None,
            source_endpoint=str(raw.get("source_endpoint")) if raw.get("source_endpoint") else None,
            source_id=str(raw.get("source_id")) if raw.get("source_id") else None,
            group_name=str(raw.get("group_name")) if raw.get("group_name") else None,
            rule_name=str(raw.get("rule_name")) if raw.get("rule_name") else None,
        )


__all__ = [
    "AlertState",
    "VmalertRuleGroup",
    "VmalertRule",
    "VmalertAlertSignal",
]

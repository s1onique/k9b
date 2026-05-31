"""Normalized models for vmalert rule and alert state.

This module defines internal models for representing vmalert's alerting state
as read-only diagnostic context. These models are derived from vmalert's
/api/v1/rules and /api/v1/alerts endpoints.

Key design:
- Read-only representation of vmalert state
- Designed for diagnostic context, not management
- Does not model silences/inhibition (Alertmanager concepts)
- Maps vmalert state to operator-relevant signals

Extraction seam:
- Label derivation and string normalization helpers moved to
  vmalert_rule_state_normalize.py for focused testing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

from .vmalert_rule_state_normalize import (  # noqa: F401 - re-exported for backward compatibility
    _MAX_STRING_LENGTH,
    _SEVERITY_PRIORITY,
    _derive_namespace_from_labels,
    _derive_workload_from_labels,
    _extract_severity_from_labels,
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


def normalize_vmalert_response(
    raw: Mapping[str, Any],
    source_endpoint: str,
    max_string_length: int = _MAX_STRING_LENGTH,
) -> tuple[tuple[VmalertAlertSignal, ...], tuple[VmalertRuleGroup, ...]]:
    """Normalize vmalert /api/v1/rules or /api/v1/alerts response to typed models.

    Args:
        raw: Raw API response data
        source_endpoint: The vmalert endpoint that produced this response
        max_string_length: Maximum length for string fields

    Returns:
        Tuple of (alerts, rule_groups) extracted from the response
    """
    alerts: list[VmalertAlertSignal] = []
    rule_groups: list[VmalertRuleGroup] = []

    # Check for error in response
    if raw.get("error"):
        return ((), ())

    # Handle vmalert's data wrapper format: {"data": {"alerts": [...]}}
    data = raw.get("data", raw)

    # Try /api/v1/alerts format first: {"data": {"alerts": [...]}}
    alerts_data = data.get("alerts", [])
    if isinstance(alerts_data, list):
        for alert_raw in alerts_data:
            if not isinstance(alert_raw, dict):
                continue
            alert = _normalize_alert(alert_raw, source_endpoint, max_string_length)
            if alert:
                alerts.append(alert)

    # Try /api/v1/rules format: {"data": {"groups": [...]}}
    groups_data = data.get("groups", [])
    if isinstance(groups_data, list):
        for group_raw in groups_data:
            if not isinstance(group_raw, dict):
                continue
            group, group_alerts = _normalize_rule_group(group_raw, source_endpoint, max_string_length)
            if group:
                rule_groups.append(group)
            alerts.extend(group_alerts)

    return (tuple(alerts), tuple(rule_groups))


def _normalize_alert(
    raw: Mapping[str, Any],
    source_endpoint: str,
    max_string_length: int,
) -> VmalertAlertSignal | None:
    """Normalize a single alert from vmalert response."""
    # Get labels (handle both vmalert formats)
    labels_raw: Mapping[str, Any] = {}
    if isinstance(raw.get("labels"), dict):
        labels_raw = cast(Mapping[str, Any], raw["labels"])
    elif isinstance(raw.get("annotations"), dict):
        # Some formats nest under annotations
        labels_raw = cast(Mapping[str, Any], raw.get("annotations", {}))

    # Extract label string mapping
    labels: dict[str, str] = {}
    for k, v in labels_raw.items():
        if v is not None:
            labels[str(k)] = str(v)

    # Get alertname
    alertname = labels.get("alertname", "unknown")
    if alertname == "unknown":
        # Fallback to top-level field
        alertname = str(raw.get("name", raw.get("alertname", "unknown")))

    # Get state
    state_raw = str(raw.get("state", "inactive")).lower()
    try:
        state = AlertState(state_raw)
    except ValueError:
        state = AlertState.UNKNOWN

    # Extract severity from labels
    severity = _extract_severity_from_labels(labels)

    # Derive namespace and workload
    namespace = _derive_namespace_from_labels(labels)
    workload = _derive_workload_from_labels(labels)

    # Get annotations
    annotations: dict[str, Any] = {}
    if isinstance(raw.get("annotations"), dict):
        annotations = cast(dict[str, Any], raw["annotations"])
    elif isinstance(raw.get("labels"), dict):
        # Some formats nest under labels
        pass

    # Extract summary and description
    summary = None
    for key in ("summary", "description", "message"):
        val = annotations.get(key)
        if val:
            summary = _truncate_string(str(val), max_string_length)
            break

    description = annotations.get("description")
    if description:
        description = _truncate_string(str(description), max_string_length)

    # Get temporal fields
    active_at = None
    for key in ("activeAt", "active_at", "startsAt", "starts_at"):
        val = raw.get(key)
        if val:
            active_at = str(val)
            break

    starts_at = raw.get("startsAt") or raw.get("starts_at")
    if starts_at:
        starts_at = str(starts_at)

    # Get value
    value = raw.get("value")
    if value is not None:
        value = str(value)

    # Get expression
    expression = raw.get("expr") or raw.get("expression")
    if expression:
        expression = _truncate_string(str(expression), max_string_length)

    # Source tracking
    group_name = labels.get("group") or raw.get("group")
    rule_name = labels.get("rule") or raw.get("rule_name") or raw.get("name")

    return VmalertAlertSignal(
        alertname=alertname,
        state=state,
        labels=tuple(sorted(labels.items())),
        severity=severity,
        cluster_label=labels.get("cluster"),
        namespace=namespace,
        workload=workload,
        pod=labels.get("pod"),
        instance=labels.get("instance"),
        summary=summary,
        description=description,
        active_at=active_at,
        starts_at=starts_at,
        value=value,
        expression=expression,
        source_endpoint=source_endpoint,
        source_id=source_endpoint,  # Use endpoint as source_id
        group_name=str(group_name) if group_name else None,
        rule_name=str(rule_name) if rule_name else None,
    )


def _normalize_rule_group(
    raw: Mapping[str, Any],
    source_endpoint: str,
    max_string_length: int,
) -> tuple[VmalertRuleGroup, list[VmalertAlertSignal]]:
    """Normalize a rule group and extract its alerts."""
    group_name = str(raw.get("name", "unknown"))
    file_path = raw.get("file")
    interval = raw.get("interval")

    rules_data = raw.get("rules", [])
    if not isinstance(rules_data, list):
        rules_data = []

    firing_count = 0
    error_count = 0
    alerts: list[VmalertAlertSignal] = []

    for rule_raw in rules_data:
        if not isinstance(rule_raw, dict):
            continue

        # Check for alert inside rule (from /api/v1/rules format)
        alert_data = rule_raw.get("alerts")
        if isinstance(alert_data, list):
            for alert_raw in alert_data:
                if not isinstance(alert_raw, dict):
                    continue
                alert = _normalize_alert(alert_raw, source_endpoint, max_string_length)
                if alert:
                    alerts.append(alert)
                    if alert.is_firing:
                        firing_count += 1

        # Check health status of rule
        health = str(rule_raw.get("health", "ok")).lower()
        if health == "err":
            error_count += 1

    group = VmalertRuleGroup(
        name=group_name,
        file=str(file_path) if file_path else None,
        interval=str(interval) if interval else None,
        source_endpoint=source_endpoint,
        rule_count=len(rules_data),
        firing_alert_count=firing_count,
        error_count=error_count,
    )

    return (group, alerts)

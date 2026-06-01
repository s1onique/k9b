"""Normalized models for vmalert rule and alert state.

This module defines internal models for representing vmalert's alerting state
as read-only diagnostic context. These models are derived from vmalert's
/api/v1/rules and /api/v1/alerts endpoints.

Key design:
- Read-only representation of vmalert state
- Designed for diagnostic context, not management
- Does not model silences/inhibition (Alertmanager concepts)
- Maps vmalert state to operator-relevant signals

Extraction seams:
- Models (AlertState, VmalertRuleGroup, VmalertRule, VmalertAlertSignal) moved to
  vmalert_rule_state_models.py for focused testing.
- Label derivation and string normalization helpers moved to
  vmalert_rule_state_normalize.py for focused testing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from .vmalert_rule_state_models import (  # noqa: F401 - re-exported for backward compatibility
    AlertState,
    VmalertAlertSignal,
    VmalertRule,
    VmalertRuleGroup,
)
from .vmalert_rule_state_normalize import (  # noqa: F401 - re-exported for backward compatibility
    _MAX_STRING_LENGTH,
    _SEVERITY_PRIORITY,
    _derive_namespace_from_labels,
    _derive_workload_from_labels,
    _extract_severity_from_labels,
    _truncate_string,
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

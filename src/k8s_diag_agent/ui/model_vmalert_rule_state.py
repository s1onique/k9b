"""View models for vmalert rule state UI layer.

This module contains view model dataclasses for vmalert rule/alert state,
extracted from the external_analysis artifact. It mirrors the pattern used
for Alertmanager compact views.

Dependency direction: model_vmalert_rule_state.py -> model_primitives.py
model.py imports from model_vmalert_rule_state.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class VmalertRuleStateAlertView:
    """View model for a single vmalert alert in rule state."""
    alertname: str
    state: str
    severity: str | None
    cluster_label: str | None
    namespace: str | None
    workload: str | None
    pod: str | None
    instance: str | None
    summary: str | None
    description: str | None
    active_at: str | None
    starts_at: str | None
    source_endpoint: str | None
    group_name: str | None
    rule_name: str | None


@dataclass(frozen=True)
class VmalertRuleStateRuleGroupView:
    """View model for a vmalert rule group in rule state."""
    name: str
    file: str | None
    interval: str | None
    rule_count: int
    firing_alert_count: int
    error_count: int


@dataclass(frozen=True)
class VmalertRuleStateFetchErrorView:
    """View model for a vmalert fetch error."""
    source_endpoint: str
    source_id: str | None
    status: str
    error: str


@dataclass(frozen=True)
class VmalertRuleStateView:
    """View model for vmalert rule state artifact."""
    source_count: int
    fetched_source_count: int
    failed_source_count: int
    alert_count: int
    firing_alert_count: int
    pending_alert_count: int
    critical_firing_count: int
    rule_group_count: int
    fetch_error_count: int
    captured_at: str
    alerts: tuple[VmalertRuleStateAlertView, ...]
    rule_groups: tuple[VmalertRuleStateRuleGroupView, ...]
    fetch_errors: tuple[VmalertRuleStateFetchErrorView, ...]

    # Computed diagnostic context for incident report
    @property
    def top_alertnames(self) -> tuple[str, ...]:
        """Return top alertnames by firing count."""
        from collections import Counter
        firing_names = [a.alertname for a in self.alerts if a.state == "firing"]
        counts = Counter(firing_names).most_common(5)
        return tuple(name for name, _ in counts)

    @property
    def severity_counts(self) -> tuple[tuple[str, int], ...]:
        """Return severity counts for firing alerts."""
        from collections import Counter
        firing_severities = [a.severity or "unknown" for a in self.alerts if a.state == "firing"]
        counts = Counter(firing_severities).most_common()
        return tuple((sev, cnt) for sev, cnt in counts)

    @property
    def affected_namespaces(self) -> tuple[str, ...]:
        """Return affected namespaces from firing alerts."""
        seen: set[str] = set()
        result: list[str] = []
        for alert in self.alerts:
            if alert.state == "firing" and alert.namespace and alert.namespace not in seen:
                seen.add(alert.namespace)
                result.append(alert.namespace)
        return tuple(result)

    @property
    def affected_workloads(self) -> tuple[str, ...]:
        """Return affected workloads from firing alerts."""
        seen: set[str] = set()
        result: list[str] = []
        for alert in self.alerts:
            if alert.state == "firing" and alert.workload and alert.workload not in seen:
                seen.add(alert.workload)
                result.append(alert.workload)
        return tuple(result)


def _build_vmalert_rule_state_alert_view(
    raw: Mapping[str, Any],
) -> VmalertRuleStateAlertView:
    """Build VmalertRuleStateAlertView from raw JSON data."""
    return VmalertRuleStateAlertView(
        alertname=_coerce_str(raw.get("alertname", "unknown")),
        state=_coerce_str(raw.get("state", "unknown")),
        severity=_coerce_optional_str(raw.get("severity")),
        cluster_label=_coerce_optional_str(raw.get("cluster_label")),
        namespace=_coerce_optional_str(raw.get("namespace")),
        workload=_coerce_optional_str(raw.get("workload")),
        pod=_coerce_optional_str(raw.get("pod")),
        instance=_coerce_optional_str(raw.get("instance")),
        summary=_coerce_optional_str(raw.get("summary")),
        description=_coerce_optional_str(raw.get("description")),
        active_at=_coerce_optional_str(raw.get("active_at")),
        starts_at=_coerce_optional_str(raw.get("starts_at")),
        source_endpoint=_coerce_optional_str(raw.get("source_endpoint")),
        group_name=_coerce_optional_str(raw.get("group_name")),
        rule_name=_coerce_optional_str(raw.get("rule_name")),
    )


def _build_vmalert_rule_state_rule_group_view(
    raw: Mapping[str, Any],
) -> VmalertRuleStateRuleGroupView:
    """Build VmalertRuleStateRuleGroupView from raw JSON data."""
    return VmalertRuleStateRuleGroupView(
        name=_coerce_str(raw.get("name", "unknown")),
        file=_coerce_optional_str(raw.get("file")),
        interval=_coerce_optional_str(raw.get("interval")),
        rule_count=_coerce_int(raw.get("rule_count")),
        firing_alert_count=_coerce_int(raw.get("firing_alert_count")),
        error_count=_coerce_int(raw.get("error_count")),
    )


def _build_vmalert_rule_state_fetch_error_view(
    raw: Mapping[str, Any],
) -> VmalertRuleStateFetchErrorView:
    """Build VmalertRuleStateFetchErrorView from raw JSON data."""
    return VmalertRuleStateFetchErrorView(
        source_endpoint=_coerce_str(raw.get("source_endpoint", "")),
        source_id=_coerce_optional_str(raw.get("source_id")),
        status=_coerce_str(raw.get("status", "unknown")),
        error=_coerce_str(raw.get("error", "")),
    )


def _build_vmalert_rule_state_view(
    raw: object | None,
) -> VmalertRuleStateView | None:
    """Build VmalertRuleStateView from raw JSON data (vmalert_rule_state field).

    Returns None when artifact is missing (not an error).
    """
    if not isinstance(raw, Mapping):
        return None

    # Parse alerts
    alerts_raw = raw.get("alerts") or ()
    alerts: list[VmalertRuleStateAlertView] = []
    if isinstance(alerts_raw, Sequence) and not isinstance(alerts_raw, (str, bytes)):
        for alert_raw in alerts_raw:
            if isinstance(alert_raw, Mapping):
                alerts.append(_build_vmalert_rule_state_alert_view(alert_raw))

    # Parse rule groups
    rule_groups_raw = raw.get("rule_groups") or ()
    rule_groups: list[VmalertRuleStateRuleGroupView] = []
    if isinstance(rule_groups_raw, Sequence) and not isinstance(rule_groups_raw, (str, bytes)):
        for group_raw in rule_groups_raw:
            if isinstance(group_raw, Mapping):
                rule_groups.append(_build_vmalert_rule_state_rule_group_view(group_raw))

    # Parse fetch errors
    fetch_errors_raw = raw.get("fetch_errors") or ()
    fetch_errors: list[VmalertRuleStateFetchErrorView] = []
    if isinstance(fetch_errors_raw, Sequence) and not isinstance(fetch_errors_raw, (str, bytes)):
        for error_raw in fetch_errors_raw:
            if isinstance(error_raw, Mapping):
                fetch_errors.append(_build_vmalert_rule_state_fetch_error_view(error_raw))

    # Compute firing/pending/critical counts
    firing_count = sum(1 for a in alerts if a.state == "firing")
    pending_count = sum(1 for a in alerts if a.state == "pending")
    critical_count = sum(1 for a in alerts if a.state == "firing" and a.severity == "critical")

    return VmalertRuleStateView(
        source_count=_coerce_int(raw.get("source_count")),
        fetched_source_count=_coerce_int(raw.get("fetched_source_count")),
        failed_source_count=_coerce_int(raw.get("failed_source_count")),
        alert_count=len(alerts),
        firing_alert_count=firing_count,
        pending_alert_count=pending_count,
        critical_firing_count=critical_count,
        rule_group_count=len(rule_groups),
        fetch_error_count=len(fetch_errors),
        captured_at=_coerce_str(raw.get("captured_at", "")),
        alerts=tuple(alerts),
        rule_groups=tuple(rule_groups),
        fetch_errors=tuple(fetch_errors),
    )

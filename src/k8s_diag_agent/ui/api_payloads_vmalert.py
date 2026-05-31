"""TypedDict payload definitions for vmalert contracts."""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    # vmalert source inventory contracts
    "VmalertSourcePayload",
    "VmalertSourcesPayload",
    # vmalert rule state contracts
    "VmalertRuleStateAlertPayload",
    "VmalertRuleStateRuleGroupPayload",
    "VmalertRuleStateFetchErrorPayload",
    "VmalertRuleStatePayload",
]


class VmalertSourcePayload(TypedDict, total=False):
    """Payload for a single vmalert source."""

    source_id: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str
    state: str
    discovered_at: str | None
    verified_at: str | None
    last_check: str | None
    last_error: str | None
    verified_version: str | None
    confidence_hints: list[str]
    # Deduplication provenance fields
    merged_provenances: list[str]  # all contributing origins
    display_provenance: str  # human-readable provenance string
    # Manual provenance: distinguishes operator-configured vs operator-promoted
    manual_source_mode: str | None  # operator-configured, operator-promoted, or not-present
    # Computed UI fields
    is_manual: bool
    is_tracking: bool
    can_disable: bool
    can_promote: bool
    display_origin: str
    display_state: str
    provenance_summary: str
    # Cluster association for per-cluster UI filtering
    cluster_label: str | None
    # Deterministic identity fields for historical/debug tracking
    canonicalEntityId: str | None
    cluster_uid: str | None
    object_uid: str | None


class VmalertSourcesPayload(TypedDict, total=False):
    """Payload for the full vmalert source inventory."""

    sources: list[VmalertSourcePayload]
    total_count: int
    source_count: int
    discovered_count: int
    discovered_but_unverified_count: int
    auto_tracked_count: int
    manual_count: int
    discovery_timestamp: str | None
    cluster_context: str | None


class VmalertRuleStateAlertPayload(TypedDict, total=False):
    """Payload for a single vmalert alert in rule state."""

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


class VmalertRuleStateRuleGroupPayload(TypedDict, total=False):
    """Payload for a vmalert rule group in rule state."""

    name: str
    file: str | None
    interval: str | None
    rule_count: int
    firing_alert_count: int
    error_count: int


class VmalertRuleStateFetchErrorPayload(TypedDict, total=False):
    """Payload for a vmalert fetch error in rule state."""

    source_endpoint: str
    source_id: str | None
    status: str
    error: str


class VmalertRuleStatePayload(TypedDict, total=False):
    """Payload for vmalert rule state in run payload.

    Exposes collected vmalert alert/rule state as read-only diagnostic context.

    Contract invariants:
    - source_count: total sources attempted
    - fetched_source_count: sources successfully fetched
    - failed_source_count: sources that failed to fetch (non-fatal)
    - alert_count: total alerts across all sources
    - firing_alert_count: alerts in firing state
    - pending_alert_count: alerts in pending state
    - critical_firing_count: firing alerts with critical severity
    - alerts: list of alert signals
    - rule_groups: list of rule groups
    - fetch_errors: list of fetch errors (non-fatal diagnostic context)
    - Missing artifact returns None (not an error)
    """

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
    alerts: list[VmalertRuleStateAlertPayload]
    rule_groups: list[VmalertRuleStateRuleGroupPayload]
    fetch_errors: list[VmalertRuleStateFetchErrorPayload]

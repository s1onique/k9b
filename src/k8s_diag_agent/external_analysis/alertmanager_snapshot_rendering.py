"""Rendering and formatting helpers for Alertmanager snapshots.

This module contains:
- Markdown/text formatting helpers
- Display-only display helpers
- UI-oriented formatting

Note: For most use cases, use AlertmanagerCompact.to_dict() and
AlertmanagerCompact.to_json_bytes() which provide deterministic JSON output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alertmanager_snapshot_contract import AlertmanagerCompact, AlertmanagerSnapshot


def format_snapshot_summary(snapshot: AlertmanagerSnapshot) -> str:
    """Format a human-readable summary of an Alertmanager snapshot."""
    lines = [
        "# Alertmanager Snapshot",
        "",
        f"Status: {snapshot.status.value}",
        f"Captured: {snapshot.captured_at}",
        f"Source: {snapshot.source or 'unknown'}",
        f"Total Alerts: {snapshot.alert_count}",
        f"Truncated: {snapshot.truncated}",
        "",
    ]
    
    if snapshot.errors:
        lines.append("## Errors")
        for error in snapshot.errors:
            lines.append(f"- {error}")
        lines.append("")
    
    if snapshot.alerts:
        lines.append("## Alerts")
        for i, alert in enumerate(snapshot.alerts[:10], 1):
            lines.append(f"{i}. {alert.alertname} ({alert.state}) - {alert.severity}")
        if len(snapshot.alerts) > 10:
            lines.append(f"... and {len(snapshot.alerts) - 10} more")
        lines.append("")
    
    return "\n".join(lines)


def format_compact_summary(compact: AlertmanagerCompact) -> str:
    """Format a human-readable summary of an Alertmanager compact artifact."""
    lines = [
        "# Alertmanager Compact Summary",
        "",
        f"Status: {compact.status}",
        f"Total Alerts: {compact.alert_count}",
        f"Truncated: {compact.truncated}",
        "",
    ]
    
    if compact.severity_counts:
        lines.append("## Severity Counts")
        for sev, count in compact.severity_counts:
            lines.append(f"- {sev}: {count}")
        lines.append("")
    
    if compact.state_counts:
        lines.append("## State Counts")
        for state, count in compact.state_counts:
            lines.append(f"- {state}: {count}")
        lines.append("")
    
    if compact.top_alert_names:
        lines.append(f"## Top Alert Names ({len(compact.top_alert_names)} shown)")
        for name in compact.top_alert_names:
            lines.append(f"- {name}")
        lines.append("")
    
    if compact.affected_namespaces:
        lines.append(f"## Affected Namespaces ({len(compact.affected_namespaces)} shown)")
        for ns in compact.affected_namespaces:
            lines.append(f"- {ns}")
        lines.append("")
    
    if compact.by_cluster:
        lines.append(f"## By Cluster ({len(compact.by_cluster)} clusters)")
        for summary in compact.by_cluster:
            lines.append(f"- {summary.cluster}: {summary.alert_count} alerts")
        lines.append("")
    
    return "\n".join(lines)

"""Reusable fixtures for the SEAM01 production regression tests.

This support module deliberately contains no pytest test functions or test
classes. It supplies deterministic snapshot/source factories and the artifact
prepopulation used by the production-path tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)
from k8s_diag_agent.incident_alert_signal_store import write_alert_signal_artifact

from .incident_current_run_promotion_workset01_support import make_signal

RUN_ID = "run-2026-07-15T0330Z"
SOURCE_IDENTITY = "http://alertmanager:9093"
ALERT_COUNT = 33


def build_thirty_three_distinct_alerts() -> list[NormalizedAlert]:
    """Build the deterministic 33-alert production-shaped fixture."""
    return [
        NormalizedAlert(
            fingerprint=f"alert-2026-07-15T0330Z-{index:03d}",
            alertname="KubePodCrashLooping",
            state="active",
            severity="critical",
            cluster="prod",
            namespace="default",
            service="redis",
            instance=f"redis-{index // 7}",
            starts_at="2026-07-15T03:30:00Z",
            ends_at=None,
            summary=f"Crash loop on redis-{index // 7}",
        )
        for index in range(ALERT_COUNT)
    ]


def write_alerts_round_one(runs_dir: Path) -> list[Any]:
    """Pre-populate artifacts so the next round is identity-matched."""
    signals = [
        make_signal(
            signal_id=f"alert-2026-07-15T0330Z-{index:03d}",
            namespace="default",
            name=f"redis-{index // 7}",
            alertname="KubePodCrashLooping",
        )
        for index in range(ALERT_COUNT)
    ]
    for signal in signals:
        result = write_alert_signal_artifact(root=runs_dir, signal=signal)
        assert result.success
        assert result.is_duplicate is False
    return signals


def build_snapshot(alerts: list[NormalizedAlert]) -> AlertmanagerSnapshot:
    """Build an OK Alertmanager snapshot around normalized alerts."""
    return AlertmanagerSnapshot(
        status=AlertmanagerStatus.OK,
        captured_at="2026-07-15T03:30:00Z",
        source=SOURCE_IDENTITY,
        alert_count=len(alerts),
        alerts=tuple(alerts),
        errors=(),
    )


def build_source() -> AlertmanagerSource:
    """Build the deterministic Alertmanager source fixture."""
    return AlertmanagerSource(
        source_id=SOURCE_IDENTITY,
        endpoint=f"{SOURCE_IDENTITY}/api/v1/alerts",
    )


def gather_log(captured: list[dict[str, Any]]) -> dict[str, Any]:
    """Index captured structured log entries by event name."""
    result: dict[str, Any] = {}
    for entry in captured:
        event = entry.get("event")
        if event is not None:
            result[event] = entry
    return result

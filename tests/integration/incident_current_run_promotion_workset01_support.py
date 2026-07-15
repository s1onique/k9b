"""Shared test support for incident current-run promotion workset01 tests.

This module provides reusable signal builders, artifact persistence helpers,
and common test infrastructure for the workset01 integration test modules.

ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01

Usage:
    from tests.integration.incident_current_run_promotion_workset01_support import (
        make_signal,
        write_signal,
        make_request,
    )
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.domain.identifiers import (
    AlertSignalId,
    HealthRunId,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)
from k8s_diag_agent.incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
)
from k8s_diag_agent.incident_alert_signal_store import (
    write_alert_signal_artifact,
)


def make_signal(
    *,
    signal_id: str,
    status: AlertStatus = AlertStatus.FIRING,
    severity: str = "critical",
    namespace: str = "prod",
    name: str = "redis-0",
    alertname: str = "KubePodCrashLooping",
) -> AlertSignal:
    """Create a test AlertSignal with the given parameters.

    All timestamps default to 2026-07-12 12:00:00 UTC for deterministic test behavior.
    """
    return AlertSignal(
        signal_id=signal_id,
        source_type=AlertSourceType.ALERTMANAGER,
        source_instance="http://alertmanager:9093",
        status=status,
        alertname=alertname,
        severity=severity,
        labels=(("alertname", alertname), ("namespace", namespace), ("pod", name)),
        annotations=(),
        starts_at=datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC),
        ends_at=None,
        received_at=datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC),
        generator_url=None,
        external_url=None,
        raw_payload_artifact_id=None,
        external_fingerprint=signal_id,
        truncation=None,
    )


def write_signal(runs_dir: Path, signal: AlertSignal) -> str:
    """Persist an AlertSignal to the runs directory and return its artifact identity.

    Raises AssertionError if the identity is unexpectedly None.
    """
    result = write_alert_signal_artifact(root=runs_dir, signal=signal)
    identity = result.identity
    assert identity is not None
    return str(identity)


def make_request(
    signal_ids: tuple[str, ...],
    run_id: str = "run-1",
    source_identity: str = "http://alertmanager:9093",
) -> PromoteAlertSignalsRequest:
    """Create a PromoteAlertSignalsRequest with the given signal IDs.

    The request encodes the explicit current-run signal scope for the
    scoped promotion backend.
    """
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )

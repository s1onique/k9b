"""Shared support for the ACT promotion-dispatch outcome integration tests.

Centralises dispatch-stub fixtures and snapshot builders used by
``tests/integration/test_act_k9b_hulk_current_run_promotion_dispatch_outcome01_*.py``
so the test modules themselves stay under the LLM-friendly 500-line
limit.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)
from k8s_diag_agent.incident_alert_signal_store import (
    write_alert_signal_artifact,
)

RUN_ID = "run-2026-07-15T0340Z"
SOURCE_IDENTITY = "http://alertmanager:9093"


def build_alert(i: int) -> NormalizedAlert:
    return NormalizedAlert(
        fingerprint=f"alert-2026-07-15T0340Z-{i:03d}",
        alertname="KubePodCrashLooping",
        state="active",
        severity="critical",
        cluster="prod",
        namespace="prod",
        service="redis",
        instance=f"redis-{i // 7}",
        starts_at="2026-07-15T03:30:00Z",
        ends_at=None,
        summary=f"Crash loop on redis-{i // 7}",
    )


def build_snapshot(alerts: list[NormalizedAlert]) -> AlertmanagerSnapshot:
    return AlertmanagerSnapshot(
        status=AlertmanagerStatus.OK,
        captured_at="2026-07-15T03:30:00Z",
        source=SOURCE_IDENTITY,
        alert_count=len(alerts),
        alerts=tuple(alerts),
        errors=(),
    )


def build_source() -> AlertmanagerSource:
    return AlertmanagerSource(
        source_id=SOURCE_IDENTITY,
        endpoint=f"{SOURCE_IDENTITY}/api/v1/alerts",
    )


def persist_signals(runs_dir: Any, count: int) -> None:
    """Persist ``count`` distinct alert signal artifacts."""
    from .incident_current_run_promotion_workset01_support import make_signal

    (runs_dir / "external-analysis" / "alert-signals").mkdir(
        parents=True, exist_ok=True,
    )
    for i in range(count):
        signal = make_signal(
            signal_id=f"alert-2026-07-15T0340Z-{i:03d}",
            namespace="prod",
            name=f"redis-{i // 7}",
            alertname="KubePodCrashLooping",
        )
        result = write_alert_signal_artifact(root=runs_dir, signal=signal)
        assert result.success


class CapturingLog:
    """Captures log events for telemetry assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, *_args: Any, **kwargs: Any) -> None:
        self.events.append(dict(kwargs))

    def by_event(self, name: str) -> list[dict]:
        return [event for event in self.events if event.get("event") == name]


def stub_dispatch_with_batch(
    monkeypatch: pytest.MonkeyPatch,
    promotion_result: IncidentPromotionResult,
    batch_records: tuple[PromotionRecord, ...] = (),
) -> dict:
    """Stub the dispatcher with controlled result + batch records."""
    from k8s_diag_agent.collect import (
        incident_promotion_batch as batch_module,
    )
    from k8s_diag_agent.collect import (
        incident_promotion_dispatch as dispatch_module,
    )

    captured: dict = {}

    def dispatch_spy(*args: Any, **kwargs: Any) -> Any:
        captured["signal_ids"] = list(kwargs.get("signal_ids") or ())
        return batch_module.PromotionBatch(
            promotion_result=promotion_result,
            promotion_records=batch_records,
            source_kind="alertmanager",
            cluster_context=None,
            snapshot_bundle_id=None,
        )

    monkeypatch.setattr(
        dispatch_module,
        "promote_alert_signals_scoped_for_accumulator",
        dispatch_spy,
    )
    return captured


def stub_dispatch_raises(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
) -> None:
    """Stub the dispatcher to raise ``exc`` on every call."""
    from k8s_diag_agent.collect import (
        incident_promotion_dispatch as dispatch_module,
    )

    def raising_dispatch(*_args: Any, **_kwargs: Any) -> Any:
        raise exc

    monkeypatch.setattr(
        dispatch_module,
        "promote_alert_signals_scoped_for_accumulator",
        raising_dispatch,
    )


def successful_result_template(
    *,
    opened_incidents: int = 2,
    updated_incidents: int = 1,
    opened_incident_ids: tuple[str, ...] = ("inc-1", "inc-2"),
    updated_incident_ids: tuple[str, ...] = ("inc-3",),
) -> IncidentPromotionResult:
    """Return a representative successful dispatcher result."""
    return IncidentPromotionResult(
        ok=True,
        scanned=5,
        firing=5,
        opened_incidents=opened_incidents,
        updated_incidents=updated_incidents,
        skipped_duplicates=2,
        errors=0,
        opened_incident_ids=opened_incident_ids,
        updated_incident_ids=updated_incident_ids,
        promotion_mode=MODE_BACKEND_API,
        promotion_scan_scope="internal_api_alert_signals:scoped",
        incident_access_mode="backend",
    )
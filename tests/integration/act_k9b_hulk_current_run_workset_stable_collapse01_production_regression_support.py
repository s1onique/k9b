"""Reusable fixtures for the stable-collapse production-path tests.

No pytest test functions or test classes live here. The helpers only build
inputs and test-side setup; the integration test modules continue to invoke
the real adapter, persistence, workset, and dispatch implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
from k8s_diag_agent.incident_alert_signal import AlertSignal
from k8s_diag_agent.incident_alert_signal_identity import alert_signal_identity
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    AlertSignalAdapterResult,
)

from .incident_current_run_promotion_workset01_support import make_signal

RUN_ID = "run-2026-07-15T03:30Z"
SOURCE_IDENTITY = "http://alertmanager:9093"
ALERT_FINGERPRINT = "alert-2026-07-15T0330Z-collapse-pair"


@dataclass(frozen=True)
class SameIdentitySignalFixture:
    """Two in-memory signals and the adapter payload for the collapse path."""

    signal_a: AlertSignal
    signal_b: AlertSignal
    canonical_identity: str
    adapt_result_payload: tuple[
        tuple[AlertSignal, ...],
        AlertSignalAdapterResult,
    ]


def make_runs_dir(tmp_path: Path) -> Path:
    """Create the artifact directory shape consumed by production code."""
    runs_dir = tmp_path / "runs"
    (runs_dir / "external-analysis" / "alert-signals").mkdir(
        parents=True,
        exist_ok=True,
    )
    return runs_dir


def build_snapshot_with_single_alert() -> AlertmanagerSnapshot:
    """Build the one-alert snapshot used by the deterministic adapter stub."""
    alert = NormalizedAlert(
        fingerprint=ALERT_FINGERPRINT,
        alertname="KubePodCrashLooping",
        state="active",
        severity="critical",
        cluster="prod",
        namespace="default",
        service="redis",
        instance="redis-0",
        starts_at="2026-07-15T03:30:00Z",
        ends_at=None,
        summary="Crash loop on redis-0",
    )
    return AlertmanagerSnapshot(
        status=AlertmanagerStatus.OK,
        captured_at="2026-07-15T03:30:00Z",
        source=SOURCE_IDENTITY,
        alert_count=1,
        alerts=(alert,),
        errors=(),
    )


def build_source() -> AlertmanagerSource:
    """Build the Alertmanager source fixture."""
    return AlertmanagerSource(
        source_id=SOURCE_IDENTITY,
        endpoint=f"{SOURCE_IDENTITY}/api/v1/alerts",
    )


def duplicate_identity_signal(
    signal: AlertSignal,
    *,
    new_signal_id: str,
) -> AlertSignal:
    """Return a signal with the same canonical identity and a new UUID."""
    return replace(signal, signal_id=new_signal_id)


def build_same_identity_signals() -> SameIdentitySignalFixture:
    """Build the two-signal adapter payload used by the production seam."""
    signal_a = make_signal(
        signal_id="uuid-A",
        namespace="default",
        name="redis-0",
        alertname="KubePodCrashLooping",
    )
    signal_b = duplicate_identity_signal(signal_a, new_signal_id="uuid-B")
    canonical_identity = str(alert_signal_identity(signal_a))
    adapter_payload = (
        (signal_a, signal_b),
        AlertSignalAdapterResult(
            total_alerts=2,
            firing_signals_count=2,
            resolved_signals_count=0,
            skipped_count=0,
            signals_written=0,
            signals_skipped_duplicates=0,
            signals_failed=0,
        ),
    )
    return SameIdentitySignalFixture(
        signal_a=signal_a,
        signal_b=signal_b,
        canonical_identity=canonical_identity,
        adapt_result_payload=adapter_payload,
    )


def patch_scoped_backend_to_promoted(
    monkeypatch,
    *,
    expected_signal_ids: list[str],
    expected_run_id: str = RUN_ID,
    expected_source_identity: str = SOURCE_IDENTITY,
) -> None:
    """Patch the scoped HTTP boundary with a strict contract spy.

    The test exercises the real dispatcher and real accumulator
    codepaths; only the HTTP boundary is mocked because no scheduler
    backend is running in the test process. The spy asserts the
    dispatcher forwarded the exact production values: the run id,
    the source identity, the canonical collapsed signal list, and
    the deduplicated property. This is the same boundary patch that
    existed in the pre-split sibling test
    ``test_act_k9b_incident_current_run_promotion_workset01_scheduler.py``
    (and that test was the reference for the production-path
    invariant this ACT proves); the patch is relocated to the
    support module so it stays scaffolding, not test logic.

    ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

    The stub previously returned the legacy dict shape
    (``ok/scanned/opened_incidents/...``) which the typed scoped
    mapper can no longer decode. The mapper now classifies such a
    payload as
    ``promotion-dispatch-exception-captured /
    promotion-dispatch-outcome-classified`` -- exactly the failure
    mode this regression was supposed to forbid.

    This helper now returns the typed
    ``ScopedPromotionDispatchCompleted`` projection with the
    canonical request fingerprint derived from
    ``scoped_promotion_request_fingerprint`` so the test exercises
    the same production-typed contract
    (:class:`ScopedPromotionAccumulatorCompleted`) that real
    scheduler ingestion drives. The phantom ``alert-signals-promoted``
    event is no longer synthesised from a free-form computation; it
    flows through the production
    ``alert-signals-promoted-via-backend`` audit log emitted by
    ``handle_promote_alert_signals`` in the live deployment.
    """
    from k8s_diag_agent.collect import (
        incident_promotion_backend as backend_module,
    )
    from k8s_diag_agent.collect.promotion_outcomes import PromotionSucceeded
    from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
        ScopedPromotionCompletedProjection,
    )
    from k8s_diag_agent.collect.promotion_scoped_http_seam import (
        ScopedPromotionDispatchCompleted,
        ScopedPromotionReceipt,
        scoped_promotion_request_fingerprint,
    )
    from k8s_diag_agent.domain.identifiers import (
        AlertSignalId,
        HealthRunId,
    )
    from k8s_diag_agent.incident_alert_promotion_binding import (
        BoundScopedPromotionResult,
    )
    from k8s_diag_agent.incident_alert_promotion_contract import (
        IncidentPromotionResult,
        PromoteAlertSignalsRequest,
    )

    def _fake(
        *,
        run_id: str,
        source_identity: str,
        signal_ids: list[str],
        _snapshot_bundle_id: object = None,
    ) -> object:
        # Strict contract assertions on the production-forwarded
        # values. The dispatcher MUST forward the exact production
        # run id, source identity, and the canonical collapsed signal
        # list. Any mismatch is a real production regression, not a
        # test setup issue.
        assert run_id == expected_run_id, (
            f"scoped backend run id mismatch: got {run_id!r}, "
            f"expected {expected_run_id!r}"
        )
        assert source_identity == expected_source_identity, (
            f"scoped backend source identity mismatch: got "
            f"{source_identity!r}, expected {expected_source_identity!r}"
        )
        assert signal_ids == expected_signal_ids, (
            f"scoped backend signal_ids mismatch: got {signal_ids!r}, "
            f"expected {expected_signal_ids!r}"
        )
        assert len(signal_ids) == len(set(signal_ids)), (
            f"scoped backend received duplicate signal_ids: "
            f"{signal_ids!r}"
        )
        # Build the canonical typed promotion request so the bounded
        # ``ScopedPromotionAccumulatorCompleted.__post_init__``
        # validator accepts the stubbed handoff. The request
        # fingerprint MUST be the canonical
        # ``scoped_promotion_request_fingerprint`` (64-char lowercase
        # hex SHA-256) -- a handwritten fingerprint would crash the
        # validator and surface as a
        # ``promotion-dispatch-outcome-classified=fail`` event.
        request = PromoteAlertSignalsRequest(
            run_id=HealthRunId(run_id),
            source_identity=source_identity,
            signal_ids=tuple(
                AlertSignalId(value) for value in signal_ids
            ),
        )
        result = IncidentPromotionResult(
            run_id=request.run_id,
            source_identity=request.source_identity,
            scanned_signal_ids=request.signal_ids,
            opened_incident_ids=(
                "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
            ),
        )
        bound = BoundScopedPromotionResult(
            request=request, result=result
        )
        promotion_outcome = PromotionSucceeded(
            run_id=request.run_id,
            requested_signal_ids=tuple(
                str(s) for s in request.signal_ids
            ),
            records=(),
            diagnosis_incident_ids=(
                "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
            ),
        )
        projection = ScopedPromotionCompletedProjection(
            promotion_outcome=promotion_outcome,
            aggregate_receipt=ScopedPromotionReceipt(bound=bound),
            request_id=f"r3-{run_id}",
            request_fingerprint=scoped_promotion_request_fingerprint(
                request
            ),
        )
        return ScopedPromotionDispatchCompleted(projection=projection)

    monkeypatch.setattr(
        backend_module,
        "promote_alert_signals_via_scoped_backend_api",
        _fake,
    )


def gather_event(
    captured: list[dict[str, Any]],
    event_name: str,
) -> dict[str, Any]:
    """Return a captured structured event by its name."""
    for entry in captured:
        if entry.get("event") == event_name:
            return entry
    raise AssertionError(f"event {event_name!r} not logged")

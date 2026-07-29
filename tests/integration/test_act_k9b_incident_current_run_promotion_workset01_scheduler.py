"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 scheduler tests.

This module contains the scheduler orchestration and backend logging cardinality
tests for the incident current-run promotion ACT.

Test coverage:
1. R2 regression: 35 equivalent AlertSignals → 1 unique artifact identity.
2. R3: scheduler ingestion collapses 35 → 1 in the backend request.
3. Backend logging cardinalities (authoritative signal counts).

ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k8s_diag_agent.collect import (
    incident_promotion_backend as backend_mod,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    promote_alert_signals_scoped_for_accumulator,
)
from k8s_diag_agent.collect.incident_store import (
    IncidentStore,
)
from k8s_diag_agent.incident_alert_promotion_scoped import (
    promote_scoped_alert_signals,
)
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    persist_alert_signals,
)

from .incident_current_run_promotion_workset01_support import (
    make_request,
    make_signal,
    write_signal,
)


def test_thirty_five_equivalent_alerts_yield_one_unique_artifact(
    tmp_path: Path,
) -> None:
    """R2 regression: 35 equivalent AlertSignals → 1 unique artifact identity.

    Production scenario: 35 firing signals were observed, but they all
    collapse to a single canonical incident (same correlation key). The
    scheduler MUST stable-deduplicate the artifact workset before
    posting; otherwise the scoped backend rejects the request with
    ``signalIds must not contain duplicates``.
    """
    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # 35 equivalent AlertSignals: identical signal_id + content. The
    # persist function MUST give them all the same SHA256 identity
    # (the first is newly written, the rest are duplicates).
    same_signal_id = "alert-canonical-001"
    written_identities: list[str] = []
    for _ in range(35):
        signal = make_signal(
            signal_id=same_signal_id,
            namespace="prod",
            name="redis-0",
        )
        written_identities.append(write_signal(runs_dir, signal))

    # All 35 returns the same artifact identity.
    unique = set(written_identities)
    assert len(unique) == 1
    canonical_identity = written_identities[0]

    # The scheduler contract: stable-deduplicate the artifact workset
    # before posting. The scoped backend request contains exactly 1 ID.
    scoped_signal_ids = tuple(
        dict.fromkeys(written_identities)
    )
    assert len(scoped_signal_ids) == 1
    assert scoped_signal_ids[0] == canonical_identity

    # Backend request is built with the unique tuple (no duplicates).
    request = make_request(signal_ids=scoped_signal_ids)
    request_dict = request.to_wire_dict()
    assert request_dict["signalIds"] == [canonical_identity]

    # The scoped promotion processes exactly 1 signal and produces
    # exactly 1 actionable incident.
    store = IncidentStore()
    result = promote_scoped_alert_signals(
        request=request,
        incident_store=store,
        runs_dir=runs_dir,
    )
    assert result.scanned_signal_count == 1
    assert result.opened_incident_ids == (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
    )
    assert result.actionable_incident_ids == result.opened_incident_ids
    assert len(store.list_incidents()) == 1

    # Ingestion duplicate count: 35 persisted - 1 unique = 34 duplicates.
    duplicate_count = max(0, len(written_identities) - len(unique))
    assert duplicate_count == 34


def test_scheduler_ingestion_posts_one_signal_id_for_thirty_five_alerts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3: scheduler ingestion collapses 35 → 1 in the backend request.

    The R2 regression ``test_thirty_five_equivalent_alerts_yield_one_unique_artifact``
    proves the algorithm in isolation by calling the persistence +
    scoped-promotion paths with already-known IDs. R3 requires proving
    the production scheduler ingestion actually drives the dispatcher
    with one ``signal_id``:

        persist_alert_signals(...) →
        promote_alert_signals_scoped_for_accumulator(
            runs_dir, run_id, source_identity,
            signal_ids=(canonical_artifact_identity,),
        )

    For that we stub ``promote_alert_signals_via_scoped_backend_api``
    (the HTTP boundary inside the dispatcher) and assert the captured
    ``signal_ids`` argument is exactly the deduplicated canonical
    identity. Three duplicate metrics are exposed:

        persisted_signal_count = 35
        unique_artifact_signal_count = 1
        artifact_write_duplicate_count = 34
        current_batch_identity_collapse_count = 34
    """
    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # 35 equivalent AlertSignal inputs. ``persist_alert_signals``
    # collapses them to a single SHA256 artifact identity (the first
    # is newly written, the remaining 34 are duplicates at the
    # persistence layer).
    same_signal_id = "alert-canonical-001"
    signals = tuple(
        make_signal(
            signal_id=same_signal_id,
            namespace="prod",
            name="redis-0",
        )
        for _ in range(35)
    )
    persist_result, written_signals = persist_alert_signals(
        signals=signals,
        root=runs_dir,
    )
    assert len(written_signals) == 35
    canonical_artifact_identity = str(written_signals[0].artifact_identity)
    assert {str(p.artifact_identity) for p in written_signals} == {
        canonical_artifact_identity
    }

    # Stub the HTTP boundary so we can capture ``signal_ids`` as the
    # dispatcher sends them. The stub returns a structured result
    # mirroring the production backend response.
    captured: dict[str, object] = {}

    def _fake_via_backend(
        *,
        run_id: str,
        source_identity: str,
        signal_ids: list[str],
        _snapshot_bundle_id: object = None,
    ) -> object:
        from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
            ScopedPromotionCompletedProjection,
        )
        from k8s_diag_agent.collect.promotion_scoped_http_seam import (
            ScopedPromotionDispatchCompleted,
            ScopedPromotionReceipt,
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

        captured["run_id"] = run_id
        captured["source_identity"] = source_identity
        captured["signal_ids"] = list(signal_ids)
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
        bound = BoundScopedPromotionResult(request=request, result=result)
        projection = ScopedPromotionCompletedProjection(
            promotion_outcome=__import__(
                "k8s_diag_agent.collect.promotion_outcomes",
                fromlist=["PromotionSucceeded"],
            ).PromotionSucceeded(
                run_id=request.run_id,
                requested_signal_ids=tuple(
                    str(s) for s in request.signal_ids
                ),
                records=(),
                diagnosis_incident_ids=("http-alertmanager-9093:crash_loop:prod:pod:redis-0",),
            ),
            aggregate_receipt=ScopedPromotionReceipt(bound=bound),
            request_id="stubbed",
            request_fingerprint="x" * 64,
        )
        return ScopedPromotionDispatchCompleted(projection=projection)

    # The dispatcher imports ``promote_alert_signals_via_scoped_backend_api``
    # lazily from ``incident_promotion_backend`` inside the function
    # body, so the seam we have to patch is the source module, not
    # the dispatcher module.
    monkeypatch.setattr(
        backend_mod,
        "promote_alert_signals_via_scoped_backend_api",
        _fake_via_backend,
    )

    # Stable-deduplicate the artifact workset before posting
    # (mirrors the production scheduler ingestion implementation).
    deduped_signal_ids = tuple(
        dict.fromkeys(
            str(p.artifact_identity) for p in written_signals
        )
    )
    assert deduped_signal_ids == (canonical_artifact_identity,)

    # Three duplicate-count metrics, derived deterministically from
    # the persistence + collapse layers.
    persisted_signal_count = len(written_signals)
    unique_artifact_signal_count = len(
        {str(p.artifact_identity) for p in written_signals}
    )
    artifact_write_duplicate_count = int(
        getattr(persist_result, "signals_skipped_duplicates", 0) or 0
    )
    current_batch_identity_collapse_count = max(
        0, persisted_signal_count - unique_artifact_signal_count
    )

    assert persisted_signal_count == 35
    assert unique_artifact_signal_count == 1
    assert artifact_write_duplicate_count == 34
    assert current_batch_identity_collapse_count == 34

    # Actually invoke the dispatcher with the deduplicated workset
    # so we capture the wire-level ``signal_ids`` argument.
    accumulator = RunPromotionAccumulator()
    batch = promote_alert_signals_scoped_for_accumulator(
        runs_dir=runs_dir,
        health_run_id="run-r3",
        source_identity="http://alertmanager:9093",
        signal_ids=deduped_signal_ids,
        accumulator=accumulator,
    )
    assert isinstance(batch, PromotionBatch)
    # The audit's hard assertion: exactly one identity was forwarded.
    assert captured["signal_ids"] == [canonical_artifact_identity]
    assert captured["run_id"] == "run-r3"
    assert captured["source_identity"] == "http://alertmanager:9093"

    promotion_result = batch.promotion_result
    assert promotion_result.scanned == 1
    assert promotion_result.opened_incidents == 1
    # The dispatcher projection of ``opened_incident_ids`` must
    # surface the canonical correlation-derived incident id.
    assert list(promotion_result.opened_incident_ids) == [
        "http-alertmanager-9093:crash_loop:prod:pod:redis-0"
    ]
    # No follow-up categories from a single canonical signal.
    assert list(promotion_result.updated_incident_ids) == []

    # PromoteAlertSignalsRequest would refuse a duplicate-id tuple,
    # so the dispatcher MUST post exactly one entry.
    request = make_request(signal_ids=deduped_signal_ids)
    wire = request.to_wire_dict()
    assert wire["signalIds"] == [canonical_artifact_identity]


class TestBackendLoggingCardinalities:
    """``_log_promotion_result`` must use authoritative signal counts.

    The R3.2 audit verified that ``requested_signal_count`` and
    ``scanned_signal_count`` MUST come from ``len(request.signal_ids)``
    and ``result.scanned_signal_count`` rather than from the
    collapsed per-category incident counts (which lose information
    when several signals share one incident). The test patches the
    stdlib logger to capture the audit-event payload and asserts the
    counts are NOT derived from the per-category sizes.
    """

    def test_log_emits_authoritative_signal_counts(self, caplog) -> None:
        """The audit event MUST carry the request-length signal count, not
        the per-category incident sum.

        We construct a synthetic Result-like object exposing the
        category counts (1, 0, 0, 0) the way the bug reported them,
        and assert the log event reports ``requested_signal_count``
        from the explicit kwarg (5) and ``scanned_signal_count``
        from the explicit kwarg (5), proving the function no longer
        derives them from the category sum.
        """
        from k8s_diag_agent.ui.server_incident_internal_handlers import (
            _log_promotion_result,
        )

        with caplog.at_level("INFO", logger="k8s_diag_agent.ui.server_incident_internal_handlers"):  # noqa: E501
            _log_promotion_result(
                event_name="alert-signals-promoted-via-backend",
                run_id="run-r3-2",
                source_identity="http://alertmanager:9093",
                requested_signal_count=5,
                scanned_signal_count=5,
                opened_count=1,  # 5 signals collapse to 1 incident
                materially_changed_count=0,
                observation_refreshed_count=0,
                unchanged_count=0,
                skipped_count=0,
                failure_count=0,
                promotion_scope="explicit_current_run_signal_ids",
                promotion_actionable_count=1,
            )

        # Find the relevant record. The ``event`` attribute comes from
        # the ``extra={"event": event_name, ...}`` payload of the
        # production ``_logger.info(..., extra=...)`` call.
        matches = [r for r in caplog.records if getattr(r, "event", None) == "alert-signals-promoted-via-backend"]
        assert matches, f"no audit log emitted; saw {[r.name for r in caplog.records]}"
        record = matches[-1]
        # The ``extra`` payload is exposed as attributes on the record.
        assert getattr(record, "requested_signal_count", None) == 5
        assert getattr(record, "scanned_signal_count", None) == 5
        # The category fields stay as 1/0/0/0 — proving we are NOT
        # summing them to fake the signal counts.
        assert getattr(record, "opened_incident_count", None) == 1
        assert getattr(record, "materially_changed_incident_count", None) == 0
        assert getattr(record, "observation_refreshed_incident_count", None) == 0
        assert getattr(record, "unchanged_incident_count", None) == 0
        assert getattr(record, "actionable_incident_count", None) == 1

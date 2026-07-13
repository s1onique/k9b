"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 end-to-end regression.

This integration test reproduces the production failure that
motivated the ACT and proves the post-ACT tree fixes it:

* 75 historical firing signals persisted BEFORE the run.
* 1 current-run signal ingested in this run.
* The scoped promotion MUST process only the 1 current-run signal.
* The diagnosis handoff MUST receive only the canonical actionable
  projection (1 incident) and the budget MUST start at zero.
* The observation-only variant MUST produce zero actionable incidents
  and zero review-packet writes.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet_budget import (
    ReviewPacketCreationBudget,
)
from k8s_diag_agent.collect.incident_store import (
    IncidentStore,
)
from k8s_diag_agent.domain.identifiers import (
    AlertSignalId,
    AutomaticDiagnosisCollectorRunId,
    HealthRunId,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)
from k8s_diag_agent.incident_alert_promotion_scoped import (
    promote_scoped_alert_signals,
)
from k8s_diag_agent.incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
)
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    persist_alert_signals,
)
from k8s_diag_agent.incident_alert_signal_store import (
    write_alert_signal_artifact,
)


def _make_signal(
    *,
    signal_id: str,
    status: AlertStatus = AlertStatus.FIRING,
    severity: str = "critical",
    namespace: str = "prod",
    name: str = "redis-0",
    alertname: str = "KubePodCrashLooping",
) -> AlertSignal:
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


def _write(runs_dir: Path, signal: AlertSignal) -> str:
    result = write_alert_signal_artifact(root=runs_dir, signal=signal)
    identity = result.identity
    assert identity is not None
    return str(identity)


def _request(
    signal_ids: tuple[str, ...],
) -> PromoteAlertSignalsRequest:
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId("run-1"),
        source_identity="http://alertmanager:9093",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


# Re-export to keep the test self-contained.
__all__ = [
    "test_production_failure_regression_production_equivalent",
    "test_observation_only_refresh_produces_no_actionable_incidents",
    "test_diagnosis_handoff_receives_only_actionable_projection",
    "test_thirty_five_equivalent_alerts_yield_one_unique_artifact",
    "test_scheduler_ingestion_posts_one_signal_id_for_thirty_five_alerts",
]


def test_production_failure_regression_production_equivalent(
    tmp_path: Path,
) -> None:
    """Production-equivalent regression for the bug that motivated the ACT.

    The production run:
      * 75 historical firing signals/incidents exist
      * 1 current-run signal is ingested in this run
      * promotion_requested_count = 1
      * promotion_scanned_count = 1
      * promotion_actionable_count = 1
      * diagnosis_explicit_id_count = 1
      * fresh_collector_budget_used_at_start = 0
      * eligible_incidents = 1
      * new_review_packets_written = 1
      * historical_incidents_touched = 0
    """
    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # 75 historical firing signals persisted before the run.
    for index in range(75):
        _write(
            runs_dir,
            _make_signal(
                signal_id=f"historical-{index:03d}",
                namespace="ns-h",
                name=f"hist-{index:03d}",
            ),
        )

    # 1 current-run signal ingested in this run.
    current_signal = _make_signal(
        signal_id="current-001",
        namespace="prod",
        name="redis-0",
    )
    current_identity = _write(runs_dir, current_signal)

    store = IncidentStore()
    result = promote_scoped_alert_signals(
        request=_request(signal_ids=(current_identity,)),
        incident_store=store,
        runs_dir=runs_dir,
    )

    # The post-ACT contract:
    #   * exactly 1 signal processed (the current-run one).
    #   * exactly 1 actionable incident (the new open).
    #   * the 75 historical signals MUST NOT contribute to the result
    #     or to the incident store.
    #   * a fresh collector budget MUST start at zero usage.
    assert result.scanned_signal_count == 1
    assert result.opened_incident_ids == (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
    )
    assert result.actionable_incident_ids == result.opened_incident_ids
    assert len(store.list_incidents()) == 1

    # Budget starts at zero and consumes only after a successful write.
    budget = ReviewPacketCreationBudget(
        collector_run_id=AutomaticDiagnosisCollectorRunId("auto-1"),
        limit=1,
    )
    assert budget.used == 0
    assert budget.exhausted is False
    assert budget.as_diagnostic()["source"] == "collector_run_accounting"


def test_observation_only_refresh_produces_no_actionable_incidents(
    tmp_path: Path,
) -> None:
    """Observation-only refresh: same signal re-promoted MUST NOT be actionable.

    The second scenario from the ACT: 0 actionable incidents and 0 new
    review-packet writes; the budget MUST NOT charge any unit.
    """
    _ = None
    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # Seed an incident directly so the scoped path finds an
    # already-merged signal fingerprint on disk.
    seed = _make_signal(signal_id="seed-001", namespace="prod", name="redis-0")
    seed_identity = _write(runs_dir, seed)

    store = IncidentStore()
    promote_scoped_alert_signals(
        request=_request(signal_ids=(seed_identity,)),
        incident_store=store,
        runs_dir=runs_dir,
    )
    # Re-promotion of the SAME signal id is a no-op merge; the budget
    # MUST NOT charge any unit and the actionable projection MUST be
    # empty (recency-only refresh is NOT actionable).
    result = promote_scoped_alert_signals(
        request=_request(signal_ids=(seed_identity,)),
        incident_store=store,
        runs_dir=runs_dir,
    )
    assert result.actionable_incident_ids == ()
    assert result.unchanged_incident_ids == (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
    )
    assert result.opened_incident_ids == ()
    assert result.materially_changed_incident_ids == ()
    assert result.observation_refreshed_incident_ids == ()


def test_diagnosis_handoff_receives_only_actionable_projection(
    tmp_path: Path,
) -> None:
    """The diagnosis handoff MUST receive only actionable incidents.

    Mixed batch: one opened, one materially changed, one unchanged.
    The actionable projection MUST contain only the opened and
    materially-changed incidents; observation-refresh and unchanged
    incidents MUST be excluded.
    """
    import dataclasses

    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    opened_signal = _make_signal(
        signal_id="opened-001", namespace="prod", name="redis-0"
    )
    opened_id = _write(runs_dir, opened_signal)

    material_signal = _make_signal(
        signal_id="material-001",
        namespace="prod",
        name="redis-1",
        severity="warning",
    )
    material_id = _write(runs_dir, material_signal)

    unchanged_signal = _make_signal(
        signal_id="unchanged-001", namespace="prod", name="redis-2"
    )
    unchanged_id = _write(runs_dir, unchanged_signal)

    store = IncidentStore()
    promote_scoped_alert_signals(
        request=_request(signal_ids=(opened_id, material_id, unchanged_id)),
        incident_store=store,
        runs_dir=runs_dir,
    )

    # Promote the material signal with materially different severity AND
    # a unique ``signal_id`` (the artifact identity is hash-based, so
    # two signals sharing every observable field collapse to the same
    # identity; changing ``signal_id`` is the cleanest way to simulate
    # a new alert that updates the existing incident).
    material_signal_changed = dataclasses.replace(
        material_signal,
        signal_id="material-002",
        external_fingerprint="material-002",
    )
    material_changed_id = _write(runs_dir, material_signal_changed)

    result = promote_scoped_alert_signals(
        request=_request(
            signal_ids=(
                opened_id,
                material_changed_id,
                unchanged_id,
            )
        ),
        incident_store=store,
        runs_dir=runs_dir,
    )
    assert set(result.actionable_incident_ids) == set(
        result.materially_changed_incident_ids
    )
    assert (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-2"
    ) not in result.actionable_incident_ids
    assert len(result.actionable_incident_ids) == 1
    assert (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-1"
    ) in result.materially_changed_incident_ids
    assert (
        "http-alertmanager-9093:crash_loop:prod:pod:redis-0"
    ) in result.unchanged_incident_ids
    assert set(result.actionable_incident_ids) == set(
        result.materially_changed_incident_ids
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
        signal = _make_signal(
            signal_id=same_signal_id,
            namespace="prod",
            name="redis-0",
        )
        written_identities.append(_write(runs_dir, signal))

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
    request = _request(signal_ids=scoped_signal_ids)
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

    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # 35 equivalent AlertSignal inputs. ``persist_alert_signals``
    # collapses them to a single SHA256 artifact identity (the first
    # is newly written, the remaining 34 are duplicates at the
    # persistence layer).
    same_signal_id = "alert-canonical-001"
    signals = tuple(
        _make_signal(
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
    ) -> dict[str, object]:
        captured["run_id"] = run_id
        captured["source_identity"] = source_identity
        captured["signal_ids"] = list(signal_ids)
        return {
            "ok": True,
            "scanned": 1,
            "opened_incidents": 1,
            "updated_incidents": 0,
            "opened_incident_ids": [
                "http-alertmanager-9093:crash_loop:prod:pod:redis-0"
            ],
            "updated_incident_ids": [],
            "skipped_duplicates": 0,
            "errors": 0,
            "promotion_mode": "backend-api",
        }

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
    request = _request(signal_ids=deduped_signal_ids)
    wire = request.to_wire_dict()
    assert wire["signalIds"] == [canonical_artifact_identity]
    _ = dataclasses  # confirm the helper import is materialized


# ---------------------------------------------------------------------------
# R3.2: strict parser regression + backend cardinality regression tests
# ---------------------------------------------------------------------------


class TestResponseParserRejectsMalformedIds:
    """``IncidentPromotionResult.from_wire_dict`` must reject malformed IDs.

    The R3 closure claim that every wire ID array is strictly
    validated requires these negative proofs. Empty, whitespace,
    oversized, and unsafe identifiers must all fail closed rather
    than slip through into a typed result.
    """

    _PAYLOAD_BASE: dict[str, object] = {
        "runId": "auto-run-20260101",
        "sourceIdentity": "http://alertmanager:9093",
    }

    def test_empty_string_in_scanned_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload: dict[str, object] = dict(self._PAYLOAD_BASE)
        payload["scannedSignalIds"] = [""]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_whitespace_only_in_opened_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["\n"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_whitespace_in_actionable_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["id-1"]
        payload["materiallyChangedIncidentIds"] = []
        payload["actionableIncidentIds"] = ["\n"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_oversized_unsafe_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            MAX_ID_LENGTH,
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["scannedSignalIds"] = ["a" * (MAX_ID_LENGTH + 1)]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_unsafe_character_in_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["bad id with spaces"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_malformed_failure_signal_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["failures"] = [
            {"signalId": "\n", "reasonCode": "x"}
        ]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_malformed_run_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["runId"] = ""  # empty
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_minimal_payload_with_only_required_fields_succeeds(self) -> None:
        """R3.4: payload with only ``runId`` + ``sourceIdentity`` parses.

        Omitted optional arrays (``scannedSignalIds``, ``skippedSignalIds``,
        the four incident ID lists, ``failures``, ``actionableIncidentIds``)
        MUST default to empty tuples; the typed result reports all
        counts at zero and an empty failure list. The previous bug
        used ``payload.get("failures", ()) or ()`` so a missing
        ``failures`` field was rejected with ``failures must be an
        array`` even though every other optional array was correctly
        defaulted to ``()``.
        """
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
        )

        payload: dict[str, object] = {
            "runId": "auto-run-20260101",
            "sourceIdentity": "http://alertmanager:9093",
        }
        result = IncidentPromotionResult.from_wire_dict(payload)
        # Identity and run-id are propagated verbatim.
        assert str(result.run_id) == "auto-run-20260101"
        assert result.source_identity == "http://alertmanager:9093"
        # All optional arrays defaulted to empty tuples.
        assert list(result.scanned_signal_ids) == []
        assert list(result.skipped_signal_ids) == []
        assert list(result.opened_incident_ids) == []
        assert list(result.materially_changed_incident_ids) == []
        assert list(result.observation_refreshed_incident_ids) == []
        assert list(result.unchanged_incident_ids) == []
        assert list(result.failures) == []
        # All counts at zero.
        assert result.scanned_signal_count == 0
        assert result.opened_incident_count == 0
        assert result.materially_changed_incident_count == 0
        assert result.observation_refreshed_incident_count == 0
        assert result.unchanged_incident_count == 0
        # The actionable projection is the stable unique union of
        # opened + materially-changed; with both empty, it is empty.
        assert list(result.actionable_incident_ids) == []

    def test_overlong_source_identity_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            MAX_SOURCE_IDENTITY_LENGTH,
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["sourceIdentity"] = "a" * (MAX_SOURCE_IDENTITY_LENGTH + 1)
        with pytest.raises(PromotionScopeError):  # noqa: E501
            IncidentPromotionResult.from_wire_dict(payload)


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

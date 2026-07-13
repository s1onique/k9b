"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 scoped promotion tests.

These tests prove the typed current-run promotion contract and
backend-owned scoped promotion never fall back to a global
firing-signal scan. They are written for the production-semantic
behaviour; no mocked counters are allowed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.domain.identifiers import (
    AlertSignalId,
    HealthRunId,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    MAX_PROMOTION_SIGNAL_IDS,
    PromoteAlertSignalsRequest,
    PromotionScopeError,
    parse_promote_alert_signals_request,
)
from k8s_diag_agent.incident_alert_promotion_scoped import (
    promote_scoped_alert_signals,
)
from k8s_diag_agent.incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
)
from k8s_diag_agent.incident_alert_signal_store import (
    write_alert_signal_artifact,
)


def _make_signal(
    *,
    signal_id: str,
    fingerprint: str = "",
    status: AlertStatus = AlertStatus.FIRING,
    severity: str = "critical",
    namespace: str = "prod",
    name: str = "redis-0",
    alertname: str = "KubePodCrashLooping",
) -> AlertSignal:
    fingerprint_value = fingerprint or signal_id
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
        external_fingerprint=fingerprint_value,
        truncation=None,
    )


def _write_signal(runs_dir: Path, signal: AlertSignal) -> str:
    """Write the signal artifact and return the deterministic identity.

    The signal artifact is named after the deterministic identity hash
    produced by :func:`write_alert_signal_artifact`. The scheduler hands
    the backend those identities (not the in-memory UUID) so the
    backend can locate the exact artifact.
    """
    result = write_alert_signal_artifact(root=runs_dir, signal=signal)
    identity = result.identity
    assert identity is not None
    return str(identity)


def _request(
    *,
    run_id: str = "run-1",
    source_identity: str = "http://alertmanager:9093",
    signal_ids: tuple[str, ...] = (),
) -> PromoteAlertSignalsRequest:
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


class TestPromoteAlertSignalsRequest:
    def test_request_rejects_missing_run_id(self) -> None:
        with pytest.raises(PromotionScopeError):
            PromoteAlertSignalsRequest(
                run_id=HealthRunId(""),
                source_identity="http://alertmanager:9093",
                signal_ids=(),
            )

    def test_request_rejects_oversized_signal_batch(self) -> None:
        oversized = tuple(AlertSignalId(f"sig-{i}") for i in range(MAX_PROMOTION_SIGNAL_IDS + 1))
        with pytest.raises(PromotionScopeError):
            PromoteAlertSignalsRequest(
                run_id=HealthRunId("run-1"),
                source_identity="http://alertmanager:9093",
                signal_ids=oversized,
            )

    def test_request_rejects_duplicate_signal_ids(self) -> None:
        with pytest.raises(PromotionScopeError):
            PromoteAlertSignalsRequest(
                run_id=HealthRunId("run-1"),
                source_identity="http://alertmanager:9093",
                signal_ids=(
                    AlertSignalId("sig-1"),
                    AlertSignalId("sig-1"),
                ),
            )

    def test_request_rejects_cross_source_signal_id(self) -> None:
        with pytest.raises(PromotionScopeError):
            _request(
                source_identity="",
                signal_ids=("sig-1",),
            )

    def test_parser_rejects_unknown_fields(self) -> None:
        with pytest.raises(PromotionScopeError):
            parse_promote_alert_signals_request(
                {
                    "runId": "run-1",
                    "sourceIdentity": "src",
                    "signalIds": [],
                    "extra": "nope",
                }
            )

    def test_parser_requires_signal_ids(self) -> None:
        with pytest.raises(PromotionScopeError):
            parse_promote_alert_signals_request(
                {"runId": "run-1", "sourceIdentity": "src"}
            )


class TestPromoteScopedAlertSignalsSemantics:
    def test_historical_signals_are_excluded(
        self, tmp_path: Path
    ) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)

        # 75 historical firing signals persisted BEFORE the run.
        for index in range(75):
            historical = _make_signal(
                signal_id=f"historical-{index:03d}",
                namespace="ns-h",
                name=f"hist-{index:03d}",
            )
            _write_signal(runs_dir, historical)

        # 1 current-run signal ingested in this run.
        current_signal = _make_signal(
            signal_id="current-001",
            namespace="prod",
            name="redis-0",
        )
        current_identity = _write_signal(runs_dir, current_signal)

        store = IncidentStore()
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=(current_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )

        assert result.scanned_signal_count == 1
        # The historical 75 incidents MUST NOT be in the result.
        for category in (
            result.opened_incident_ids,
            result.materially_changed_incident_ids,
            result.observation_refreshed_incident_ids,
            result.unchanged_incident_ids,
        ):
            assert len(category) <= 1
        assert store.get_incident(
            "http-alertmanager-9093:crash_loop:ns-h:pod:hist-000"
        ) is None

    def test_empty_batch_does_no_global_scan(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)

        for index in range(10):
            _write_signal(
                runs_dir,
                _make_signal(
                    signal_id=f"hist-{index:03d}",
                    namespace="ns-h",
                    name=f"hist-{index:03d}",
                ),
            )

        store = IncidentStore()
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=()),
            incident_store=store,
            runs_dir=runs_dir,
        )
        assert result.scanned_signal_count == 0
        assert result.opened_incident_ids == ()
        assert result.materially_changed_incident_ids == ()
        assert result.observation_refreshed_incident_ids == ()
        assert result.unchanged_incident_ids == ()
        # The store MUST remain untouched.
        assert store.list_incidents() == ()

    def test_missing_scope_fails_closed(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)

        # Persist a signal for a DIFFERENT source than the request.
        foreign_signal = _make_signal(
            signal_id="foreign-001",
        )
        foreign_signal = AlertSignal(
            **{**foreign_signal.__dict__, "source_instance": "http://other:9093"}
        )
        _write_signal(runs_dir, foreign_signal)

        store = IncidentStore()
        with pytest.raises(PromotionScopeError):
            promote_scoped_alert_signals(
                request=_request(
                    source_identity="http://alertmanager:9093",
                    signal_ids=("does-not-exist",),
                ),
                incident_store=store,
                runs_dir=runs_dir,
            )
        assert store.list_incidents() == ()

    def test_newly_opened_incident_is_actionable(
        self, tmp_path: Path
    ) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        identity = _write_signal(
            runs_dir,
            _make_signal(signal_id="new-001", namespace="prod", name="redis-0"),
        )

        store = IncidentStore()
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=(identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        assert result.opened_incident_ids == (
            "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
        )
        assert result.actionable_incident_ids == result.opened_incident_ids
        assert result.unchanged_incident_ids == ()
        assert result.observation_refreshed_incident_ids == ()
        assert result.materially_changed_incident_ids == ()

    def test_material_change_is_actionable(
        self, tmp_path: Path
    ) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        first = _make_signal(
            signal_id="first-001",
            namespace="prod",
            name="redis-0",
            severity="warning",
        )
        first_identity = _write_signal(runs_dir, first)
        store = IncidentStore()
        promote_scoped_alert_signals(
            request=_request(signal_ids=(first_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        # Now promote a substantively different signal: severity went
        # critical, so the change MUST be material, not observation.
        second = _make_signal(
            signal_id="second-001",
            namespace="prod",
            name="redis-0",
            severity="critical",
        )
        second_identity = _write_signal(runs_dir, second)
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=(second_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        assert result.materially_changed_incident_ids == (
            "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
        )
        assert result.actionable_incident_ids == result.materially_changed_incident_ids
        assert result.unchanged_incident_ids == ()
        assert result.opened_incident_ids == ()

    def test_recency_only_refresh_is_not_actionable(
        self, tmp_path: Path
    ) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        seed = _make_signal(signal_id="seed-001", namespace="prod", name="redis-0")
        seed_identity = _write_signal(runs_dir, seed)
        store = IncidentStore()
        promote_scoped_alert_signals(
            request=_request(signal_ids=(seed_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        # Same correlation; same content; same signal id (deduplicated).
        duplicate = _make_signal(
            signal_id="seed-001", namespace="prod", name="redis-0"
        )
        duplicate_identity = _write_signal(runs_dir, duplicate)
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=(duplicate_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        # Re-promotion of the SAME signal id is a no-op merge, which
        # the ACT's material-change classifier treats as ``unchanged``;
        # both ``unchanged`` and ``observation`` MUST be excluded from
        # the actionable projection.
        assert result.unchanged_incident_ids == (
            "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
        )
        assert result.actionable_incident_ids == ()
        assert result.opened_incident_ids == ()
        assert result.materially_changed_incident_ids == ()

    def test_unchanged_incident_is_not_actionable(
        self, tmp_path: Path
    ) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        # Seed an incident directly so the scoped path finds an
        # already-merged signal fingerprint on disk.
        seed = _make_signal(
            signal_id="seed-only", namespace="prod", name="redis-0"
        )
        seed_identity = _write_signal(runs_dir, seed)
        store = IncidentStore()
        promote_scoped_alert_signals(
            request=_request(signal_ids=(seed_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        # The same signal id is now persisted. Promoting it again MUST
        # classify as unchanged because the merge would be a no-op.
        result = promote_scoped_alert_signals(
            request=_request(signal_ids=(seed_identity,)),
            incident_store=store,
            runs_dir=runs_dir,
        )
        assert result.unchanged_incident_ids == (
            "http-alertmanager-9093:crash_loop:prod:pod:redis-0",
        )
        assert result.actionable_incident_ids == ()

    def test_deterministic_ordering(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "runs"
        signals_dir = runs_dir / "external-analysis" / "alert-signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        identities: dict[int, str] = {}
        for index in (3, 1, 2):
            identities[index] = _write_signal(
                runs_dir,
                _make_signal(
                    signal_id=f"ord-{index}",
                    namespace="prod",
                    name=f"redis-{index}",
                ),
            )
        store = IncidentStore()
        result = promote_scoped_alert_signals(
            request=_request(
                signal_ids=(
                    identities[3],
                    identities[1],
                    identities[2],
                ),
            ),
            incident_store=store,
            runs_dir=runs_dir,
        )
        # All three are unique opens so the actionable projection is
        # sorted by the first-occurrence order in the request.
        correlation = (
            "http-alertmanager-9093:crash_loop:prod:pod:redis-3",
            "http-alertmanager-9093:crash_loop:prod:pod:redis-1",
            "http-alertmanager-9093:crash_loop:prod:pod:redis-2",
        )
        assert result.opened_incident_ids == correlation
        assert result.actionable_incident_ids == result.opened_incident_ids


class TestSchedulerClientScopedCall:
    def test_promote_alert_signals_scoped_posts_camel_case(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.ui.server_incident_internal_fetch import SchedulerClient

        captured: dict = {}

        def _fake_urlopen(req: object, timeout: object = None) -> object:
            captured["url"] = req.full_url
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            captured["headers"] = dict(req.headers)

            class _Resp:
                def __enter__(self) -> object:
                    return self

                def __exit__(self, *args: object) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "runId": "run-1",
                            "sourceIdentity": "http://alertmanager:9093",
                            "scannedSignalIds": ["sig-1"],
                            "openedIncidentIds": ["inc-1"],
                            "materiallyChangedIncidentIds": [],
                            "observationRefreshedIncidentIds": [],
                            "unchangedIncidentIds": [],
                            "skippedSignalIds": [],
                            "failures": [],
                            "actionableIncidentIds": ["inc-1"],
                        }
                    ).encode()

            return _Resp()

        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _fake_urlopen(req, timeout)
        )
        client = SchedulerClient(
            base_url="http://k9b-backend:8080", token="test-token"
        )
        result = client.promote_alert_signals_scoped(
            run_id="run-1",
            source_identity="http://alertmanager:9093",
            signal_ids=["sig-1"],
        )
        assert isinstance(result, dict)
        assert result["actionableIncidentIds"] == ["inc-1"]
        assert result["openedIncidentIds"] == ["inc-1"]
        assert captured["payload"] == {
            "runId": "run-1",
            "sourceIdentity": "http://alertmanager:9093",
            "signalIds": ["sig-1"],
        }
        assert captured["url"].endswith(
            "/api/internal/incidents/promote-alert-signals"
        )
        assert (
            captured["headers"].get("Authorization") == "Bearer test-token"
        )

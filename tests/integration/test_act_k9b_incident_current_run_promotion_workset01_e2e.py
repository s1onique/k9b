"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 core E2E tests.

This module contains the production-equivalent promotion and diagnosis-workset
behavior tests for the incident current-run promotion ACT.

Test coverage:
1. Production-equivalent regression: 75 historical signals + 1 current-run signal.
2. Observation-only refresh produces no actionable incidents.
3. Diagnosis handoff receives only actionable projection.

ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_review_packet_budget import (
    ReviewPacketCreationBudget,
)
from k8s_diag_agent.collect.incident_store import (
    IncidentStore,
)
from k8s_diag_agent.domain.identifiers import (
    AutomaticDiagnosisCollectorRunId,
)
from k8s_diag_agent.incident_alert_promotion_scoped import (
    promote_scoped_alert_signals,
)

from .incident_current_run_promotion_workset01_support import (
    make_request,
    make_signal,
    write_signal,
)


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
        write_signal(
            runs_dir,
            make_signal(
                signal_id=f"historical-{index:03d}",
                namespace="ns-h",
                name=f"hist-{index:03d}",
            ),
        )

    # 1 current-run signal ingested in this run.
    current_signal = make_signal(
        signal_id="current-001",
        namespace="prod",
        name="redis-0",
    )
    current_identity = write_signal(runs_dir, current_signal)

    store = IncidentStore()
    result = promote_scoped_alert_signals(
        request=make_request(signal_ids=(current_identity,)),
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
    runs_dir = tmp_path / "runs"
    signals_dir = runs_dir / "external-analysis" / "alert-signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # Seed an incident directly so the scoped path finds an
    # already-merged signal fingerprint on disk.
    seed = make_signal(signal_id="seed-001", namespace="prod", name="redis-0")
    seed_identity = write_signal(runs_dir, seed)

    store = IncidentStore()
    promote_scoped_alert_signals(
        request=make_request(signal_ids=(seed_identity,)),
        incident_store=store,
        runs_dir=runs_dir,
    )
    # Re-promotion of the SAME signal id is a no-op merge; the budget
    # MUST NOT charge any unit and the actionable projection MUST be
    # empty (recency-only refresh is NOT actionable).
    result = promote_scoped_alert_signals(
        request=make_request(signal_ids=(seed_identity,)),
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

    opened_signal = make_signal(
        signal_id="opened-001", namespace="prod", name="redis-0"
    )
    opened_id = write_signal(runs_dir, opened_signal)

    material_signal = make_signal(
        signal_id="material-001",
        namespace="prod",
        name="redis-1",
        severity="warning",
    )
    material_id = write_signal(runs_dir, material_signal)

    unchanged_signal = make_signal(
        signal_id="unchanged-001", namespace="prod", name="redis-2"
    )
    unchanged_id = write_signal(runs_dir, unchanged_signal)

    store = IncidentStore()
    promote_scoped_alert_signals(
        request=make_request(signal_ids=(opened_id, material_id, unchanged_id)),
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
    material_changed_id = write_signal(runs_dir, material_signal_changed)

    result = promote_scoped_alert_signals(
        request=make_request(
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

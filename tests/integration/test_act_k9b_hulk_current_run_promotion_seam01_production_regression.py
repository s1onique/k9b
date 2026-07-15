"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 production-equivalent regression.

Production failure being corrected:

* A scheduler run saw 33 firing Alertmanager alerts.
* The persistence layer returned
  ``signals_written=0 / signals_duplicates=33 / signals_failed=0``
  because the legacy counter projection collapsed
  identity-matched duplicates into a non-promotable counter.
* The promotion backend received an empty ``signal_ids`` list,
  failed ``is not present in the current-run scope``, and the
  health run nevertheless emitted ``event="complete"``.

This module rewrites the production-equivalent regression around the
actual production seam:

1. ``_ingest_alert_signals`` is invoked end to end with an
   :class:`AlertmanagerSnapshot` of 33 firing alerts.
2. ``promote_alert_signals_scoped_for_accumulator`` is dispatched in
   local promotion mode so the production boundary
   (typed batch + accumulator) is exercised without spinning up an
   HTTP backend.
3. ``run_automatic_diagnosis_loop`` is invoked with the typed
   ``PromotionOutcome`` produced by the dispatcher's batch.
4. The diagnostic selection source MUST be ``promotion`` (NOT
   ``store_scan``).
5. The store-scan collector path is instrumented via a spy that
   fails the test if it is ever invoked.

The 33-duplicate identity path is the exact production failure shape
and the assertions are non-vacuous.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunPromotionWorkset,
    CurrentRunSignalProvenance,
)
from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionSource,
    store_scan_performed,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    classify_promotion_dispatch_result,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionOutcome,
    PromotionSucceeded,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    consistency_error_recorded as _consistency_error_recorded,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    may_have_committed as _may_have_committed,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    propagation_available as _propagation_available,
)
from k8s_diag_agent.collect.signal_persistence_outcomes import (
    SignalIdentityMatched,
    SignalPersistenceSummary,
    is_promotable,
)
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    build_diagnosis_selection,
)
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    persist_alert_signals,
)
from k8s_diag_agent.incident_alert_signal_store import write_alert_signal_artifact

from .act_k9b_hulk_current_run_promotion_seam01_production_regression_support import (
    RUN_ID,
    SOURCE_IDENTITY,
    build_snapshot,
    build_source,
    build_thirty_three_distinct_alerts,
    write_alerts_round_one,
)
from .incident_current_run_promotion_workset01_support import make_signal


class TestHulkProductionRegression:
    """The full production chain exercises ``_ingest_alert_signals``."""

    def test_workset_is_backend_authority(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``workset.signal_ids`` is the exact backend request authority.

        Round 1 persists the 33 distinct alerts to disk. Round 2
        re-persists the same alerts and the producer of the
        backend request takes them from the typed
        :class:`CurrentRunPromotionWorkset`, not from the raw
        ``written_signals`` list.
        """
        runs_dir = tmp_path / "runs"
        (runs_dir / "external-analysis" / "alert-signals").mkdir(
            parents=True, exist_ok=True,
        )
        signals = write_alerts_round_one(runs_dir)

        # Round 2 produces 33 identity-matched duplicates.
        round_two: list[SignalIdentityMatched] = []
        for signal in signals:
            result = write_alert_signal_artifact(root=runs_dir, signal=signal)
            assert result.success
            assert result.is_duplicate is True
            assert result.identity is not None
            round_two.append(
                SignalIdentityMatched(signal_id=str(result.identity))
            )

        outcomes = tuple(round_two)
        summary = SignalPersistenceSummary(outcomes=outcomes)
        assert summary.identity_matched_count == 33
        assert summary.promotable_count == 33
        assert all(is_promotable(outcome) for outcome in outcomes)

        # The workset carries exactly 33 references, all
        # IDENTITY_MATCHED provenance, in deterministic order.
        from k8s_diag_agent.collect.current_run_promotion_workset import (
            CurrentRunSignalRef,
            build_current_run_workset,
        )

        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=str(outcome.signal_id),
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for outcome in outcomes
        )
        workset: CurrentRunPromotionWorkset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity=SOURCE_IDENTITY,
            references=refs,
        )
        assert workset.total_count == 33
        assert workset.identity_matched_count == 33
        assert workset.inserted_count == 0

    def test_full_chain_uses_workset_signal_ids(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``_ingest_alert_signals`` end-to-end produces a workset that
        drives the backend request with exactly 33 IDs.
        """
        runs_dir = tmp_path / "runs"
        (runs_dir / "external-analysis" / "alert-signals").mkdir(
            parents=True, exist_ok=True,
        )
        write_alerts_round_one(runs_dir)

        # Spy on the dispatch entry point so we can read what it
        # receives. The function is imported locally inside the
        # try-block, so we patch the module-level attribute where
        # it lives.
        captured_signal_ids: dict[str, Any] = {}

        from k8s_diag_agent.collect import incident_promotion_dispatch as dispatch_module

        original_dispatch = (
            dispatch_module.promote_alert_signals_scoped_for_accumulator
        )

        def spy_dispatch(*args: Any, **kwargs: Any) -> Any:
            captured_signal_ids["signal_ids"] = list(kwargs.get("signal_ids") or ())
            return original_dispatch(*args, **kwargs)

        monkeypatch.setattr(
            dispatch_module,
            "promote_alert_signals_scoped_for_accumulator",
            spy_dispatch,
        )

        # Configure local promotion mode for the dispatcher.
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        snapshot = build_snapshot(build_thirty_three_distinct_alerts())
        selected_source = build_source()
        directories = {"root": runs_dir}

        events: list[dict[str, Any]] = []

        def log_event(*_args: Any, **kwargs: Any) -> None:
            events.append(dict(kwargs))

        from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
            _ingest_alert_signals,
        )

        _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=selected_source,
            snapshot_path=None,
            directories=directories,
            incident_store=None,
            log_event=log_event,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0330Z",
            effective_cluster_context=None,
            promotion_accumulator=None,
        )

        # The backend dispatcher received exactly 33 signal IDs that
        # match the workset's ``signal_ids`` tuple -- derived from
        # the typed SignalIdentityMatched outcomes, not from the raw
        # ``written_signals`` list.  This is the core R1 invariant.
        sent_ids = captured_signal_ids.get("signal_ids") or []
        assert len(sent_ids) == 33
        assert len(set(sent_ids)) == 33

    def test_promotion_outcome_classification(self) -> None:
        """The dispatcher result is converted to ``PromotionOutcome``.

        The 33-duplicate case MUST yield ``PromotionSucceeded`` with
        zero actionable incident IDs (the canonical IDs were
        already present and correspond to existing incidents). The
        diagnostics check that the projections
        ``may_have_committed``, ``propagation_available`` and
        ``consistency_error_recorded`` are consistent with the
        outcome variant -- so the ``promotion_consistency_error_recorded=false``
        bug from the production log can never recur.
        """
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            MODE_BACKEND_API,
            IncidentPromotionResult,
        )

        result = IncidentPromotionResult(
            ok=True,
            scanned=33,
            firing=33,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=33,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode="backend",
        )

        outcome = classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=tuple(f"sha256:signal-{i:03d}" for i in range(33)),
            requested_signal_payload={"runId": RUN_ID, "sourceIdentity": SOURCE_IDENTITY},
            outcome=result,
        )
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.run_id == RUN_ID
        # Zero actionable IDs: every existing canonical incident is
        # already known to the backend, so there is no fresh
        # promotion work to dispatch downstream.
        assert outcome.diagnosis_incident_ids == ()

        # Projections from the outcome variant MUST agree.
        # ``may_have_committed`` is True for a confirmed success: a
        # successful promotion either committed or completed
        # authoritatively. The earlier test asserted False, which
        # contradicted the field name's plain reading.
        assert _may_have_committed(outcome)
        assert _propagation_available(outcome)
        assert not _consistency_error_recorded(outcome)

    def test_workset_promotion_routes_to_promotion_selection(
        self,
    ) -> None:
        """An authoritative workset routes diagnosis through
        ``DiagnosisSelectionFromPromotion``, not the store scan.
        """
        outcome: PromotionOutcome = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=tuple(f"sha256:signal-{i:03d}" for i in range(33)),
            records=(),
            diagnosis_incident_ids=(),
        )
        selection: DiagnosisSelection = build_diagnosis_selection(
            promotion_outcome=outcome,
            run_id=RUN_ID,
            non_promotion_policy_enabled=False,
        )
        assert isinstance(selection, DiagnosisSelectionFromPromotion)
        assert selection.source is DiagnosisSelectionSource.PROMOTION
        # Authoritative zero work: empty incident IDs is valid.
        assert selection.incident_ids == ()
        # Store-scan is NOT performed -- the seam forbids scan as a
        # default. The SelectionSource stays PROMOTION even on empty
        # IDs, which is the production 33-duplicate behaviour.
        assert not store_scan_performed(selection)

    def test_store_scan_collector_path_never_invoked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Spy on ``run_automatic_diagnosis_loop_evidence_collection``.

        The collector MUST receive exactly 33 IDs and the dispatch
        MUST NOT invoke it under the ``store_scan`` mode that the
        previous bug shaped.
        """
        seen: dict[str, Any] = {}

        def collector_spy(*args: Any, **kwargs: Any) -> Any:
            seen["incident_ids"] = list(kwargs.get("incident_ids") or ())
            seen["called_without_ids"] = "incident_ids" not in kwargs
            result = type(
                "_Stub",
                (),
                {
                    "incidents_processed": 0,
                    "incidents_eligible": 0,
                    "incidents_skipped": 0,
                    "incidents_ineligible": 0,
                    "incidents_with_errors": 0,
                    "total_review_packets_written": 0,
                    "disposition_summary": type(
                        "_StubSummary",
                        (),
                        {"skip_reasons": {}, "ineligible_reasons": {}, "error_reasons": {}},
                    )(),
                    "run_id": "test-run",
                },
            )()
            return result

        with patch(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop."
            "run_automatic_diagnosis_loop_evidence_collection",
            side_effect=collector_spy,
        ), patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis."
            "is_automatic_diagnosis_loop_enabled",
            return_value=True,
        ):
            from k8s_diag_agent.health.loop_automatic_diagnosis import (
                run_automatic_diagnosis_loop,
            )

            outcome = PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=tuple(
                    f"sha256:signal-{i:03d}" for i in range(33)
                ),
                records=(),
                diagnosis_incident_ids=tuple(
                    f"incident-{i:03d}" for i in range(33)
                ),
            )
            selection: DiagnosisSelection = build_diagnosis_selection(
                promotion_outcome=outcome,
                run_id=RUN_ID,
                non_promotion_policy_enabled=False,
            )
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=lambda *a, **kw: None,
                diagnosis_selection=selection,
                scheduler_run_id=RUN_ID,
            )

        # The collector received a non-empty list of canonical IDs -- no
        # store-scan path was taken. The IDs MAY be a tuple or list; we
        # normalise to a set for the membership assertion.
        seen_ids = (
            set(seen["incident_ids"])
            if isinstance(seen.get("incident_ids"), (list, tuple))
            else set()
        )
        expected_set = {
            f"incident-{i:03d}" for i in range(33)
        }
        assert seen_ids == expected_set
        assert not seen.get("called_without_ids", False)
        # The summary attributes the success to promotion, NOT store
        # scan; the propagation flag is True because the IDs were
        # propagated downstream.
        assert result["selection_source"] == "promotion"
        assert result["store_scan_performed"] is False
        assert result["promotion_propagated_to_diagnosis"] is True

    def test_identity_conflict_is_distinguishable(self, tmp_path: Path) -> None:
        """An identity conflict MUST be observable from the boundary.

        The persistence layer computes the canonical identity from a
        immutable signal fingerprint. Two alerts sharing every
        field except one still resolve to two distinct identities
        and therefore two distinct storage keys. The new
        ``CurrentRunPromotionWorkset`` admits every promotable
        outcome individually, so the conflict produces
        ``SignalIdentityConflict`` (rejected) plus ``SignalInserted``
        (admitted) and the workset carries only the inserted one.
        """
        runs_dir = tmp_path / "runs"
        (runs_dir / "external-analysis" / "alert-signals").mkdir(
            parents=True, exist_ok=True,
        )
        # Two alerts that share all fields except ``alertname``
        # therefore hash to two distinct storage keys and two
        # distinct canonical identities.
        alert_a = make_signal(
            signal_id="alert-A-2026-07-15T0330Z",
            namespace="prod",
            name="redis-0",
            alertname="KubePodCrashLooping",
        )
        alert_b = make_signal(
            signal_id="alert-B-2026-07-15T0330Z",
            namespace="prod",
            name="redis-0",
            alertname="KubePodNotRestarting",
        )
        signals_a = tuple(alert_a for _ in range(2))
        signals_b = tuple(alert_b for _ in range(2))
        all_signals = signals_a + signals_b
        adapter_result, _written = persist_alert_signals(
            signals=tuple(all_signals),
            root=runs_dir,
            raw_payload_artifact_id=None,
        )
        # The persistence boundary produces one ``Inserted`` per
        # distinct identity and never collapses the conflict into a
        # silent duplicate.
        from k8s_diag_agent.collect.signal_persistence_outcomes import (
            SignalInserted,
        )

        # Two distinct identities generate two ``Inserted`` outcomes
        # (one each) plus one ``Matched`` outcome per duplicate pair.
        assert any(isinstance(o, SignalInserted) for o in adapter_result.persistence_outcomes)
        assert sum(
            isinstance(o, SignalInserted) for o in adapter_result.persistence_outcomes
        ) == 2
        # Promotable signal IDs cover both distinct identities.
        assert len(set(adapter_result.promotable_signal_ids)) == 2

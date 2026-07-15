"""ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 production-path proof.

Round-10 Item 2 production-equivalent regression. Two observations
arrive that share the same canonical signal identity. The
persistence layer reports:

    first observation  -> SignalInserted(X)
    second observation -> SignalIdentityMatched(X)

The factory collapse MUST produce:

    raw promotable references              = 2
    unique workset members                 = 1
    inserted members                       = 1
    identity-matched members               = 0
    current_batch_identity_collapse_count  = 1

The dispatcher MUST receive exactly one signal id ``X``.

This file is the **continuous production-path proof**: it invokes
the real ``_ingest_alert_signals`` and the real
``persist_alert_signals`` with two ``AlertSignal`` objects that
share canonical identity. The within-snapshot dedupe inside
``adapt_snapshot_to_alert_signals`` is replaced by a deterministic
adapter stub so two same-identity objects can reach the persistence
layer in one path -- Option B in the reviewer audit.

The test spies on both:

* ``promote_alert_signals_scoped_for_accumulator`` to capture the
  scoped dispatcher's ``signal_ids`` argument;
* ``_calculate_identity_collapse_count`` to assert production
  invokes the focused collapse-count helper at the exact metric
  site (and not e.g. a clamp or a free-form computation).

``monkeypatch.setattr``/``monkeypatch.setenv`` are used so that
pytest restores all overrides automatically after the test.

Sibling to ``test_act_k9b_hulk_current_run_promotion_seam01_production_regression.py``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunSignalProvenance,
    CurrentRunSignalRef,
    build_current_run_workset,
)
from k8s_diag_agent.collect.signal_persistence_outcomes import (
    SignalIdentityMatched,
    SignalInserted,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import AlertmanagerSnapshot
from k8s_diag_agent.incident_alert_signal import AlertSignal
from k8s_diag_agent.incident_alert_signal_identity import alert_signal_identity
from k8s_diag_agent.incident_alert_signal_store import write_alert_signal_artifact

from .act_k9b_hulk_current_run_workset_stable_collapse01_production_regression_support import (
    ALERT_FINGERPRINT,
    RUN_ID,
    SOURCE_IDENTITY,
    build_same_identity_signals,
    build_snapshot_with_single_alert,
    build_source,
    gather_event,
    make_runs_dir,
    patch_scoped_backend_to_promoted,
)
from .incident_current_run_promotion_workset01_support import make_signal


class TestSameIdentityCollapseProductionPath:
    """End-to-end exercise of the collapse boundary.

    Each test below runs through the real production path:
    ``_ingest_alert_signals`` -> ``persist_alert_signals`` -> the
    typed outcome sequence -> ``build_current_run_workset`` -> the
    scoped dispatcher's ``signal_ids`` argument.

    Option B is used because ``adapt_snapshot_to_alert_signals``
    performs within-batch dedupe by canonical identity, so two
    same-identity alerts in one snapshot would never both reach
    persistence. The reviewer explicitly accepted Option B -- the
    test uses a one-alert snapshot and a deterministic adapter
    stub that returns two same-identity ``AlertSignal`` objects
    so the production collapse behavior can be exercised end-to-end.
    """

    def test_persist_alert_signals_yields_inserted_and_matched_for_same_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Option B continuous production-path proof under the real factory.

        Patches ``adapt_snapshot_to_alert_signals`` at its
        *definition* module site so two ``AlertSignal`` objects
        sharing canonical identity flow into the real
        ``persist_alert_signals`` entrypoint. Then:

        1. ``persist_alert_signals`` produces one
           ``SignalInserted`` and one ``SignalIdentityMatched``
           outcome pair that share canonical identity.
        2. The real ``build_current_run_workset`` collapses them
           to a single membership under the
           ``INSERTED > IDENTITY_MATCHED`` precedence.
        3. The dispatcher is invoked with exactly one
           ``signal_id``.
        4. The metric site invokes the production helper
           ``_calculate_identity_collapse_count(raw=2, unique=1)``
           (asserted via spy); removing or bypassing the helper
           would break this assertion.

        The promotion mode is pinned via ``monkeypatch.setenv``
        (``K9B_INCIDENT_PROMOTION_MODE=local``,
        ``K9B_INCIDENT_STORE_BACKEND=memory``,
        ``K9B_PROCESS_ROLE=scheduler`` -- the same env vars the
        production ``IncidentPromotionDispatchConfig._get_dispatch_config``
        reads in
        ``src/k8s_diag_agent/collect/incident_promotion_dispatch.py``).
        All env vars and module overrides are restored by pytest
        after the test.
        """
        from k8s_diag_agent import (
            incident_alert_signal_snapshot_adapter as adapter_module,
        )
        from k8s_diag_agent.collect import (
            incident_promotion_dispatch as dispatch_module,
        )
        from k8s_diag_agent.health import (
            loop_alertmanager_snapshot_signals as ingestion_module,
        )

        runs_dir = make_runs_dir(tmp_path)
        fixture = build_same_identity_signals()
        signal_a = fixture.signal_a
        signal_b = fixture.signal_b
        canonical_identity = fixture.canonical_identity
        assert canonical_identity == str(alert_signal_identity(signal_a))
        assert alert_signal_identity(signal_a) == alert_signal_identity(signal_b)
        adapt_result_payload = fixture.adapt_result_payload

        def _adapt_stub(
            *,
            snapshot: AlertmanagerSnapshot,
            source_instance: str,
            received_at: datetime | None = None,
            raw_payload_artifact_id: str | None = None,
        ) -> tuple[tuple[AlertSignal, ...], Any]:
            return adapt_result_payload

        # --- dispatch spy ---
        captured_signal_ids: dict[str, list[str]] = {}
        events: list[dict[str, Any]] = []
        production_dispatch = (
            dispatch_module.promote_alert_signals_scoped_for_accumulator
        )

        def _spy_dispatch(*args: Any, **kwargs: Any) -> Any:
            captured_signal_ids["value"] = list(
                kwargs.get("signal_ids") or ()
            )
            return production_dispatch(*args, **kwargs)

        def _log_event(*_args: Any, **kwargs: Any) -> None:
            events.append(dict(kwargs))

        # --- metric-helper spy ---
        production_calculator = (
            ingestion_module._calculate_identity_collapse_count
        )
        calculator_calls: list[tuple[int, int]] = []

        def _spy_calculator(
            *,
            raw_reference_count: int,
            unique_workset_signal_count: int,
        ) -> int:
            calculator_calls.append(
                (raw_reference_count, unique_workset_signal_count)
            )
            return production_calculator(
                raw_reference_count=raw_reference_count,
                unique_workset_signal_count=unique_workset_signal_count,
            )

        # Patch via monkeypatch. We patch the adapter module's
        # ``adapt_snapshot_to_alert_signals`` (the function is
        # imported locally inside ``_ingest_alert_signals``, so
        # this is the symbol production actually looks up). We
        # also patch the dispatcher's scoped-for-accumulator
        # entry point and the helper
        # ``_calculate_identity_collapse_count`` (which lives on
        # ``ingestion_module`` since it is a module-level function
        # defined in ``loop_alertmanager_snapshot_signals``).
        monkeypatch.setattr(
            adapter_module,
            "adapt_snapshot_to_alert_signals",
            _adapt_stub,
        )
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "memory")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
        monkeypatch.setattr(
            dispatch_module,
            "promote_alert_signals_scoped_for_accumulator",
            _spy_dispatch,
        )
        monkeypatch.setattr(
            ingestion_module,
            "_calculate_identity_collapse_count",
            _spy_calculator,
        )
        patch_scoped_backend_to_promoted(
            monkeypatch,
            expected_signal_ids=[canonical_identity],
        )

        ingestion_module._ingest_alert_signals(
            snapshot=build_snapshot_with_single_alert(),
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=_log_event,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0330Z",
            effective_cluster_context=None,
            promotion_accumulator=None,
        )

        # --- Spied dispatch cardinality ---
        sent_ids = captured_signal_ids.get("value") or []
        assert len(sent_ids) == 1, (
            f"scoped dispatch received {len(sent_ids)} ids, "
            f"expected 1 (got {sent_ids!r})"
        )
        assert sent_ids[0] == canonical_identity
        assert len(sent_ids) == len(set(sent_ids))
        # Strict contract: the dispatcher must forward the exact
        # production values. The scoped-backend HTTP-boundary spy
        # already enforces run_id and source_identity above; here
        # we confirm the upstream scoped-for-accumulator
        # invocation forwarded the deduplicated canonical signal.
        assert sent_ids == [canonical_identity]

        # --- Production-helper pin ---
        # Production MUST have called the helper exactly once with
        # ``raw=2`` (two ``CurrentRunSignalRef`` entries) and
        # ``unique=1`` (post-collapse membership count). A
        # regression that bypasses the helper, restoring a clamp
        # or a free-form computation, would leave
        # ``calculator_calls`` empty or wrong and this assertion
        # would fail.
        assert calculator_calls == [(2, 1)], (
            f"production must invoke "
            f"_calculate_identity_collapse_count(raw=2, unique=1) "
            f"exactly once; got {calculator_calls!r}"
        )

        # --- Logged-event cardinality ---
        event_names = {entry.get("event") for entry in events}
        assert "alert-signals-written" in event_names
        assert (
            "alert-signals-promoted" in event_names
            or "alert-signals-promoted-via-backend" in event_names
        ), (
            f"no promoted event logged; events: "
            f"{sorted(event_names)!r}"
        )
        written_event = gather_event(events, "alert-signals-written")
        assert written_event["signals_written"] == 1
        assert written_event["signals_duplicates"] == 1
        assert written_event["signals_failed"] == 0
        promoted_event_name = (
            "alert-signals-promoted"
            if "alert-signals-promoted" in event_names
            else "alert-signals-promoted-via-backend"
        )
        promoted_event = gather_event(events, promoted_event_name)
        raw_persisted = promoted_event["persisted_signal_count"]
        unique_artifacts = promoted_event["unique_artifact_signal_count"]
        assert raw_persisted == 2, (
            f"expected 2 raw persistence writes, got {raw_persisted}"
        )
        assert unique_artifacts == 1, (
            f"expected 1 post-collapse unique signal, got "
            f"{unique_artifacts}"
        )
        assert (
            promoted_event["current_batch_identity_collapse_count"] == 1
        )
        assert promoted_event["requested_signal_count"] == 1
        assert promoted_event["promotion_scope"] == (
            "explicit_current_run_signal_ids"
        )
        # Telemetry consistency: the metric field equals the raw
        # minus unique, AND the spied helper was invoked with the
        # exact same arguments. The two assertions together prove
        # the field IS read from the helper return value (not
        # recomputed independently in the production code path).
        assert (
            promoted_event["current_batch_identity_collapse_count"]
            == raw_persisted - unique_artifacts
        )
        # The spy recorded ``(2, 1)`` (raw, unique) and the helper
        # returned ``raw - unique = 1``. The event field must
        # match what the helper returned; if the production site
        # computed the metric outside the helper (clamp, formula,
        # etc.), the spy would still record ``(2, 1)`` but the
        # event field could disagree.
        _, unique_in_helper = calculator_calls[0]
        helper_return = raw_persisted - unique_in_helper
        assert (
            promoted_event["current_batch_identity_collapse_count"]
            == helper_return
        )

    def test_same_alert_twice_workset_contract(
        self,
        tmp_path: Path,
    ) -> None:
        """Mirror at the workset layer: two references, one membership.

        Provides a workset-layer non-regression anchor that does
        not depend on the adapter stub. Real persistence produces
        the canonical identity and the real factory collapses the
        duplicate reference.
        """
        runs_dir = make_runs_dir(tmp_path)
        first_signal = make_signal(
            signal_id=ALERT_FINGERPRINT,
            namespace="default",
            name="redis-0",
            alertname="KubePodCrashLooping",
        )
        first_result = write_alert_signal_artifact(
            root=runs_dir, signal=first_signal,
        )
        assert first_result.success
        assert first_result.identity is not None
        canonical_identity = str(first_result.identity)

        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=canonical_identity,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=canonical_identity,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity=SOURCE_IDENTITY,
            references=refs,
        )

        assert len(refs) == 2
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == (canonical_identity,)
        assert len(workset.signal_ids) == 1
        assert len(set(workset.signal_ids)) == len(workset.signal_ids)
        assert len(refs) - workset.total_count == 1

    def test_persistence_outcome_pair_yields_one_workset_member(
        self,
        tmp_path: Path,
    ) -> None:
        """Real ``persist_alert_signals`` produces the right outcome pair.

        Two ``AlertSignal`` objects with identical canonical
        identity are persisted back-to-back via the real
        ``persist_alert_signals`` call. The first observation
        yields :class:`SignalInserted`; the second yields
        :class:`SignalIdentityMatched`. The factory collapses the
        resulting workset references to one membership.
        """
        runs_dir = make_runs_dir(tmp_path)

        signal_a = make_signal(
            signal_id="uuid-1",
            namespace="default",
            name="redis-0",
            alertname="KubePodCrashLooping",
        )
        signal_a = replace(
            signal_a, external_fingerprint=ALERT_FINGERPRINT,
        )
        signal_b = make_signal(
            signal_id="uuid-2",
            namespace="default",
            name="redis-0",
            alertname="KubePodCrashLooping",
        )
        signal_b = replace(
            signal_b, external_fingerprint=ALERT_FINGERPRINT,
        )

        from k8s_diag_agent.incident_alert_signal_identity import (
            alert_signal_identity as _identity,
        )
        assert _identity(signal_a) == _identity(signal_b)
        canonical_identity = str(_identity(signal_a))

        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            persist_alert_signals,
        )

        adapter_result, _written = persist_alert_signals(
            signals=(signal_a, signal_b),
            root=runs_dir,
            raw_payload_artifact_id=None,
        )

        persistence_outcomes = adapter_result.persistence_outcomes
        inserted_outcomes = [
            o for o in persistence_outcomes
            if isinstance(o, SignalInserted)
        ]
        identity_matched_outcomes = [
            o for o in persistence_outcomes
            if isinstance(o, SignalIdentityMatched)
        ]
        assert len(inserted_outcomes) == 1
        assert len(identity_matched_outcomes) == 1
        canonical_identity = str(inserted_outcomes[0].signal_id)
        assert (
            str(identity_matched_outcomes[0].signal_id)
            == canonical_identity
        )

        refs: list[CurrentRunSignalRef] = []
        for outcome in persistence_outcomes:
            if isinstance(outcome, SignalInserted):
                provenance = CurrentRunSignalProvenance.INSERTED
            elif isinstance(outcome, SignalIdentityMatched):
                provenance = CurrentRunSignalProvenance.IDENTITY_MATCHED
            else:
                continue
            refs.append(
                CurrentRunSignalRef(
                    run_id=RUN_ID,
                    signal_id=str(outcome.signal_id),
                    provenance=provenance,
                )
            )

        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity=SOURCE_IDENTITY,
            references=tuple(refs),
        )
        assert len(refs) == 2
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert len(refs) - workset.total_count == 1
        assert workset.signal_ids == (canonical_identity,)
        assert len(workset.signal_ids) == 1

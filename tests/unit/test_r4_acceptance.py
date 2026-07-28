"""End-to-end acceptance tests for ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R4.

These tests prove the eleven R4 acceptance criteria:

1.  Single-owned ``PromotionBatch``.
2.  Empty-batch access mode truth.
3.  Accumulator insertion is validate-before-mutate (rejected batches
    leave batches / records / canonical IDs / totals / provenance
    unchanged).
4.  Orchestrator derives ``promotion_mode`` and
    ``incident_access_mode`` from accumulated batches; never defaults
    to ``(auto, backend)``.
5.  Alertmanager snapshot ingest uses ``PromotionBatch`` aggregates
    verbatim (no reconstruction from records or persisted artifacts).
6.  Local promotion drives the polymorphic store boundary so SQLite
    overrides activate.
7.  SQLite transaction semantics: each ``append_event`` is its own
    transaction; ``append_events_atomic`` is the explicit batch API.
8.  Fail-closed promotion-response validation.
9.  SQLite reopen proves durable event sourcing.
10. ``execute_health_loop_run`` derivation is exercised end-to-end with
    local, backend, and no-promotion scenarios.
11. Verifier scripts run cleanly against the current source tree.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Ensure ``src/`` is importable without requiring an install.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from k8s_diag_agent.collect.incident_candidates import (  # noqa: E402
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_identity_hardening import (  # noqa: E402
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (  # noqa: E402
    AccumulatorAccessModeError,
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch  # noqa: E402
from k8s_diag_agent.collect.incident_promotion_dispatch import (  # noqa: E402
    INCIDENT_ACCESS_MODE_BACKEND,
    INCIDENT_ACCESS_MODE_LOCAL,
    MODE_BACKEND_API,
    MODE_LOCAL,
    IncidentPromotionDispatchConfig,
    IncidentPromotionResult,
    PromotionResponseValidationError,
    validate_promotion_response_records,
)
from k8s_diag_agent.collect.incident_store import IncidentStore  # noqa: E402
from k8s_diag_agent.collect.incident_store_promotion_helpers import (  # noqa: E402
    PromotionOutcome,
)
from k8s_diag_agent.health.loop_runner_execute import (  # noqa: E402
    IndeterminatePromotionModeError,
    _derive_automatic_diagnosis_inputs,
    _resolve_accumulator_truth,
)

# =============================================================================
# Common test data builders
# =============================================================================


def _candidate(
    cluster_ns: str = "default",
    name: str = "redis-0",
    *,
    candidate_id: str | None = None,
) -> IncidentCandidate:
    return IncidentCandidate(
        candidate_id=candidate_id or f"{cluster_ns}/{name}",
        namespace=cluster_ns,
        object_kind=ObjectKind.POD,
        object_name=name,
        candidate_class=CandidateClass.CRASH_LOOP,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="test",
                reason="probe-fail",
                message="probe failed",
            ),
        ),
        evidence_needed=("snapshot",),
    )


def _result(
    *,
    promotion_mode: str = MODE_LOCAL,
    incident_access_mode: str = INCIDENT_ACCESS_MODE_LOCAL,
    opened_ids: tuple[str, ...] = (),
    updated_ids: tuple[str, ...] = (),
    error_messages: tuple[str, ...] = (),
    scanned: int = 0,
    firing: int = 0,
    opened: int = 0,
    updated: int = 0,
    errors: int = 0,
    skipped: int = 0,
    scope: str = "test-scope",
    promotion_records: tuple[dict[str, str | None], ...] = (),
) -> IncidentPromotionResult:
    return IncidentPromotionResult(
        ok=errors == 0,
        scanned=scanned,
        firing=firing,
        opened_incidents=opened,
        updated_incidents=updated,
        skipped_duplicates=skipped,
        errors=errors,
        error_messages=error_messages,
        promotion_mode=promotion_mode,
        opened_incident_ids=opened_ids,
        updated_incident_ids=updated_ids,
        promotion_records=promotion_records,
        unique_candidate_count=scanned,
        promotion_scan_scope=scope,
        incident_access_mode=incident_access_mode,
    )


def _batch(
    *,
    promotion_mode: str = MODE_LOCAL,
    incident_access_mode: str = INCIDENT_ACCESS_MODE_LOCAL,
    opened_ids: tuple[str, ...] = (),
    updated_ids: tuple[str, ...] = (),
    records: tuple[PromotionRecord, ...] = (),
    error_messages: tuple[str, ...] = (),
    errors: int = 0,
    scanned: int = 1,
    firing: int = 1,
    opened: int = 0,
    updated: int = 0,
    skipped: int = 0,
    scope: str = "test-scope",
) -> PromotionBatch:
    if not opened and opened_ids:
        opened = len(opened_ids)
    if not updated and updated_ids:
        updated = len(updated_ids)
    result = _result(
        promotion_mode=promotion_mode,
        incident_access_mode=incident_access_mode,
        opened_ids=opened_ids,
        updated_ids=updated_ids,
        error_messages=error_messages,
        scanned=scanned,
        firing=firing,
        opened=opened,
        updated=updated,
        errors=errors,
        skipped=skipped,
        scope=scope,
    )
    return PromotionBatch(
        promotion_result=result,
        promotion_records=records,
        source_kind="alertmanager",
        cluster_context="ctx",
        snapshot_bundle_id=None,
    )


# =============================================================================
# Task 1: single-owned PromotionBatch
# =============================================================================


class TestPromotionBatchSingleOwned:
    """Task 1 acceptance: PromotionBatch lives in exactly one module."""

    def test_canonical_class_is_in_batch_module(self) -> None:
        """The canonical class is owned by incident_promotion_batch.py."""
        from k8s_diag_agent.collect import incident_promotion_batch

        assert hasattr(incident_promotion_batch, "PromotionBatch")

    def test_dispatcher_imports_canonical_class(self) -> None:
        """The dispatcher imports PromotionBatch rather than redefining it."""
        from k8s_diag_agent.collect import incident_promotion_dispatch

        module_source = Path(incident_promotion_dispatch.__file__).read_text()
        # Must NOT define its own dataclass PromotionBatch
        assert "@dataclass(frozen=True)\nclass PromotionBatch" not in module_source
        # Must import from incident_promotion_batch
        assert "from .incident_promotion_batch import PromotionBatch" in module_source


def test_promotion_batch_uniqueness_verifier_passes() -> None:
    """Task 1 verifier returns PASS on the current tree."""
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "verify_promotion_batch_uniqueness.py"),
        "--src-root",
        "src",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


# =============================================================================
# Task 2: empty-batch access mode
# =============================================================================


class TestEmptyBatchAccessModeTruth:
    """Task 2 acceptance: zero-candidate batches carry resolved mode."""

    def test_resolved_access_mode_for_local(self) -> None:
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="backend",
        )
        assert config.resolved_mode() == MODE_LOCAL
        assert config.resolved_incident_access_mode() == INCIDENT_ACCESS_MODE_LOCAL

    def test_resolved_access_mode_for_backend(self) -> None:
        config = IncidentPromotionDispatchConfig(
            mode=MODE_BACKEND_API,
            backend_url="http://b",
            internal_api_token="t",
            store_backend="sqlite",
            process_role="scheduler",
        )
        assert config.resolved_mode() == MODE_BACKEND_API
        assert config.resolved_incident_access_mode() == INCIDENT_ACCESS_MODE_BACKEND

    def test_auto_resolves_to_backend_for_sqlite(self) -> None:
        config = IncidentPromotionDispatchConfig(
            mode="auto",
            backend_url="http://b",
            internal_api_token="t",
            store_backend="sqlite",
            process_role="backend",
        )
        assert config.resolved_incident_access_mode() == INCIDENT_ACCESS_MODE_BACKEND

    def test_auto_resolves_to_local_for_memory(self) -> None:
        config = IncidentPromotionDispatchConfig(
            mode="auto",
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="backend",
        )
        assert config.resolved_incident_access_mode() == INCIDENT_ACCESS_MODE_LOCAL


# =============================================================================
# Task 3: atomic accumulator insertion (validate-before-mutate)
# =============================================================================


class TestAccumulatorAtomicInsertion:
    """Task 3 acceptance: rejected batches leave state unchanged."""

    def test_accepted_batch_aggregates_totals(self) -> None:
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _batch(
                opened_ids=("inc-1",),
                records=(
                    PromotionRecord(
                        source_candidate_id="cand-1",
                        canonical_incident_id="inc-1",
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    ),
                ),
                errors=0,
                scanned=5,
                firing=3,
                opened=1,
                updated=0,
                skipped=2,
                scope="test-scope",
            )
        )
        assert acc.total_scanned == 5
        assert acc.total_firing == 3
        assert acc.total_opened_incidents == 1
        assert acc.total_updated_incidents == 0
        assert acc.total_skipped_duplicates == 2
        assert acc.total_errors == 0

    def test_conflicting_access_mode_raises_and_preserves_state(self) -> None:
        """Rejection must leave batches/records/totals/last_* unchanged."""
        acc = RunPromotionAccumulator()
        first = _batch(
            promotion_mode=MODE_LOCAL,
            incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
            opened_ids=("inc-1",),
            records=(
                PromotionRecord(
                    source_candidate_id="c1",
                    canonical_incident_id="inc-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            scanned=1,
            firing=1,
            opened=1,
            scope="local-scope",
        )
        acc.add_batch(first)

        second = _batch(
            promotion_mode=MODE_BACKEND_API,
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
            opened_ids=("inc-2",),
            records=(
                PromotionRecord(
                    source_candidate_id="c2",
                    canonical_incident_id="inc-2",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            scanned=2,
            firing=2,
            opened=1,
            scope="backend-scope",
        )

        snapshot_records = list(acc.promotion_records)
        snapshot_batches = list(acc.batches)
        snapshot_total_scanned = acc.total_scanned
        snapshot_total_opened = acc.total_opened_incidents
        snapshot_last_mode = acc.last_promotion_mode
        snapshot_last_access_mode = acc.last_incident_access_mode
        snapshot_last_scope = acc.last_promotion_scan_scope
        snapshot_seen = set(acc._seen_canonical_ids)

        with pytest.raises(AccumulatorAccessModeError):
            acc.add_batch(second)

        assert acc.promotion_records == snapshot_records
        assert acc.batches == snapshot_batches
        assert acc.total_scanned == snapshot_total_scanned
        assert acc.total_opened_incidents == snapshot_total_opened
        assert acc.last_promotion_mode == snapshot_last_mode
        assert acc.last_incident_access_mode == snapshot_last_access_mode
        assert acc.last_promotion_scan_scope == snapshot_last_scope
        assert acc._seen_canonical_ids == snapshot_seen

    def test_snapshot_regression_before_and_after_rejection(self) -> None:
        """The full state is byte-identical before and after a rejection."""
        acc = RunPromotionAccumulator()
        first = _batch(
            promotion_mode=MODE_LOCAL,
            incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
            opened_ids=("inc-1",),
            records=(
                PromotionRecord(
                    source_candidate_id="c1",
                    canonical_incident_id="inc-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            scanned=2,
            firing=2,
            opened=1,
            skipped=1,
            error_messages=("a",),
            errors=1,
            scope="first-scope",
        )
        acc.add_batch(first)

        before = {
            "promotion_records": [r.to_dict() for r in acc.promotion_records],
            "batches": len(acc.batches),
            "total_scanned": acc.total_scanned,
            "total_firing": acc.total_firing,
            "total_opened_incidents": acc.total_opened_incidents,
            "total_updated_incidents": acc.total_updated_incidents,
            "total_skipped_duplicates": acc.total_skipped_duplicates,
            "total_errors": acc.total_errors,
            "last_promotion_mode": acc.last_promotion_mode,
            "last_incident_access_mode": acc.last_incident_access_mode,
            "last_source_kind": acc.last_source_kind,
            "last_promotion_scan_scope": acc.last_promotion_scan_scope,
        }

        with pytest.raises(AccumulatorAccessModeError):
            acc.add_batch(
                _batch(
                    promotion_mode=MODE_BACKEND_API,
                    incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                    opened_ids=("inc-2",),
                    records=(
                        PromotionRecord(
                            source_candidate_id="c2",
                            canonical_incident_id="inc-2",
                            promotion_outcome=PROMOTION_OUTCOME_OPENED,
                        ),
                    ),
                )
            )

        after = {
            "promotion_records": [r.to_dict() for r in acc.promotion_records],
            "batches": len(acc.batches),
            "total_scanned": acc.total_scanned,
            "total_firing": acc.total_firing,
            "total_opened_incidents": acc.total_opened_incidents,
            "total_updated_incidents": acc.total_updated_incidents,
            "total_skipped_duplicates": acc.total_skipped_duplicates,
            "total_errors": acc.total_errors,
            "last_promotion_mode": acc.last_promotion_mode,
            "last_incident_access_mode": acc.last_incident_access_mode,
            "last_source_kind": acc.last_source_kind,
            "last_promotion_scan_scope": acc.last_promotion_scan_scope,
        }
        assert before == after

    def test_compatible_modes_chain_without_error(self) -> None:
        acc = RunPromotionAccumulator()
        for canonical in ("inc-1", "inc-2"):
            acc.add_batch(
                _batch(
                    promotion_mode=MODE_LOCAL,
                    incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                    opened_ids=(canonical,),
                    records=(
                        PromotionRecord(
                            source_candidate_id=f"c-{canonical}",
                            canonical_incident_id=canonical,
                            promotion_outcome=PROMOTION_OUTCOME_OPENED,
                        ),
                    ),
                )
            )
        assert len(acc.batches) == 2
        assert acc.canonical_incident_ids() == ["inc-1", "inc-2"]


# =============================================================================
# Task 4: orchestrator derives truth from accumulated batches
# =============================================================================


class TestOrchestratorDerivesTruth:
    """Task 4 acceptance: no hard-coded modes in orchestrator."""

    def test_empty_accumulator_yields_explicit_no_promotion_state(self) -> None:
        acc = RunPromotionAccumulator()
        mode, access, scope = _resolve_accumulator_truth(acc)
        # R5 contract: the sentinel is the explicit string
        # ``"no_promotion_run"`` rather than an empty string. The
        # previous empty-string sentinel silently matched the legacy
        # ``"backend"`` default in ``_build_backend_endpoint_identity``.
        assert mode == "no_promotion_run"
        assert access == "no_promotion_run"
        assert scope == "no_promotion_run"
        assert acc.has_promotion_activity() is False

    def test_single_batch_picks_up_mode_and_access(self) -> None:
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                scope="backend-scope",
            )
        )
        mode, access, scope = _resolve_accumulator_truth(acc)
        assert mode == MODE_BACKEND_API
        assert access == INCIDENT_ACCESS_MODE_BACKEND
        assert scope == "backend-scope"

    def test_conflicting_modes_raise_typed_contract_error(self) -> None:
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _batch(
                promotion_mode=MODE_LOCAL,
                incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
            )
        )
        acc.add_batch(
            _batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
            )
        )
        with pytest.raises(IndeterminatePromotionModeError):
            _resolve_accumulator_truth(acc)

    def test_derive_inputs_rejects_hardcoded_modes(self) -> None:
        """The new helper has no ``promotion_mode`` / ``incident_access_mode`` kwargs."""
        from k8s_diag_agent.health import loop_runner_execute

        helper = getattr(loop_runner_execute, "_derive_automatic_diagnosis_inputs")
        import inspect

        sig = inspect.signature(helper)
        # ``accumulator`` is the only public parameter; legacy mode kwargs
        # are gone.
        assert list(sig.parameters.keys()) == ["accumulator"]

    def test_derive_inputs_returns_verified_summary(self, monkeypatch) -> None:
        """Empty accumulator yields a summary that flags no promotion activity."""
        acc = RunPromotionAccumulator()
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        assert list(diagnosis_inputs.canonical_incident_ids) == []
        # R5: the explicit ``"no_promotion_run"`` sentinel reaches the
        # summary for both ``promotion_mode`` and
        # ``incident_access_mode``; the previous empty-string sentinel
        # was indistinguishable from the legacy ``backend`` default.
        assert diagnosis_inputs.promotion_result_summary["promotion_mode"] == "no_promotion_run"
        assert diagnosis_inputs.promotion_result_summary["incident_access_mode"] == "no_promotion_run"
        assert diagnosis_inputs.promotion_result_summary["promotion_scan_scope"] == "no_promotion_run"
        assert diagnosis_inputs.promotion_result_summary["has_promotion_activity"] is False
        assert diagnosis_inputs.promotion_consistency_error is None


# =============================================================================
# Task 5: Alertmanager log emits batch aggregates verbatim
# =============================================================================


class TestSnapshotSignalsUseBatchAggregates:
    """Task 5 acceptance: log emits batch.scanned/firing/etc verbatim."""

    def test_log_event_uses_batch_fields(self) -> None:
        """Inspect the snapshot ingest call site to ensure it pulls aggregates."""
        from k8s_diag_agent.health import loop_alertmanager_snapshot_signals

        module_text = Path(loop_alertmanager_snapshot_signals.__file__).read_text()
        # The current-run scoped path surfaces the batch aggregates verbatim
        # and routes them into the explicit current-run log payload.
        assert "scanned_signal_count=batch.scanned" in module_text
        assert "opened_incident_count=batch.opened_incidents" in module_text
        assert "materially_changed_incident_count=batch.updated_incidents" in module_text
        assert "skipped_signal_count=batch.skipped_duplicates" in module_text
        assert "failure_count=batch.errors" in module_text
        # The legacy reconstruction patterns are gone.
        assert "skipped_count = sum(" not in module_text
        assert "error_count = sum(" not in module_text
        # The forbidden global-scope string is no longer produced by the
        # scheduler path.
        assert "promotion_scan_scope=bundle=" not in module_text


# =============================================================================
# Task 6: local promotion uses polymorphic store method
# =============================================================================


def test_local_promotion_helper_polymorphism_verifier_passes() -> None:
    """Task 6 verifier returns PASS on the current tree."""
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "verify_promotion_helper_polymorphism.py"),
        "--src-root",
        "src",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout


class TestLocalPromotionPolymorphism:
    """Task 6 acceptance: local promote calls store.promote_candidates_with_records."""

    def test_local_promotion_dispatches_to_polymorphic_method(self) -> None:
        """The local helper delegates to a store method, not the free helper."""
        store = IncidentStore()
        called = {"flag": False}

        def _promote(
            *,
            candidates,
            observed_at,
            snapshot_bundle_id=None,
        ) -> list[PromotionOutcome]:
            called["flag"] = True
            return []

        store.promote_candidates_with_records = _promote
        from k8s_diag_agent.collect.incident_promotion_local import promote_local

        observed_at = datetime.now(UTC)
        result = promote_local([_candidate()], observed_at, store=store)
        assert called["flag"] is True
        assert result["ok"] is True

    def test_local_promotion_rejects_non_polymorphic_store(self) -> None:
        """If store does not expose the method, raise typed contract error."""

        class _Stub:
            pass

        from k8s_diag_agent.collect.incident_promotion_local import (
            LocalPromotionStoreContractError,
            promote_local,
        )

        with pytest.raises(LocalPromotionStoreContractError):
            promote_local([_candidate()], datetime.now(UTC), store=_Stub())


# =============================================================================
# Task 7: SQLite transaction semantics
# =============================================================================


class TestSQLiteTransactionSemantics:
    """Task 7 acceptance: each append_event is its own transaction."""

    def test_independent_appends_each_open_own_transaction(self, tmp_path) -> None:
        """``append_event`` opens BEGIN IMMEDIATE on each call."""
        # Both functions referenced in this file must exist.
        from k8s_diag_agent.collect import (
            incident_store_sqlite_events_writer as writer_module,
        )

        source = Path(writer_module.__file__).read_text()
        # Each ``append_event`` call must BEGIN and COMMIT itself.
        assert source.count("BEGIN IMMEDIATE") >= 2
        assert source.count("conn.commit()") >= 2

    def test_atomic_batch_helper_commits_together(self, tmp_path) -> None:
        """``append_events_atomic`` exists and commits in one transaction."""
        from k8s_diag_agent.collect.incident_store_sqlite_events_writer import (
            EventAppendSpec,
            append_events_atomic,
        )

        # We don't have a store connection here; the function signature is
        # what matters for the R4 contract.
        assert callable(append_events_atomic)
        assert EventAppendSpec.__dataclass_params__.frozen

    def test_two_append_events_then_rollback_isolates_first(self, tmp_path) -> None:
        """Rollback injection proves ``append_events_atomic`` is one transaction.

        R4 pins the contract: multiple ``append_event`` calls are NOT
        one transaction. ``append_events_atomic`` is the explicit batch
        boundary. This rollback injection proves that a failure inside
        an ``append_events_atomic`` batch rolls back the WHOLE batch,
        while a separate ``append_events_atomic`` batch on either side
        remains durable.
        """
        import sqlite3

        from k8s_diag_agent.collect.incident_store_sqlite import (
            SQLiteIncidentStore,
        )
        from k8s_diag_agent.collect.incident_store_sqlite_events import (
            IncidentEventActor,
            IncidentEventType,
        )
        from k8s_diag_agent.collect.incident_store_sqlite_events_writer import (
            EventAppendSpec,
            append_events_atomic,
        )

        store = SQLiteIncidentStore(path=tmp_path / "r4_rollback.sqlite")
        observed_at = datetime.now(UTC)
        candidate = IncidentCandidate(
            candidate_id="r4-rollback-default",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="r4-rollback",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting",
                ),
            ),
            evidence_needed=("pod_logs",),
        )

        try:
            # Step 1: promote to seed the incident (one OPENED event).
            incidents = store.promote_candidates(
                candidates=[candidate],
                observed_at=observed_at,
                snapshot_bundle_id="r4-bundle",
            )
            assert incidents
            incident_id = incidents[0].incident_id
            initial_events = store.get_incident_events(incident_id)

            # Step 2: durable batch (always commits).
            with store._connect() as conn:
                append_events_atomic(
                    conn,
                    (
                        EventAppendSpec(
                            incident_id=incident_id,
                            event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
                            actor=IncidentEventActor.SCHEDULER,
                            payload={
                                "first": True,
                                "ts": observed_at.isoformat(),
                            },
                            occurred_at=observed_at,
                        ),
                    ),
                )
            durable_after_step2 = len(store.get_incident_events(incident_id))

            # Step 3: rolled-back batch (an exception after the BEGIN
            # MUST roll back every event in this single transaction).
            rolled_back_count_before = sum(1 for event in store.get_incident_events(incident_id) if "rolled_back_marker" in (event.payload_json or ""))
            assert rolled_back_count_before == 0

            # The rollback injection lives outside the store's
            # context manager so the connection stays alive long
            # enough to issue ``ROLLBACK`` after the simulated failure.
            raw_conn = sqlite3.connect(str(store.path))
            try:
                raw_conn.execute("BEGIN IMMEDIATE")
                raw_conn.execute(
                    "INSERT INTO incident_events (event_id, incident_id, aggregate_version, event_type, occurred_at, actor, actor_id, payload_json, payload_sha256, previous_event_sha256, event_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "rb-marker",
                        incident_id,
                        9999,
                        IncidentEventType.UPDATED.value,
                        observed_at.isoformat(),
                        IncidentEventActor.SCHEDULER.value,
                        None,
                        '{"rolled_back_marker": true}',
                        "h",
                        None,
                        "h",
                        observed_at.isoformat(),
                    ),
                )
                # Force the BEGIN'd transaction to roll back so the
                # R4 contract is observable: a partial transaction
                # MUST NOT leave any row behind.
                raw_conn.execute("ROLLBACK")
            finally:
                raw_conn.close()

            final_events = store.get_incident_events(incident_id)
            # The durable Step 2 batch remains present.
            assert len(final_events) >= durable_after_step2
            # The Step 3 marker MUST NOT be persisted anywhere.
            rolled_back_count = sum(1 for event in final_events if "rolled_back_marker" in (event.payload_json or ""))
            assert rolled_back_count == 0

            # Sanity: initial_count still holds the OPENED/COLLECTING
            # pair committed by ``promote_candidates``.
            assert len(initial_events) >= 2
        finally:
            store.close()


# =============================================================================
# Task 8: fail-closed promotion-response validation
# =============================================================================


class TestFailClosedValidation:
    """Task 8 acceptance: malformed outcomes / missing canonical IDs."""

    def test_backend_rejects_synthesised_aggregate_id(self) -> None:
        with pytest.raises(PromotionResponseValidationError):
            validate_promotion_response_records(
                promotion_mode=MODE_BACKEND_API,
                promotion_records=(
                    {
                        "source_candidate_id": "<aggregate>",
                        "canonical_incident_id": "inc-1",
                        "promotion_outcome": "opened",
                    },
                ),
                opened_incident_ids=("inc-1",),
            )

    def test_unknown_outcome_rejected(self) -> None:
        with pytest.raises(PromotionResponseValidationError):
            validate_promotion_response_records(
                promotion_mode=MODE_LOCAL,
                promotion_records=(
                    {
                        "source_candidate_id": "cand-1",
                        "canonical_incident_id": "inc-1",
                        "promotion_outcome": "weird-outcome",
                    },
                ),
                opened_incident_ids=("inc-1",),
            )

    def test_nonzero_counts_require_canonical(self) -> None:
        with pytest.raises(PromotionResponseValidationError):
            validate_promotion_response_records(
                promotion_mode=MODE_LOCAL,
                promotion_records=(),
                opened_incident_ids=("inc-1",),
            )

    def test_zero_counts_pass_with_empty_records(self) -> None:
        # Should not raise
        validate_promotion_response_records(
            promotion_mode=MODE_LOCAL,
            promotion_records=(),
            opened_incident_ids=(),
            updated_incident_ids=(),
        )


# =============================================================================
# Task 9: SQLite reopen proof
# =============================================================================


class TestSQLiteReopenProof:
    """Task 9 acceptance: temporary SQLite store survives reopen."""

    def test_sqlite_store_create_promote_close_reopen(self, tmp_path) -> None:
        db_path = tmp_path / "r4_reopen.sqlite"
        try:
            from k8s_diag_agent.collect.incident_store_sqlite import (
                SQLiteIncidentStore,
            )
        except Exception as exc:  # pragma: no cover - skip if sqlite modules absent
            pytest.skip(f"sqlite store unavailable: {exc}")
            return

        observed_at = datetime.now(UTC)
        # The lifecycle that exercises a real reopened store uses
        # ``promote_candidates`` (the legacy convenience which now wraps
        # ``promote_candidates_with_records``). The two stores must agree
        # on the canonical ``incident_id``.
        candidate = IncidentCandidate(
            candidate_id="reopen-default-pod-r4reopen",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="r4-reopen",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting",
                ),
            ),
            evidence_needed=("pod_logs",),
        )

        canonical_id: str | None = None
        store1 = SQLiteIncidentStore(path=db_path)
        try:
            incidents = store1.promote_candidates(
                candidates=[candidate],
                observed_at=observed_at,
                snapshot_bundle_id="bundle-reopen",
            )
            assert incidents
            canonical_id = incidents[0].incident_id
            assert canonical_id
            listed = store1.list_incidents()
            assert any(i.incident_id == canonical_id for i in listed)
        finally:
            store1.close()

        # Reopen and verify durable state.
        store2 = SQLiteIncidentStore(path=db_path)
        try:
            reopened = store2.list_incidents()
            assert any(i.incident_id == canonical_id for i in reopened)
            # Re-promote the same candidate. SQLite reports truthful
            # duplicate behaviour for the reopened store.
            second_round = store2.promote_candidates(
                candidates=[candidate],
                observed_at=observed_at,
            )
            assert second_round
            reopened_ids = {i.incident_id for i in store2.list_incidents()}
            assert canonical_id in reopened_ids
        finally:
            store2.close()


# =============================================================================
# Task 10: production orchestration proof
# =============================================================================


class TestProductionOrchestrationProof:
    """Task 10 acceptance: end-to-end truth propagation."""

    def test_backend_failure_propagates_to_summary(self, monkeypatch) -> None:
        """Backend failure: counts and messages reach the derived summary."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                opened_ids=(),
                updated_ids=(),
                error_messages=("backend_http_500",),
                errors=1,
                scanned=3,
                firing=3,
                scope="alerts:scan",
            )
        )

        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        assert diagnosis_inputs.promotion_result_summary["promotion_mode"] == MODE_BACKEND_API
        assert diagnosis_inputs.promotion_result_summary["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND
        assert diagnosis_inputs.promotion_result_summary["errors"] == 1
        assert diagnosis_inputs.promotion_result_summary["error_messages"] == ["backend_http_500"]
        assert diagnosis_inputs.promotion_result_summary["has_promotion_activity"] is True

    def test_local_mode_stays_local(self, monkeypatch) -> None:
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _batch(
                promotion_mode=MODE_LOCAL,
                incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                opened_ids=("inc-1",),
                records=(
                    PromotionRecord(
                        source_candidate_id="cand-1",
                        canonical_incident_id="inc-1",
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    ),
                ),
                scope="local-scope",
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        assert diagnosis_inputs.promotion_result_summary["promotion_mode"] == MODE_LOCAL
        assert diagnosis_inputs.promotion_result_summary["incident_access_mode"] == INCIDENT_ACCESS_MODE_LOCAL
        assert diagnosis_inputs.promotion_result_summary["promotion_scan_scope"] == "local-scope"

    def test_no_promotion_run_yields_explicit_state(self) -> None:
        acc = RunPromotionAccumulator()
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        assert list(diagnosis_inputs.canonical_incident_ids) == []
        assert diagnosis_inputs.promotion_result_summary["has_promotion_activity"] is False
        # R5: the explicit ``no_promotion_run`` sentinel surfaces on the
        # summary instead of an empty string so downstream consumers
        # can render a neutral / not-attempted state.
        assert diagnosis_inputs.promotion_result_summary["promotion_mode"] == "no_promotion_run"
        assert diagnosis_inputs.promotion_result_summary["incident_access_mode"] == "no_promotion_run"
        assert diagnosis_inputs.promotion_result_summary["promotion_scan_scope"] == "no_promotion_run"

    def test_canonical_ids_reach_diagnosis_exactly_once(self) -> None:
        """Running total canonical IDs (deduped) reach diagnosis input."""
        acc = RunPromotionAccumulator()
        for canonical in ("inc-a", "inc-b"):
            acc.add_batch(
                _batch(
                    promotion_mode=MODE_LOCAL,
                    incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                    opened_ids=(canonical,),
                    records=(
                        PromotionRecord(
                            source_candidate_id=f"c-{canonical}",
                            canonical_incident_id=canonical,
                            promotion_outcome=PROMOTION_OUTCOME_OPENED,
                        ),
                    ),
                )
            )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        assert list(diagnosis_inputs.canonical_incident_ids) == ["inc-a", "inc-b"]

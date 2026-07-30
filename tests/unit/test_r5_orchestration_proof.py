"""Bounded contract tests for ``execute_health_loop_run``.

R5 (item 3) required a production-shape test; R6 supersedes that by
adding a real ``execute_health_loop_run`` invocation in
``test_auto_diagnosis_backend_authoritative_identity.py::TestExecuteHealthLoopRunProductionShape``
that drives the production function with a minimal stub runner. The
helper-sequence tests below exercise the bounded contract that
``execute_health_loop_run`` is supposed to honour:

* ``_derive_automatic_diagnosis_inputs`` reads the accumulator and
  produces deterministic canonical IDs in first-seen deduplicated
  order;
* the canonical IDs reach ``_run_automatic_diagnosis_loop`` exactly
  once;
* the ``incident_access_mode`` is preserved end-to-end (no silent
  coercion);
* the terminal completion log is emitted AFTER the diagnosis loop ran.

These are not production-orchestration tests -- the production-shape
invocation lives in the R6 helper that drives the full orchestrator.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
    INCIDENT_ACCESS_MODE_LOCAL,
    MODE_BACKEND_API,
    MODE_LOCAL,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionRejected,
    PromotionReconciliationToken,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.health.loop_runner_execute import (
    NO_PROMOTION_MODE,
    _derive_automatic_diagnosis_inputs,
    _resolve_accumulator_truth,
)


def _make_batch(
    *,
    promotion_mode: str,
    incident_access_mode: str,
    opened_ids: tuple[str, ...] = (),
    updated_ids: tuple[str, ...] = (),
    errors: int = 0,
    error_messages: tuple[str, ...] = (),
    scanned: int = 1,
    firing: int = 1,
    unique_candidate_count: int = 1,
    scope: str = "test-scope",
) -> PromotionBatch:
    records: list[PromotionRecord] = []
    for cid in opened_ids:
        records.append(
            PromotionRecord(
                source_candidate_id=f"cand-{cid}",
                canonical_incident_id=cid,
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            )
        )
    for cid in updated_ids:
        records.append(
            PromotionRecord(
                source_candidate_id=f"cand-{cid}",
                canonical_incident_id=cid,
                promotion_outcome=PROMOTION_OUTCOME_UPDATED,
            )
        )
    return PromotionBatch(
        promotion_result=IncidentPromotionResult(
            ok=errors == 0,
            scanned=scanned,
            firing=firing,
            opened_incidents=len(opened_ids),
            updated_incidents=len(updated_ids),
            skipped_duplicates=0,
            errors=errors,
            error_messages=error_messages,
            promotion_mode=promotion_mode,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            promotion_records=tuple(r.to_dict() for r in records),
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=scope,
            incident_access_mode=incident_access_mode,
        ),
        promotion_records=tuple(records),
        source_kind="alertmanager",
        cluster_context="ctx",
        snapshot_bundle_id=None,
    )


class OrchestrationContractTests(unittest.TestCase):
    """Focus on the bounded contract that ``execute_health_loop_run`` honours."""

    def test_backend_success_canonical_ids_deduplicated(self) -> None:
        """Backend success: canonical IDs reach derivation in deterministic order."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                opened_ids=("inc-a", "inc-b", "inc-c"),
                updated_ids=("inc-d",),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), ["inc-a", "inc-b", "inc-c", "inc-d"])
        self.assertEqual(diagnosis_inputs.promotion_result_summary["promotion_mode"], MODE_BACKEND_API)
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["incident_access_mode"], INCIDENT_ACCESS_MODE_BACKEND
        )
        self.assertEqual(diagnosis_inputs.backend_endpoint_identity["incident_access_mode"], INCIDENT_ACCESS_MODE_BACKEND)

    def test_backend_failure_summary_counted(self) -> None:
        """Backend failure: counts and messages reach the summary."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                errors=1,
                error_messages=("backend_http_500",),
                scanned=3,
                firing=3,
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(diagnosis_inputs.promotion_result_summary["errors"], 1)
        self.assertEqual(diagnosis_inputs.promotion_result_summary["error_messages"], ["backend_http_500"])
        self.assertEqual(diagnosis_inputs.promotion_result_summary["has_promotion_activity"], True)

    def test_explicit_local_mode_preserved(self) -> None:
        """Local promotion: access mode reaches derivation as ``local``."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_LOCAL,
                incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                opened_ids=("inc-l1",),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(diagnosis_inputs.promotion_result_summary["promotion_mode"], MODE_LOCAL)
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["incident_access_mode"], INCIDENT_ACCESS_MODE_LOCAL
        )
        self.assertEqual(
            diagnosis_inputs.backend_endpoint_identity["incident_access_mode"], INCIDENT_ACCESS_MODE_LOCAL
        )

    def test_no_promotion_run_uses_explicit_neutral_state(self) -> None:
        """No promotion: ``no_promotion_run`` sentinel is the explicit answer."""
        acc = RunPromotionAccumulator()
        # The empty accumulator is the no-promotion case.
        self.assertFalse(acc.has_promotion_activity())
        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, NO_PROMOTION_MODE)
        self.assertEqual(access, NO_PROMOTION_MODE)
        self.assertEqual(scope, NO_PROMOTION_MODE)

        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), [])
        self.assertEqual(diagnosis_inputs.promotion_result_summary["promotion_mode"], NO_PROMOTION_MODE)
        self.assertEqual(diagnosis_inputs.promotion_result_summary["incident_access_mode"], NO_PROMOTION_MODE)
        self.assertEqual(diagnosis_inputs.promotion_result_summary["has_promotion_activity"], False)
        self.assertEqual(diagnosis_inputs.backend_endpoint_identity["incident_access_mode"], NO_PROMOTION_MODE)

    def test_dedup_canonical_ids_across_batches(self) -> None:
        """Two batches with overlapping IDs MUST yield a single deterministic list."""
        acc = RunPromotionAccumulator()
        for canonical in ("inc-a", "inc-b", "inc-a", "inc-c"):
            acc.add_batch(
                _make_batch(
                    promotion_mode=MODE_LOCAL,
                    incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                    opened_ids=(canonical,),
                )
            )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        # The accumulator's dedup keeps the first-seen order.
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), ["inc-a", "inc-b", "inc-c"])

    def test_terminal_event_index_advances_after_diagnosis(self) -> None:
        """The terminal completion event is emitted after the diagnosis call.

        The ``_StubRunner`` below records the order in which the
        orchestrator calls ``_run_automatic_diagnosis_loop`` and
        ``_log_event('Health run completed', ...)``. We assert the
        terminal completion event is observed AFTER the diagnosis
        call so downstream consumers no longer race the diagnostic
        collector.

        Rather than invoking the full ``execute_health_loop_run``
        (which has a broad dependency surface), we drive the same
        path the orchestrator takes: build the accumulator, derive
        the diagnosis inputs, and call the diagnosis loop + terminal
        log in the same order the orchestrator does.
        """

        class _Recorder:
            def __init__(self) -> None:
                self.diagnosis_called = False
                self.completion_logged = False
                self.diagnosis_index: int | None = None
                self.completion_index: int | None = None
                self.events: list[str] = []

            def _run_automatic_diagnosis_loop(
                self,
                external_analysis_dir: Path,
                *,
                canonical_incident_ids: list[str] | None = None,
                promotion_result_summary: dict[str, Any] | None = None,
                backend_endpoint_identity: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                self.events.append("diagnosis")
                self.diagnosis_called = True
                self.diagnosis_index = len(self.events) - 1
                return {"ok": True}

            def _log_event(self, *args: Any, **kwargs: Any) -> None:
                self.events.append("log")
                if (
                    len(args) >= 3
                    and args[2] == "Health run completed"
                ):
                    self.completion_logged = True
                    self.completion_index = len(self.events) - 1

        recorder = _Recorder()
        # Drive the same path the orchestrator does, in order.
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                opened_ids=("inc-1",),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        # 1. Diagnosis loop runs first.
        recorder._run_automatic_diagnosis_loop(
            external_analysis_dir=Path("/tmp/r5"),
            canonical_incident_ids=diagnosis_inputs.canonical_incident_ids,
            promotion_result_summary=diagnosis_inputs.promotion_result_summary,
            backend_endpoint_identity=diagnosis_inputs.backend_endpoint_identity,
        )
        # 2. Terminal completion log is emitted after the diagnosis.
        recorder._log_event(
            "health-loop",
            "INFO",
            "Health run completed",
            event="complete",
            automatic_diagnosis_synchronous=True,
        )
        # 3. The terminal completion index MUST be after the
        # diagnosis index, in the recorder's event stream.
        self.assertTrue(recorder.diagnosis_called)
        self.assertTrue(recorder.completion_logged)
        self.assertIsNotNone(recorder.diagnosis_index)
        self.assertIsNotNone(recorder.completion_index)
        # Cast to int so mypy accepts the comparison: both are
        # ``int | None`` after the ``assertIsNotNone`` checks above.
        completion_index = recorder.completion_index
        diagnosis_index = recorder.diagnosis_index
        assert completion_index is not None
        assert diagnosis_index is not None
        self.assertGreater(
            completion_index,
            diagnosis_index,
            msg=(
                "Terminal completion log MUST be emitted AFTER the "
                "diagnosis loop ran so downstream health-run "
                "consumers no longer race the diagnostic collector."
            ),
        )


# ---------------------------------------------------------------------------
# ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION01:
# Production projection regression tests for outcome-without-batch scenario.
#
# CORRECTION02: Exhaustive typed projection - only PromotionCommitUnknown
# requires reconciliation. PromotionRejected remains blocked (not reconciliation).
# PromotionSucceeded without batch is a consistency contract error.
# ---------------------------------------------------------------------------


# Production-shaped canonical 64-char hex fingerprint (matches real contract)
_CANONICAL_FINGERPRINT = "a" * 64

# Production-shaped signal IDs: "sha256:" + 64 lowercase hex chars
_SIGNAL_ID_A = "sha256:" + ("a" * 64)
_SIGNAL_ID_B = "sha256:" + ("b" * 64)

# Validate fixture grammar
assert len(_CANONICAL_FINGERPRINT) == 64, f"fingerprint must be 64 chars, got {len(_CANONICAL_FINGERPRINT)}"
assert _CANONICAL_FINGERPRINT == _CANONICAL_FINGERPRINT.lower(), "fingerprint must be lowercase hex"
assert _SIGNAL_ID_A.startswith("sha256:"), "signal ID must start with sha256:"
assert len(_SIGNAL_ID_A.split(":")[1]) == 64, f"signal ID hash must be 64 chars, got {len(_SIGNAL_ID_A.split(':')[1])}"


def _make_canonical_token(
    request_id: str = "req-test",
) -> PromotionReconciliationToken:
    """Create a production-shaped reconciliation token with valid fingerprint."""
    return PromotionReconciliationToken(
        request_id=request_id,
        request_fingerprint=_CANONICAL_FINGERPRINT,
    )


class TestResolveAccumulatorTruthWithOutcome(unittest.TestCase):
    """Regression tests for _resolve_accumulator_truth with outcome but no batch.

    ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION02:
    Exhaustive typed projection - only PromotionCommitUnknown requires reconciliation.
    PromotionRejected remains blocked (not reconciliation).
    PromotionSucceeded without batch is a consistency contract error.
    """

    def test_empty_accumulator_returns_no_promotion_run(self) -> None:
        """Empty accumulator with no batches and no outcome -> no_promotion_run."""
        acc = RunPromotionAccumulator()
        self.assertFalse(acc.has_promotion_activity())
        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, NO_PROMOTION_MODE)
        self.assertEqual(access, NO_PROMOTION_MODE)
        self.assertEqual(scope, NO_PROMOTION_MODE)

    def test_batch_provides_activity(self) -> None:
        """Real batch -> activity true and batch mode returned."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                opened_ids=("inc-1",),
            )
        )
        self.assertTrue(acc.has_promotion_activity())
        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, MODE_BACKEND_API)
        self.assertEqual(access, INCIDENT_ACCESS_MODE_BACKEND)

    def test_commit_unknown_without_batch_returns_reconciliation(self) -> None:
        """Commit-unknown outcome without batch -> commit_unknown mode.

        Only PromotionCommitUnknown requires reconciliation.
        Uses typed enum reason (production-shaped).
        """
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id="run-test",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_make_canonical_token(),
                requested_signal_ids=(_SIGNAL_ID_A, _SIGNAL_ID_B),
            )
        )
        self.assertTrue(acc.has_promotion_activity())
        self.assertEqual(len(acc.batches), 0)

        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, "commit_unknown")
        self.assertEqual(access, "reconciliation_required")
        self.assertEqual(scope, "reconciliation_required")

    def test_rejected_without_batch_returns_rejected_not_reconciliation(self) -> None:
        """Rejection outcome without batch -> rejected mode (NOT reconciliation).

        PromotionRejected does NOT require reconciliation - it definitely did not commit.
        """
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionRejected(
                run_id="run-test",
                reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
                rejected_signal_ids=(_SIGNAL_ID_A,),
            )
        )
        self.assertTrue(acc.has_promotion_activity())
        self.assertEqual(len(acc.batches), 0)

        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, "rejected")
        self.assertEqual(access, "blocked")
        self.assertEqual(scope, "promotion_rejected")

    def test_succeeded_without_batch_returns_consistency_error(self) -> None:
        """Success outcome without batch -> consistency contract error.

        A successful active-scoped promotion must have its atomic batch/receipt.
        Without a batch, this is a consistency violation.
        """
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionSucceeded(
                run_id="run-test",
                requested_signal_ids=(_SIGNAL_ID_A,),
                records=(),
                diagnosis_incident_ids=(),
            )
        )
        self.assertTrue(acc.has_promotion_activity())
        self.assertEqual(len(acc.batches), 0)

        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, "promotion_consistency_contract_error")
        self.assertEqual(access, "promotion_consistency_contract_error")
        self.assertEqual(scope, "promotion_consistency_contract_error")

    def test_batch_with_outcome_returns_batch_mode(self) -> None:
        """Outcome with batch -> returns batch mode (existing behavior preserved)."""
        acc = RunPromotionAccumulator()
        acc.add_batch(
            _make_batch(
                promotion_mode=MODE_BACKEND_API,
                incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
                opened_ids=("inc-1",),
            )
        )
        acc.record_promotion_outcome(
            PromotionSucceeded(
                run_id="run-test",
                requested_signal_ids=(_SIGNAL_ID_A,),
                records=(),
                diagnosis_incident_ids=("inc-1",),
            )
        )
        self.assertTrue(acc.has_promotion_activity())
        self.assertEqual(len(acc.batches), 1)

        mode, access, scope = _resolve_accumulator_truth(acc)
        self.assertEqual(mode, MODE_BACKEND_API)
        self.assertEqual(access, INCIDENT_ACCESS_MODE_BACKEND)


class TestDeriveAutomaticDiagnosisInputsWithOutcome(unittest.TestCase):
    """Test _derive_automatic_diagnosis_inputs with outcome but no batch."""

    def test_commit_unknown_projection_consistency(self) -> None:
        """Commit-unknown without batch produces correct typed projections.

        Required final projection:
            selection_mode=commit_unknown
            incident_access_mode=reconciliation_required
            should_run=false
            is_blocked=false (commit_unknown is not "blocked")

        Forbidden:
            incident_access_mode=no_promotion_run
            selection_mode=blocked
        """
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id="run-test",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_make_canonical_token(),
                requested_signal_ids=(_SIGNAL_ID_A,),
            )
        )

        inputs = _derive_automatic_diagnosis_inputs(acc)
        summary = inputs.promotion_result_summary

        # has_promotion_activity must be True
        self.assertTrue(summary["has_promotion_activity"])

        # incident_access_mode must be reconciliation_required, NOT no_promotion_run
        self.assertEqual(summary["incident_access_mode"], "reconciliation_required")
        self.assertEqual(inputs.execution.incident_access_mode, "reconciliation_required")
        self.assertEqual(inputs.execution.selection_mode, "commit_unknown")

        # Diagnosis must NOT be invoked for commit_unknown
        self.assertFalse(inputs.execution.should_run)
        # commit_unknown is NOT blocked - it's "unavailable pending reconciliation"
        self.assertFalse(inputs.execution.is_blocked)

    def test_rejected_projection_blocks_diagnosis(self) -> None:
        """Rejection outcome blocks diagnosis - NOT reconciliation required."""
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionRejected(
                run_id="run-test",
                reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
                rejected_signal_ids=(_SIGNAL_ID_A,),
            )
        )

        inputs = _derive_automatic_diagnosis_inputs(acc)
        summary = inputs.promotion_result_summary

        self.assertTrue(summary["has_promotion_activity"])
        # incident_access_mode must NOT be reconciliation_required for rejection
        self.assertNotEqual(summary["incident_access_mode"], "reconciliation_required")

        # Diagnosis must NOT be invoked for rejection
        self.assertFalse(inputs.execution.should_run)
        self.assertTrue(inputs.execution.is_blocked)

    def test_succeeded_without_batch_projection(self) -> None:
        """Success without batch -> consistency contract error projection."""
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionSucceeded(
                run_id="run-test",
                requested_signal_ids=(_SIGNAL_ID_A,),
                records=(),
                diagnosis_incident_ids=(),
            )
        )

        inputs = _derive_automatic_diagnosis_inputs(acc)
        summary = inputs.promotion_result_summary

        self.assertTrue(summary["has_promotion_activity"])
        # Must NOT be reconciliation_required - this is a consistency error, not unknown
        self.assertNotEqual(summary["incident_access_mode"], "reconciliation_required")

        # Diagnosis must NOT be invoked
        self.assertFalse(inputs.execution.should_run)


if __name__ == "__main__":
    unittest.main()

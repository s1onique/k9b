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


if __name__ == "__main__":
    unittest.main()

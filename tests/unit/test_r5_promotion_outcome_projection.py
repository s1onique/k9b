"""R5 outcome-without-batch projection tests.

Regression tests for _resolve_accumulator_truth with outcome but no batch.

ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION02:
Exhaustive typed projection - only PromotionCommitUnknown requires reconciliation.
PromotionRejected remains blocked (not reconciliation).
PromotionSucceeded without batch is a consistency contract error.

Split from:
    test_r5_orchestration_proof.py
For:
    ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION06
"""

from __future__ import annotations

import unittest

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
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.health.loop_runner_execute import (
    NO_PROMOTION_MODE,
    _derive_automatic_diagnosis_inputs,
    _resolve_accumulator_truth,
)

_SIGNAL_ID_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_SIGNAL_ID_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _make_canonical_token() -> PromotionReconciliationToken:
    return PromotionReconciliationToken(
        request_id="canonical-request-id",
        request_fingerprint="canonical-fingerprint",
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


class TestResolveAccumulatorTruthWithOutcome(unittest.TestCase):
    """Regression tests for _resolve_accumulator_truth with outcome but no batch."""

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
    """Regression tests for _derive_automatic_diagnosis_inputs with outcome but no batch."""

    def test_commit_unknown_with_signal_ids_produces_empty_diagnosis(self) -> None:
        """Commit-unknown dispatch has no diagnosis to hand off."""
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id="run-test",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_make_canonical_token(),
                requested_signal_ids=(_SIGNAL_ID_A,),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), [])
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["promotion_mode"],
            "commit_unknown",
        )

    def test_rejected_with_signal_ids_produces_empty_diagnosis(self) -> None:
        """Rejected dispatch has no diagnosis to hand off."""
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionRejected(
                run_id="run-test",
                reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
                rejected_signal_ids=(_SIGNAL_ID_A,),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), [])
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["promotion_mode"],
            "rejected",
        )

    def test_succeeded_without_records_produces_empty_diagnosis(self) -> None:
        """Success without records has nothing to hand off."""
        acc = RunPromotionAccumulator()
        acc.record_promotion_outcome(
            PromotionSucceeded(
                run_id="run-test",
                requested_signal_ids=(_SIGNAL_ID_A,),
                records=(),
                diagnosis_incident_ids=(),
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), [])

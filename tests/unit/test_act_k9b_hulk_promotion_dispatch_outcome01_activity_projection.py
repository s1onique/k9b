"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 activity projection tests.

Regression tests for has_promotion_activity invariant.

Required invariant:
    has_promotion_activity = bool(batches) OR promotion_outcome is not None

Cases:
    - empty accumulator -> False
    - successful batch -> True
    - rejected outcome without batch -> True
    - commit-unknown outcome without batch -> True
    - dispatch absent -> final no_promotion_run
    - dispatch commit-unknown -> final reconciliation_required

Split from:
    test_act_k9b_hulk_promotion_dispatch_outcome01_accumulator_telemetry.py
For:
    ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION06
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)

RUN_ID = "run-2026-07-15T0350Z"

# Production-shaped signal IDs: "sha256:" + 64 lowercase hex chars
_SIGNAL_ID_A = "sha256:" + ("a" * 64)
_SIGNAL_ID_B = "sha256:" + ("b" * 64)

# Production-shaped canonical fingerprint (matches real contract)
_CANONICAL_FINGERPRINT = "c" * 64

# Validate fixture grammar
assert len(_SIGNAL_ID_A.split(":")[1]) == 64, f"signal ID hash must be 64 chars, got {len(_SIGNAL_ID_A.split(':')[1])}"
assert _SIGNAL_ID_A.startswith("sha256:"), "signal ID must start with sha256:"
assert len(_CANONICAL_FINGERPRINT) == 64, f"fingerprint must be 64 chars, got {len(_CANONICAL_FINGERPRINT)}"
assert _CANONICAL_FINGERPRINT == _CANONICAL_FINGERPRINT.lower(), "fingerprint must be lowercase hex"


def _token(
    request_id: str = "req-abc",
) -> PromotionReconciliationToken:
    """Create a production-shaped reconciliation token with valid fingerprint."""
    return PromotionReconciliationToken(
        request_id=request_id,
        request_fingerprint=_CANONICAL_FINGERPRINT,
    )


class TestHasPromotionActivity:
    """Regression tests for has_promotion_activity invariant."""

    def test_empty_accumulator_has_no_activity(self) -> None:
        """Empty accumulator with no batches and no outcome -> no activity."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False

    def test_batch_provides_activity(self) -> None:
        """A recorded batch provides promotion activity."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PROMOTION_OUTCOME_OPENED,
            PromotionRecord,
        )
        from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            IncidentPromotionResult,
        )

        accumulator = RunPromotionAccumulator()
        record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="inc-1",
            promotion_outcome=PROMOTION_OUTCOME_OPENED,
        )
        batch = PromotionBatch(
            promotion_result=IncidentPromotionResult(
                ok=True,
                scanned=1,
                firing=1,
                opened_incidents=1,
                updated_incidents=0,
                skipped_duplicates=0,
                errors=0,
                error_messages=(),
                promotion_mode="backend-api",
                opened_incident_ids=("inc-1",),
                updated_incident_ids=(),
                promotion_records=[record.to_dict()],
                unique_candidate_count=1,
                promotion_scan_scope="test",
                incident_access_mode="backend",
            ),
            promotion_records=(record,),
            source_kind="alertmanager",
            cluster_context="test",
            snapshot_bundle_id=None,
        )
        accumulator.add_batch(batch)
        assert accumulator.has_promotion_activity() is True
        assert len(accumulator.batches) == 1

    def test_rejected_outcome_without_batch_has_activity(self) -> None:
        """Rejection outcome without batch proves dispatch occurred."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionRejected(
                run_id=RUN_ID,
                reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
                rejected_signal_ids=(_SIGNAL_ID_A,),
            )
        )
        assert accumulator.has_promotion_activity() is True

    def test_commit_unknown_outcome_without_batch_has_activity(self) -> None:
        """Commit-unknown outcome without batch proves dispatch occurred.

        This is the core regression: a commit-unknown dispatch was previously
        projecting as no_promotion_run because has_promotion_activity only
        checked bool(batches). With the fix, a recorded outcome proves
        promotion activity even without a successful batch append.
        """
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
                reconciliation_token=_token(),
                requested_signal_ids=(_SIGNAL_ID_A,),
            )
        )
        assert accumulator.has_promotion_activity() is True

    def test_succeeded_outcome_without_batch_has_activity(self) -> None:
        """Success outcome without batch proves dispatch occurred."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=(_SIGNAL_ID_A,),
                records=(),
                diagnosis_incident_ids=(),
            )
        )
        assert accumulator.has_promotion_activity() is True

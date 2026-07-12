"""ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R7 ordered-sequence contract tests.

R7 (item 3): every backend-authoritative ``PromotionBatch`` is validated
against the ordered-sequence-with-multiplicity contract BEFORE
``RunPromotionAccumulator.add_batch`` mutates its state. A rejected
batch leaves the accumulator unchanged and raises
:class:`PromotionConsistencyContractError`. Tests below cover the
ordered-sequence contract failure modes that production must reject.

R7 (item 4): the contract terminology is "ordered sequence with
multiplicity", not "multiset". The tests below assert the new wording.

The contract requires validation of:
* ``batch.promotion_records``
* ``batch.opened_incident_ids``
* ``batch.updated_incident_ids``
* ``batch.opened_incidents``
* ``batch.updated_incidents``

Validation runs BEFORE accumulator mutation. Arrays reconstructed from
the records themselves are NOT used; the dispatcher-supplied arrays
must equal the ordered sequence of canonical IDs on opened/updated
records with multiplicity.
"""

from __future__ import annotations

import os
import unittest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    PromotionConsistencyContractError,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND as DISPATCH_BACKEND,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_LOCAL as DISPATCH_LOCAL,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    IncidentPromotionResult,
)


def _teardown() -> None:
    for var in (
        "K9B_BACKEND_INTERNAL_URL",
        "K9B_INTERNAL_API_TOKEN",
        "K9B_INCIDENT_STORE_BACKEND",
        "K9B_PROCESS_ROLE",
        "K9B_INCIDENT_PROMOTION_MODE",
        "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
    ):
        os.environ.pop(var, None)


def _backend_batch(
    *,
    opened_incidents: int = 1,
    updated_incidents: int = 0,
    opened_ids: tuple[str, ...] = ("incident-1",),
    updated_ids: tuple[str, ...] = (),
    records: tuple[PromotionRecord, ...] = (
        PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
    ),
) -> PromotionBatch:
    """Build a backend-authoritative batch for the add_batch validator tests."""
    return PromotionBatch(
        promotion_result=IncidentPromotionResult(
            ok=True,
            scanned=opened_incidents + updated_incidents,
            firing=opened_incidents + updated_incidents,
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            skipped_duplicates=0,
            errors=0,
            promotion_mode="backend-api",
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            promotion_records=(),  # canonical IDs live in ``records``
            unique_candidate_count=opened_incidents + updated_incidents,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=DISPATCH_BACKEND,
        ),
        promotion_records=records,
        source_kind="alertmanager",
    )


class TestRunPromotionAccumulatorBatchValidation(unittest.TestCase):
    """R7 (item 3): backend-authoritative batch validation before mutation."""

    def setUp(self) -> None:
        _teardown()
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"

    def tearDown(self) -> None:
        _teardown()

    def test_equal_length_wrong_id_rejected(self) -> None:
        """Equal-length but wrong ID MUST be rejected (R7 item 3)."""
        accumulator = RunPromotionAccumulator()
        bad_batch = _backend_batch(
            opened_ids=("incident-1", "incident-WRONG"),
            records=(
                PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
                PromotionRecord("cand-2", "incident-2", PROMOTION_OUTCOME_OPENED),
            ),
        )
        with self.assertRaises(PromotionConsistencyContractError):
            accumulator.add_batch(bad_batch)
        # The rejected batch left the accumulator unchanged.
        assert accumulator.promotion_records == []
        assert accumulator.batches == []
        assert accumulator.canonical_incident_ids() == []

    def test_valid_duplicate_canonical_ids_accepted(self) -> None:
        """Valid duplicate canonical IDs (many->one collapse) MUST be accepted."""
        accumulator = RunPromotionAccumulator()
        records = (
            PromotionRecord("cand-1", "incident-shared", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-2", "incident-shared", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-3", "incident-other", PROMOTION_OUTCOME_OPENED),
        )
        batch = _backend_batch(
            opened_incidents=3,
            updated_incidents=0,
            opened_ids=("incident-shared", "incident-shared", "incident-other"),
            records=records,
        )
        accumulator.add_batch(batch)
        # The accumulator carries the typed records and the canonical IDs.
        assert len(accumulator.promotion_records) == 3
        assert accumulator.canonical_incident_ids() == [
            "incident-shared",
            "incident-other",
        ]

    def test_wrong_multiplicity_rejected(self) -> None:
        """Wrong multiplicity MUST be rejected (R7 item 3)."""
        accumulator = RunPromotionAccumulator()
        records = (
            PromotionRecord("cand-1", "incident-x", PROMOTION_OUTCOME_UPDATED),
            PromotionRecord("cand-2", "incident-x", PROMOTION_OUTCOME_UPDATED),
        )
        # Two records, but the updated_incident_ids only has one entry.
        bad_batch = _backend_batch(
            opened_incidents=0,
            updated_incidents=2,
            updated_ids=("incident-x",),
            records=records,
        )
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            accumulator.add_batch(bad_batch)
        # The error message uses the new ordered-sequence-with-multiplicity
        # wording (R7 item 4).
        self.assertIn(
            "ordered sequence",
            str(ctx.exception),
        )
        # The accumulator was NOT mutated.
        assert accumulator.batches == []

    def test_reordered_ids_rejected_under_ordered_sequence_contract(self) -> None:
        """Reordered IDs MUST be rejected under the ordered-sequence contract (R7 item 3/4)."""
        accumulator = RunPromotionAccumulator()
        records = (
            PromotionRecord("cand-1", "inc-a", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-2", "inc-b", PROMOTION_OUTCOME_OPENED),
        )
        # The authoritative array is reordered vs the records' canonical
        # ID order. The ordered-sequence contract rejects this even
        # though a multiset comparison would accept it.
        bad_batch = _backend_batch(
            opened_incidents=2,
            updated_incidents=0,
            opened_ids=("inc-b", "inc-a"),
            records=records,
        )
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            accumulator.add_batch(bad_batch)
        self.assertIn(
            "ordered sequence",
            str(ctx.exception),
        )
        assert accumulator.batches == []

    def test_local_batch_does_not_trigger_strict_contract(self) -> None:
        """Local-mode batches are NOT subject to the strict ordered-sequence contract.

        Local promotion uses synthesized ``<aggregate>`` records that do
        not carry authoritative canonical IDs. R7 leaves the local
        contract as-is and only enforces the contract for
        ``incident_access_mode == "backend"`` (R7 item 3).
        """
        accumulator = RunPromotionAccumulator()
        # Build a local-mode batch whose updated_ids is in record order
        # but uses a synthesized ``<aggregate>``-style record. This is
        # the legacy R4 shape; add_batch MUST accept it.
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            IncidentPromotionResult as Ipr,
        )

        local_result = Ipr(
            ok=True,
            scanned=1,
            firing=1,
            opened_incidents=0,
            updated_incidents=1,
            skipped_duplicates=0,
            errors=0,
            promotion_mode="local",
            opened_incident_ids=(),
            updated_incident_ids=("incident-l1",),
            promotion_records=(),
            unique_candidate_count=1,
            promotion_scan_scope="local_promotion",
            incident_access_mode=DISPATCH_LOCAL,
        )
        local_batch = PromotionBatch(
            promotion_result=local_result,
            promotion_records=(
                PromotionRecord(
                    "<aggregate>", "incident-l1", PROMOTION_OUTCOME_UPDATED
                ),
            ),
            source_kind="alertmanager",
        )
        # Local batches are accepted; the strict contract is only
        # enforced for backend-mode batches.
        accumulator.add_batch(local_batch)
        assert len(accumulator.batches) == 1


if __name__ == "__main__":
    unittest.main()
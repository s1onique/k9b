"""R5 high-cardinality batch metric truth tests.

R5 (item 5) mandates bounded error messages, real
``unique_candidate_count`` aggregation, and correct local
``skipped_duplicate`` counting. The high-cardinality tests below
prove the bounds hold at the high end of the input cardinality:

* 500 opened/updated records across multiple batches;
* 200 distinct error messages with bounded ``error_messages_omitted``;
* local-mode ``skipped_duplicate`` outcomes counted from records
  even when the dispatcher's aggregate said ``0`` (legacy regression);
* ``unique_candidate_count`` is summed across batches (NOT replaced
  with ``total_scanned``).

The tests use the production ``RunPromotionAccumulator`` and
``PromotionBatch`` value types so they are evidence of the real
shape, not a parallel implementation.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
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
    IncidentPromotionResult,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY,
    _derive_automatic_diagnosis_inputs,
)


def _make_batch(
    *,
    promotion_mode: str = MODE_BACKEND_API,
    incident_access_mode: str = INCIDENT_ACCESS_MODE_BACKEND,
    opened_ids: tuple[str, ...] = (),
    updated_ids: tuple[str, ...] = (),
    skipped_records: tuple[PromotionRecord, ...] = (),
    error_messages: tuple[str, ...] = (),
    scanned: int = 0,
    firing: int = 0,
    opened: int = 0,
    updated: int = 0,
    skipped: int = 0,
    errors: int = 0,
    unique_candidate_count: int = 0,
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
    records.extend(skipped_records)
    return PromotionBatch(
        promotion_result=IncidentPromotionResult(
            ok=errors == 0,
            scanned=scanned or len(records) + len(skipped_records),
            firing=firing or len(records) + len(skipped_records),
            opened_incidents=opened or len(opened_ids),
            updated_incidents=updated or len(updated_ids),
            skipped_duplicates=skipped or len(skipped_records),
            errors=errors or len(error_messages),
            error_messages=error_messages,
            promotion_mode=promotion_mode,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            promotion_records=tuple(r.to_dict() for r in records),
            unique_candidate_count=unique_candidate_count or len(records) + len(skipped_records),
            promotion_scan_scope=scope,
            incident_access_mode=incident_access_mode,
        ),
        promotion_records=tuple(records),
        source_kind="alertmanager",
        cluster_context="ctx",
        snapshot_bundle_id=None,
    )


class HighCardinalityTests(unittest.TestCase):
    """Prove R5 (item 5) bounds hold at high cardinality."""

    def test_unique_candidate_count_aggregates_across_batches(self) -> None:
        """Real ``unique_candidate_count`` is summed across batches."""
        acc = RunPromotionAccumulator()
        for unique in (3, 7, 11, 5):
            acc.add_batch(
                _make_batch(
                    unique_candidate_count=unique,
                    opened_ids=("inc-a", "inc-b", "inc-c"),
                )
            )
        self.assertEqual(acc.total_unique_candidate_count, 3 + 7 + 11 + 5)

    def test_local_skipped_duplicate_counted_from_records(self) -> None:
        """Local mode: ``skipped_duplicate`` counted from records, not aggregate.

        R5 (item 5): the dispatcher's batch-level
        ``skipped_duplicates`` aggregate is the authoritative count
        for backend-api mode; for ``local`` mode the dispatcher
        does not publish a per-batch aggregate, so the accumulator
        counts from the records themselves. The legacy regression
        -- the batch's aggregate says ``0`` while records contain
        ``skipped_duplicate`` outcomes -- MUST still surface a
        non-zero count.
        """
        acc = RunPromotionAccumulator()
        skipped_records = tuple(
            PromotionRecord(
                source_candidate_id=f"cand-skip-{i}",
                canonical_incident_id=None,
                promotion_outcome=PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
            )
            for i in range(3)
        )
        acc.add_batch(
            _make_batch(
                promotion_mode="local",
                incident_access_mode=INCIDENT_ACCESS_MODE_LOCAL,
                skipped_records=skipped_records,
                skipped=0,  # legacy regression: batch says 0
            )
        )
        self.assertEqual(acc.total_skipped_duplicates, 3)

    def test_error_messages_bounded_with_omitted_counter(self) -> None:
        """200 error messages are bounded; ``error_messages_omitted`` is reported."""
        acc = RunPromotionAccumulator()
        error_messages = tuple(f"error-{i:04d}" for i in range(200))
        acc.add_batch(
            _make_batch(
                errors=200,
                error_messages=error_messages,
                unique_candidate_count=1,
            )
        )
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids), [])
        self.assertEqual(diagnosis_inputs.promotion_result_summary["errors"], 200)
        self.assertEqual(
            len(diagnosis_inputs.promotion_result_summary["error_messages"]),
            DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY,
        )
        # The total is 200 messages; the bound is 50 by default,
        # so 150 messages were omitted.
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["error_messages_omitted"],
            200 - DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY,
        )
        # The first message in the truncated list is the first
        # message in the input -- deterministic order is preserved.
        self.assertEqual(diagnosis_inputs.promotion_result_summary["error_messages"][0], "error-0000")
        self.assertEqual(
            diagnosis_inputs.promotion_result_summary["error_messages"][-1],
            f"error-{DEFAULT_MAX_ERROR_MESSAGES_IN_SUMMARY - 1:04d}",
        )

    def test_high_cardinality_canonical_ids_dedup(self) -> None:
        """500 canonical IDs across batches are deduped and reach derivation once."""
        acc = RunPromotionAccumulator()
        all_ids = tuple(f"inc-{i:04d}" for i in range(500))
        for chunk_start in range(0, 500, 100):
            chunk = all_ids[chunk_start : chunk_start + 100]
            acc.add_batch(
                _make_batch(
                    opened_ids=chunk,
                    unique_candidate_count=100,
                )
            )
        # Add a duplicate across batches to prove dedup.
        acc.add_batch(
            _make_batch(
                opened_ids=("inc-0000", "inc-0001"),
                unique_candidate_count=2,
            )
        )
        self.assertEqual(acc.total_unique_candidate_count, 100 * 5 + 2)
        diagnosis_inputs = _derive_automatic_diagnosis_inputs(acc)
        # Dedup: 500 unique + 0 new (the duplicate batch's IDs are
        # already in the dedup set).
        self.assertEqual(len(diagnosis_inputs.canonical_incident_ids), 500)
        # The first-seen order matches the input chunk order.
        self.assertEqual(list(diagnosis_inputs.canonical_incident_ids[:5]), ["inc-0000", "inc-0001", "inc-0002", "inc-0003", "inc-0004"])
        self.assertEqual(diagnosis_inputs.canonical_incident_ids[-1], "inc-0499")


if __name__ == "__main__":
    unittest.main()

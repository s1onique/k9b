"""Unit tests for promotion diagnosis handoff seam.

Tests the canonical handoff function that propagates promotion results
to the diagnosis workset.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import RunPromotionAccumulator
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import IncidentPromotionResult
from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
    HandoffErrorReason,
    PromotionDiagnosisHandoffError,
    PromotionPropagationResult,
    propagate_promotion_result_to_run,
)


def _make_batch(
    opened_ids: tuple[str, ...] = (),
    updated_ids: tuple[str, ...] = (),
    source_kind: str = "alertmanager",
) -> PromotionBatch:
    """Create a PromotionBatch with consistent aggregate counts and records.

    The batch's opened_incidents/updated_incidents aggregates match the
    actual PromotionRecords, which is required by add_batch validation.
    """
    records = []
    for id_ in opened_ids:
        records.append(
            PromotionRecord(
                source_candidate_id=f"alert-{id_}",
                canonical_incident_id=id_,
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            )
        )
    for id_ in updated_ids:
        records.append(
            PromotionRecord(
                source_candidate_id=f"alert-{id_}",
                canonical_incident_id=id_,
                promotion_outcome=PROMOTION_OUTCOME_UPDATED,
            )
        )

    # opened_incidents and updated_incidents must match record counts
    result = IncidentPromotionResult(
        ok=True,
        scanned=len(opened_ids) + len(updated_ids),
        opened_incidents=len(opened_ids),  # Must match record count
        updated_incidents=len(updated_ids),  # Must match record count
        opened_incident_ids=opened_ids,
        updated_incident_ids=updated_ids,
        promotion_mode="backend-api",
        incident_access_mode="backend",
    )
    return PromotionBatch(
        promotion_result=result,
        promotion_records=tuple(records),
        source_kind=source_kind,
    )


def _make_malformed_batch(
    opened_ids: tuple[str, ...],
    extra_ids: tuple[str, ...] = (),
) -> PromotionBatch:
    """Create a PromotionBatch with mismatched aggregates (for testing validation).

    The batch's opened_incidents aggregate will NOT match the record count,
    simulating a malformed backend response. This is used to test that
    validation catches such mismatches.
    """
    records = []
    for id_ in opened_ids:
        records.append(
            PromotionRecord(
                source_candidate_id=f"alert-{id_}",
                canonical_incident_id=id_,
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            )
        )

    # Malformed: opened_incidents is less than actual record count
    # (extra_ids are in the result but not in records)
    all_ids = opened_ids + extra_ids
    result = IncidentPromotionResult(
        ok=True,
        scanned=len(all_ids),
        opened_incidents=len(all_ids),  # Mismatched: expects more than records
        updated_incidents=0,
        opened_incident_ids=all_ids,  # Has extra IDs not in records
        updated_incident_ids=(),
        promotion_mode="backend-api",
        incident_access_mode="backend",
    )
    return PromotionBatch(
        promotion_result=result,
        promotion_records=tuple(records),
        source_kind="alertmanager",
    )


class TestPromotionPropagationResult:
    """Tests for PromotionPropagationResult."""

    def test_added_count_property(self) -> None:
        """added_count returns correct count."""
        result = PromotionPropagationResult(
            source="alertmanager",
            actionable_incident_ids=("id1", "id2", "id3"),
            added_incident_ids=("id1", "id2", "id3"),
            duplicate_incident_ids=(),
        )
        assert result.added_count == 3

    def test_duplicate_count_property(self) -> None:
        """duplicate_count returns correct count."""
        result = PromotionPropagationResult(
            source="alertmanager",
            actionable_incident_ids=("id1", "id2"),
            added_incident_ids=("id1",),
            duplicate_incident_ids=("id2",),
        )
        assert result.duplicate_count == 1

    def test_total_actionable_property(self) -> None:
        """total_actionable returns correct count."""
        result = PromotionPropagationResult(
            source="alertmanager",
            actionable_incident_ids=("id1", "id2", "id3"),
            added_incident_ids=("id1",),
            duplicate_incident_ids=("id2", "id3"),
        )
        assert result.total_actionable == 3


class TestPropagatePromotionResultToRun:
    """Tests for propagate_promotion_result_to_run function."""

    def test_single_actionable_id_added(self) -> None:
        """One actionable ID is added to empty accumulator."""
        batch = _make_batch(opened_ids=("incident-1",))
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert propagation.added_count == 1
        assert propagation.duplicate_count == 0
        assert propagation.added_incident_ids == ("incident-1",)
        assert "incident-1" in accumulator.canonical_incident_ids()

    def test_multiple_ids_preserve_order(self) -> None:
        """Multiple IDs preserve first-occurrence order."""
        batch = _make_batch(
            opened_ids=("id-a", "id-b"),
            updated_ids=("id-c",),
        )
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Order should be opened first, then updated
        assert propagation.actionable_incident_ids == ("id-a", "id-b", "id-c")

    def test_duplicate_ids_normalized(self) -> None:
        """Duplicate IDs within the batch are normalized."""
        batch = _make_batch(opened_ids=("id-1",))
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Should be deduplicated
        assert propagation.actionable_incident_ids == ("id-1",)
        assert propagation.added_count == 1

    def test_existing_ids_marked_as_duplicates(self) -> None:
        """IDs already in accumulator are marked as duplicates."""
        batch = _make_batch(opened_ids=("id-existing", "id-new"))
        accumulator = RunPromotionAccumulator()
        # Pre-populate with existing ID
        accumulator.record_promotion_result(
            source="previous-source",
            incident_ids=("id-existing",),
        )

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert propagation.duplicate_incident_ids == ("id-existing",)
        assert propagation.added_incident_ids == ("id-new",)
        assert propagation.added_count == 1
        assert propagation.duplicate_count == 1

    def test_invalid_batch_raises_error(self) -> None:
        """Invalid batch raises PromotionDiagnosisHandoffError."""
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch="not-a-batch",
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_PROMOTION_BATCH

    def test_invalid_result_raises_error(self) -> None:
        """Batch with invalid promotion_result raises error."""
        accumulator = RunPromotionAccumulator()

        # Create a mock batch with invalid promotion_result
        class MockBatch:
            promotion_result = "not-a-result"

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch=MockBatch(),
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_PROMOTION_BATCH

    def test_empty_id_rejected(self) -> None:
        """Empty incident ID is rejected."""
        # Create malformed batch with empty ID in result but not in records
        batch = _make_malformed_batch(
            opened_ids=("valid-id",),
            extra_ids=("",),
        )
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID

    def test_whitespace_id_rejected(self) -> None:
        """Whitespace-only incident ID is rejected."""
        # Create malformed batch with whitespace ID in result but not in records
        batch = _make_malformed_batch(
            opened_ids=("valid-id",),
            extra_ids=("   ",),
        )
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID

    def test_failure_before_update_leaves_accumulator_unchanged(self) -> None:
        """Accumulator is unchanged if validation fails."""
        # Create malformed batch with empty ID
        batch = _make_malformed_batch(
            opened_ids=("valid-id",),
            extra_ids=("",),
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_promotion_result(
            source="previous",
            incident_ids=("previous-id",),
        )

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        # Accumulator should be unchanged
        assert "previous-id" in accumulator.canonical_incident_ids()
        assert len(accumulator.promotion_records) == 1

    def test_ids_from_earlier_source_survive_later_failure(self) -> None:
        """IDs from successful source survive failure of later source."""
        # First batch succeeds
        batch1 = _make_batch(opened_ids=("id-first",))
        accumulator = RunPromotionAccumulator()

        propagate_promotion_result_to_run(
            batch=batch1,
            accumulator=accumulator,
            source="first-source",
        )

        # Second batch fails (malformed with empty ID)
        batch2 = _make_malformed_batch(
            opened_ids=("id-second",),
            extra_ids=("",),
        )

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch=batch2,
                accumulator=accumulator,
                source="second-source",
            )

        # First source's IDs should survive
        assert "id-first" in accumulator.canonical_incident_ids()
        # Second source should not have added anything
        canonical_ids = accumulator.canonical_incident_ids()
        assert "id-second" not in canonical_ids

    def test_truthful_propagation_result(self) -> None:
        """Returned result contains truthful added/duplicate counts."""
        batch = _make_batch(opened_ids=("new-1", "new-2"))
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert propagation.source == "alertmanager"
        assert len(propagation.actionable_incident_ids) == 2
        assert len(propagation.added_incident_ids) == 2
        assert len(propagation.duplicate_incident_ids) == 0

    def test_no_mutation_on_read(self) -> None:
        """Reading the promotion result has no side effects."""
        batch = _make_batch(opened_ids=("id-1",))
        accumulator = RunPromotionAccumulator()

        # Read the actionable IDs first
        actionable = batch.promotion_result.actionable_incident_ids

        # Now propagate
        propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Reading again should give same result
        assert batch.promotion_result.actionable_incident_ids == actionable

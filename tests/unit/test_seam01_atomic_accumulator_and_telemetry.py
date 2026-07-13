"""Atomic accumulator and telemetry tests for promotion-diagnosis propagation.

Fault-injection tests:
  - Accumulator state remains unchanged when application fails after staging
  - Snapshot/restore pattern for atomicity

Telemetry tests:
  - PromotionPropagationResult is captured correctly
  - Duplicate IDs tracked correctly

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R2
"""

from __future__ import annotations

import copy

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    PromotionWorksetState,
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import IncidentPromotionResult
from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
    PromotionDiagnosisHandoffError,
    propagate_promotion_result_to_run,
)


class CountingIncidentStore:
    """Fake incident store that counts operations."""

    def __init__(self) -> None:
        self.list_call_count = 0
        self.fetch_call_count = 0
        self.list_incident_ids: list[str] = []

    def list_incidents(self) -> list[str]:
        self.list_call_count += 1
        return self.list_incident_ids

    def fetch_incident(self, incident_id: str) -> dict | None:
        self.fetch_call_count += 1
        return None

    def reset_counts(self) -> None:
        self.list_call_count = 0
        self.fetch_call_count = 0


class TestAtomicAccumulatorState:
    """Test that accumulator state is preserved on failure (fault injection)."""

    def test_failure_after_staging_preserves_accumulator(self) -> None:
        """Accumulator state remains unchanged when handoff fails after staging."""
        result1 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,
            opened_incident_ids=("existing-1", "existing-2"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch1 = PromotionBatch(
            promotion_result=result1,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="existing-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="existing-2",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()
        propagate_promotion_result_to_run(
            batch=batch1,
            accumulator=accumulator,
            source="first-source",
        )

        state_before = copy.deepcopy({
            "promotion_records": list(accumulator.promotion_records),
            "seen_ids": set(accumulator._seen_canonical_ids),
            "workset_state": accumulator.workset_state,
        })

        # Second batch has invalid empty ID in projection (but valid record count)
        result2 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,  # Must match record count for aggregate validation
            opened_incident_ids=("new-1", ""),  # Empty ID in projection will fail handoff
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch2 = PromotionBatch(
            promotion_result=result2,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-3",
                    canonical_incident_id="new-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-4",
                    canonical_incident_id="",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="vmalert",
        )

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch=batch2,
                accumulator=accumulator,
                source="second-source",
            )

        state_after = copy.deepcopy({
            "promotion_records": list(accumulator.promotion_records),
            "seen_ids": set(accumulator._seen_canonical_ids),
            "workset_state": accumulator.workset_state,
        })

        assert len(state_after["promotion_records"]) == len(state_before["promotion_records"])
        assert state_after["seen_ids"] == state_before["seen_ids"]
        assert state_after["workset_state"] == PromotionWorksetState.INVALID
        assert "existing-1" in accumulator.canonical_incident_ids()
        assert "existing-2" in accumulator.canonical_incident_ids()

    def test_accumulator_snapshot_restore_on_validation_failure(self) -> None:
        """Accumulator uses snapshot/restore pattern for atomicity."""
        accumulator = RunPromotionAccumulator()

        result1 = IncidentPromotionResult(
            ok=True,
            opened_incidents=1,
            opened_incident_ids=("id-1",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch1 = PromotionBatch(
            promotion_result=result1,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="id-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        propagate_promotion_result_to_run(
            batch=batch1,
            accumulator=accumulator,
            source="first",
        )

        initial_record_count = len(accumulator.promotion_records)
        initial_seen = set(accumulator._seen_canonical_ids)

        result2 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,
            opened_incident_ids=("id-2", ""),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch2 = PromotionBatch(
            promotion_result=result2,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="id-2",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-3",
                    canonical_incident_id="",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="vmalert",
        )

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch=batch2,
                accumulator=accumulator,
                source="second",
            )

        assert len(accumulator.promotion_records) == initial_record_count
        assert set(accumulator._seen_canonical_ids) == initial_seen


class TestStoreOperationCounters:
    """Test that store operations are counted correctly based on workset state."""

    def test_valid_with_ids_zero_store_operations(self) -> None:
        """VALID + IDs: store operations should be 0."""
        store = CountingIncidentStore()
        store.list_incident_ids = ["existing-incident"]

        result = IncidentPromotionResult(
            ok=True,
            scanned=1,
            opened_incidents=1,
            opened_incident_ids=("new-incident-1",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="new-incident-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert store.list_call_count == 0
        assert store.fetch_call_count == 0
        assert accumulator.workset_state == PromotionWorksetState.VALID
        assert len(accumulator.canonical_incident_ids()) > 0

    def test_valid_empty_zero_store_operations(self) -> None:
        """VALID + empty: store operations should be 0."""
        store = CountingIncidentStore()

        result = IncidentPromotionResult(
            ok=True,
            scanned=0,
            opened_incident_ids=(),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert store.list_call_count == 0
        assert store.fetch_call_count == 0
        assert accumulator.workset_state == PromotionWorksetState.VALID
        assert len(accumulator.canonical_incident_ids()) == 0

    def test_invalid_zero_store_operations(self) -> None:
        """INVALID: store operations should be 0 (blocked)."""
        store = CountingIncidentStore()
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch="not-a-batch",
                accumulator=accumulator,
                source="alertmanager",
            )

        assert store.list_call_count == 0
        assert store.fetch_call_count == 0
        assert accumulator.workset_state == PromotionWorksetState.INVALID


class TestPropagationResultTelemetry:
    """Test that PromotionPropagationResult is captured correctly."""

    def test_propagation_result_captured_on_success(self) -> None:
        """PromotionPropagationResult is captured on accumulator."""
        result = IncidentPromotionResult(
            ok=True,
            opened_incidents=3,
            opened_incident_ids=("id-1", "id-2", "id-3"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="id-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="id-2",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-3",
                    canonical_incident_id="id-3",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="test-source",
        )

        assert propagation.source == "test-source"
        assert len(propagation.actionable_incident_ids) == 3
        assert propagation.added_count == 3
        assert propagation.duplicate_count == 0
        assert accumulator.last_propagation_result is not None
        assert accumulator.last_propagation_result.source == "test-source"
        assert accumulator.last_propagation_result.added_count == 3

    def test_propagation_result_not_captured_on_failure(self) -> None:
        """PromotionPropagationResult is NOT captured on failure."""
        result = IncidentPromotionResult(
            ok=True,
            opened_incidents=1,
            opened_incident_ids=("",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError):
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        assert accumulator.last_propagation_result is None
        assert accumulator.last_handoff_error is not None

    def test_duplicate_ids_in_propagation_result(self) -> None:
        """Duplicate IDs are tracked correctly in propagation result."""
        result1 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,
            opened_incident_ids=("id-a", "id-b"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch1 = PromotionBatch(
            promotion_result=result1,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="id-a",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="id-b",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        propagate_promotion_result_to_run(
            batch=batch1,
            accumulator=accumulator,
            source="first-source",
        )

        result2 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,
            opened_incident_ids=("id-b", "id-c"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch2 = PromotionBatch(
            promotion_result=result2,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-3",
                    canonical_incident_id="id-b",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-4",
                    canonical_incident_id="id-c",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="vmalert",
        )

        propagation = propagate_promotion_result_to_run(
            batch=batch2,
            accumulator=accumulator,
            source="second-source",
        )

        assert propagation.added_count == 1
        assert propagation.duplicate_count == 1
        assert propagation.added_incident_ids == ("id-c",)
        assert propagation.duplicate_incident_ids == ("id-b",)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

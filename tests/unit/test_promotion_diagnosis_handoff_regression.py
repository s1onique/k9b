"""Live-failure regression test for promotion-diagnosis handoff seam.

SEAM01 contract enforcement:
- PromotionBatch has NO projection APIs (actionable_incident_ids, canonical_incident_ids)
- The only allowed access is via batch.promotion_result.actionable_incident_ids
- propagate_promotion_result_to_run() is the ONLY allowed handoff function
- Distinct telemetry for execution vs handoff vs propagation outcomes

This test proves:
1. Production code does NOT access forbidden projection APIs
2. The canonical handoff helper propagates IDs correctly to automatic diagnosis
3. Workset state is explicit, not inferred from ID tuple emptiness

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import PromotionRecord
from k8s_diag_agent.collect.incident_promotion_accumulator import RunPromotionAccumulator
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import IncidentPromotionResult


class TestPromotionBatchHasNoProjectionAPIs:
    """SEAM01: PromotionBatch MUST NOT expose ID projection APIs."""

    def test_batch_has_no_actionable_incident_ids_property(self) -> None:
        """PromotionBatch.actionable_incident_ids property does NOT exist.

        SEAM01 contract: The only allowed access is via
        batch.promotion_result.actionable_incident_ids
        """
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("id-1",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="alertmanager",
        )

        # SEAM01: PromotionBatch MUST NOT have actionable_incident_ids property
        assert not hasattr(batch, "actionable_incident_ids"), (
            "PromotionBatch MUST NOT expose actionable_incident_ids projection"
        )

    def test_batch_has_no_canonical_incident_ids_method(self) -> None:
        """PromotionBatch.canonical_incident_ids() method does NOT exist.

        SEAM01 contract: No projection APIs on the batch itself.
        """
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("id-1",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="alertmanager",
        )

        # SEAM01: PromotionBatch MUST NOT have canonical_incident_ids method
        assert not hasattr(batch, "canonical_incident_ids"), (
            "PromotionBatch MUST NOT expose canonical_incident_ids projection"
        )


class TestCanonicalHandoffHelperPropagatesIDs:
    """SEAM01: The canonical handoff helper propagates IDs to diagnosis."""

    def test_handoff_helper_propagates_to_accumulator(self) -> None:
        """Real handoff helper propagates IDs via accumulator."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        # Arrange: Real batch with one actionable ID
        result = IncidentPromotionResult(
            ok=True,
            scanned=35,
            firing=35,
            opened_incidents=1,
            updated_incidents=0,
            skipped_duplicates=34,
            errors=0,
            opened_incident_ids=("canonical-incident-001",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert:pod-oom",
                    canonical_incident_id="canonical-incident-001",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
            cluster_context="prod-cluster",
        )
        accumulator = RunPromotionAccumulator()

        # Act: Use the canonical handoff helper
        propagation_result = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Verify: Propagation result has correct IDs
        assert propagation_result.added_incident_ids == ("canonical-incident-001",)
        assert propagation_result.total_actionable == 1

        # Verify: Accumulator received the ID
        assert "canonical-incident-001" in accumulator.canonical_incident_ids()

    def test_handoff_with_empty_workset_successful_stop(self) -> None:
        """SEAM01: Valid empty workset = successful stop, zero store operations."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        # Arrange: Successful promotion with zero actionable IDs
        result = IncidentPromotionResult(
            ok=True,
            scanned=5,
            firing=5,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=5,
            errors=0,
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

        # Act: Handoff with empty workset
        propagation_result = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Verify: Empty tuple is valid, NOT an error
        assert propagation_result.actionable_incident_ids == ()
        assert propagation_result.added_incident_ids == ()
        assert propagation_result.total_actionable == 0

        # Verify: accumulator stays empty (zero store operations)
        assert accumulator.canonical_incident_ids() == []

    def test_handoff_failure_blocks_diagnosis(self) -> None:
        """SEAM01: Handoff failure blocks diagnosis, not store scan."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            HandoffErrorReason,
            PromotionDiagnosisHandoffError,
            propagate_promotion_result_to_run,
        )

        # Arrange: Accumulator with existing IDs
        accumulator = RunPromotionAccumulator()
        accumulator.record_promotion_result(
            source="alertmanager",
            incident_ids=("existing-incident",),
        )

        # Batch with invalid ID (empty string) - includes matching record
        # The empty ID in opened_incident_ids will fail validation
        result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            opened_incidents=2,  # Mismatch: says 2 but only 1 record
            updated_incidents=0,
            opened_incident_ids=("", "new-incident"),  # Invalid empty ID
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert:new",
                    canonical_incident_id="new-incident",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
        )

        # Act & Verify: Handoff raises with specific reason
        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID

        # Verify: Original IDs preserved (accumulator not corrupted)
        original_ids = accumulator.canonical_incident_ids()
        assert "existing-incident" in original_ids

    def test_multiple_batches_via_handoff_aggregate_correctly(self) -> None:
        """SEAM01: Multiple batches aggregate correctly via canonical handoff."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        # Arrange: Two batches from Alertmanager sources with consistent records
        accumulator = RunPromotionAccumulator()

        result1 = IncidentPromotionResult(
            ok=True,
            scanned=1,
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("incident-a",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch1 = PromotionBatch(
            promotion_result=result1,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert:a",
                    canonical_incident_id="incident-a",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
            cluster_context="cluster-1",
        )

        result2 = IncidentPromotionResult(
            ok=True,
            scanned=1,
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("incident-b",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch2 = PromotionBatch(
            promotion_result=result2,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert:b",
                    canonical_incident_id="incident-b",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
            cluster_context="cluster-2",
        )

        # Act: Use canonical handoff helper for both
        propagate_promotion_result_to_run(
            batch=batch1,
            accumulator=accumulator,
            source="alertmanager",
        )
        propagate_promotion_result_to_run(
            batch=batch2,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Verify: Both IDs present
        canonical_ids = accumulator.canonical_incident_ids()
        assert len(canonical_ids) == 2
        assert "incident-a" in canonical_ids
        assert "incident-b" in canonical_ids

        # Verify: selection_mode would be "explicit_incident_ids"
        assert len(canonical_ids) > 0


class TestPromotionWorksetState:
    """SEAM01: Workset state is explicit, not inferred from ID emptiness."""

    def test_workset_state_enum_exists(self) -> None:
        """PromotionWorksetState enum exists with required values."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            PromotionWorksetState,
        )

        # SEAM01: Required states
        assert hasattr(PromotionWorksetState, "VALID")
        assert hasattr(PromotionWorksetState, "INVALID")
        assert hasattr(PromotionWorksetState, "NOT_APPLICABLE")

        assert PromotionWorksetState.VALID.value == "valid"
        assert PromotionWorksetState.INVALID.value == "invalid"
        assert PromotionWorksetState.NOT_APPLICABLE.value == "not_applicable"

    def test_state_matrix_valid_with_ids(self) -> None:
        """VALID + IDs = explicit current-run diagnosis."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            opened_incidents=2,
            updated_incidents=0,
            opened_incident_ids=("id-1", "id-2"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert:1",
                    canonical_incident_id="id-1",
                    promotion_outcome="opened",
                ),
                PromotionRecord(
                    source_candidate_id="alert:2",
                    canonical_incident_id="id-2",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        # Act: Handoff with valid IDs
        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Verify: VALID state with non-empty IDs = explicit diagnosis
        assert len(propagation.added_incident_ids) == 2
        assert accumulator.canonical_incident_ids() == ["id-1", "id-2"]

    def test_state_matrix_valid_empty(self) -> None:
        """VALID + empty = successful stop, zero store operations."""
        from k8s_diag_agent.collect.promotion_diagnosis_handoff import (
            propagate_promotion_result_to_run,
        )

        result = IncidentPromotionResult(
            ok=True,
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

        # Act: Handoff with empty workset
        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        # Verify: VALID + empty = successful stop
        assert len(propagation.added_incident_ids) == 0
        assert accumulator.canonical_incident_ids() == []


class TestPromotionBatchContract:
    """Tests for PromotionBatch contract invariants (non-projection)."""

    def test_promotion_result_is_exposed(self) -> None:
        """PromotionBatch exposes promotion_result."""
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("id-1",),
            updated_incident_ids=(),
            promotion_mode="local",
            incident_access_mode="local",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="alertmanager",
        )

        assert batch.promotion_result is result
        assert batch.promotion_result.ok is True

    def test_actionable_incident_ids_via_result_only(self) -> None:
        """actionable_incident_ids accessed via promotion_result, not batch."""
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("id-1", "id-2"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="alertmanager",
        )

        # SEAM01: Access via promotion_result only
        assert batch.promotion_result.actionable_incident_ids == ("id-1", "id-2")

    def test_promotion_records_are_typed(self) -> None:
        """PromotionBatch.promotion_records contains typed PromotionRecord values."""
        records = (
            PromotionRecord(
                source_candidate_id="test",
                canonical_incident_id="id-1",
                promotion_outcome="opened",
            ),
        )
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("id-1",),
            updated_incident_ids=(),
            promotion_mode="local",
            incident_access_mode="local",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=records,
            source_kind="alertmanager",
        )

        assert len(batch.promotion_records) == 1
        assert isinstance(batch.promotion_records[0], PromotionRecord)
        assert batch.promotion_records[0].canonical_incident_id == "id-1"

    def test_source_kind_propagates(self) -> None:
        """Source kind is propagated through the batch."""
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=(),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(),
            source_kind="vmalert",
            cluster_context="test-cluster",
        )

        assert batch.source_kind == "vmalert"
        assert batch.cluster_context == "test-cluster"

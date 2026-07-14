"""Workset state machine tests for promotion-diagnosis propagation.

VALID + IDs:  workset_state=VALID, explicit IDs
VALID + empty: workset_state=VALID, no IDs
INVALID:      workset_state=INVALID, diagnosis blocked

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R2
"""

from __future__ import annotations

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
    HandoffErrorReason,
    PromotionDiagnosisHandoffError,
    propagate_promotion_result_to_run,
)


class TestWorksetStateMachine:
    """Test the workset state machine for promotion-to-diagnosis propagation."""

    def test_valid_with_ids_sets_state_and_captures_result(self) -> None:
        """VALID + IDs: workset_state=VALID, propagation result captured."""
        result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            opened_incidents=2,  # Must match count of opened records
            opened_incident_ids=("incident-1", "incident-2"),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch = PromotionBatch(
            promotion_result=result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="incident-1",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="incident-2",
                    promotion_outcome=PROMOTION_OUTCOME_OPENED,
                ),
            ),
            source_kind="alertmanager",
        )
        accumulator = RunPromotionAccumulator()

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert accumulator.workset_state == PromotionWorksetState.VALID
        assert accumulator.last_propagation_result is not None
        assert accumulator.last_propagation_result.added_count == 2
        assert propagation.added_count == 2
        assert propagation.duplicate_count == 0

    def test_valid_empty_sets_state_valid(self) -> None:
        """VALID + empty: workset_state=VALID, no IDs added."""
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

        propagation = propagate_promotion_result_to_run(
            batch=batch,
            accumulator=accumulator,
            source="alertmanager",
        )

        assert accumulator.workset_state == PromotionWorksetState.VALID
        assert propagation.added_count == 0
        assert propagation.duplicate_count == 0
        assert len(list(accumulator.canonical_incident_ids())) == 0

    def test_invalid_batch_raises_and_marks_invalid(self) -> None:
        """INVALID: raises error and marks workset INVALID."""
        accumulator = RunPromotionAccumulator()

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch="not-a-batch",
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_PROMOTION_BATCH
        assert accumulator.workset_state == PromotionWorksetState.INVALID
        assert accumulator.last_handoff_error is not None
        assert accumulator.last_handoff_error.reason_code == HandoffErrorReason.INVALID_PROMOTION_BATCH

    def test_invalid_incident_id_raises_and_marks_invalid(self) -> None:
        """INVALID: empty ID raises error and marks workset INVALID."""
        result = IncidentPromotionResult(
            ok=True,
            scanned=1,
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

        with pytest.raises(PromotionDiagnosisHandoffError) as exc_info:
            propagate_promotion_result_to_run(
                batch=batch,
                accumulator=accumulator,
                source="alertmanager",
            )

        assert exc_info.value.reason_code == HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID
        assert accumulator.workset_state == PromotionWorksetState.INVALID

    def test_not_applicable_default_state(self) -> None:
        """NOT_APPLICABLE: default state when no handoff has occurred."""
        accumulator = RunPromotionAccumulator()

        assert accumulator.workset_state == PromotionWorksetState.NOT_APPLICABLE
        assert accumulator.last_handoff_error is None
        assert accumulator.last_propagation_result is None

    def test_multiple_sources_last_wins_for_workset_state(self) -> None:
        """Workset state reflects last handoff result."""
        result1 = IncidentPromotionResult(
            ok=True,
            opened_incidents=1,  # Must match count of opened records
            opened_incident_ids=("id-first",),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch1 = PromotionBatch(
            promotion_result=result1,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-1",
                    canonical_incident_id="id-first",
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

        assert accumulator.workset_state == PromotionWorksetState.VALID

        result2 = IncidentPromotionResult(
            ok=True,
            opened_incidents=2,  # Must match count of opened records
            opened_incident_ids=("id-second", ""),
            updated_incident_ids=(),
            promotion_mode="backend-api",
            incident_access_mode="backend",
        )
        batch2 = PromotionBatch(
            promotion_result=result2,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="alert-2",
                    canonical_incident_id="id-second",
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
                source="second-source",
            )

        assert accumulator.workset_state == PromotionWorksetState.INVALID
        assert "id-first" in accumulator.canonical_incident_ids()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

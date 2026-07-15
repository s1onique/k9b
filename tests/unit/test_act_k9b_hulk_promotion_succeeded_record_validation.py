"""Unit tests for PromotionSucceeded record validation.

Tests that PromotionSucceeded.__post_init__ enforces that all records
are PromotionRecord instances at construction time.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01-CLOSURE.

Reviewer blocking item: the static annotation `tuple[PromotionRecord, ...]`
is not enforced at runtime. The fallback classifier path uses `typing.cast()`
which is a no-op. This test proves that strings and tuples are rejected
at construction time.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionSucceeded,
)


class TestPromotionSucceededRecordValidation:
    """Runtime validation of PromotionSucceeded.records."""

    def test_empty_records_accepted(self) -> None:
        """Empty records tuple is a valid zero-work result."""
        outcome = PromotionSucceeded(
            run_id="run-123",
            requested_signal_ids=("sig-1", "sig-2"),
            records=(),
            diagnosis_incident_ids=(),
        )
        assert outcome.records == ()
        assert outcome.run_id == "run-123"

    def test_real_promotion_record_accepted(self) -> None:
        """Real PromotionRecord instances are accepted."""
        records = (
            PromotionRecord(
                source_candidate_id="cand-1",
                canonical_incident_id="inc-1",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
            PromotionRecord(
                source_candidate_id="cand-2",
                canonical_incident_id="inc-2",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
        )
        outcome = PromotionSucceeded(
            run_id="run-456",
            requested_signal_ids=("sig-1", "sig-2"),
            records=records,
            diagnosis_incident_ids=("inc-1", "inc-2"),
        )
        assert outcome.records == records
        assert len(outcome.records) == 2

    def test_string_record_rejected(self) -> None:
        """String records are rejected at construction time."""
        with pytest.raises(TypeError) as exc_info:
            PromotionSucceeded(
                run_id="run-789",
                requested_signal_ids=("sig-1",),
                # intentional invalid input
                records=("r1", "r2"),
                diagnosis_incident_ids=("inc-1",),
            )
        assert "PromotionSucceeded.records[0]" in str(exc_info.value)
        assert "str" in str(exc_info.value)
        assert "PromotionRecord" in str(exc_info.value)

    def test_tuple_record_rejected(self) -> None:
        """Tuple records are rejected at construction time."""
        with pytest.raises(TypeError) as exc_info:
            PromotionSucceeded(
                run_id="run-789",
                requested_signal_ids=("sig-1",),
                # intentional invalid input
                records=(("nested", "tuple"),),
                diagnosis_incident_ids=("inc-1",),
            )
        assert "PromotionSucceeded.records[0]" in str(exc_info.value)
        assert "tuple" in str(exc_info.value)

    def test_mixed_valid_invalid_rejected(self) -> None:
        """Mixed records with one invalid entry are rejected."""
        valid_record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="inc-1",
            promotion_outcome=PROMOTION_OUTCOME_OPENED,
        )
        with pytest.raises(TypeError) as exc_info:
            PromotionSucceeded(
                run_id="run-789",
                requested_signal_ids=("sig-1", "sig-2"),
                # intentional invalid input
                records=(valid_record, "invalid-string"),
                diagnosis_incident_ids=("inc-1",),
            )
        # Should fail on index 1 (the string)
        assert "records[1]" in str(exc_info.value)
        assert "str" in str(exc_info.value)

    def test_none_record_rejected(self) -> None:
        """None records are rejected at construction time."""
        with pytest.raises(TypeError) as exc_info:
            PromotionSucceeded(
                run_id="run-789",
                requested_signal_ids=("sig-1",),
                # intentional invalid input
                records=(None,),
                diagnosis_incident_ids=(),
            )
        assert "PromotionSucceeded.records[0]" in str(exc_info.value)
        assert "NoneType" in str(exc_info.value)

    def test_diagnosis_incident_ids_deduplicated(self) -> None:
        """Duplicate diagnosis_incident_ids are deduplicated at construction."""
        outcome = PromotionSucceeded(
            run_id="run-123",
            requested_signal_ids=("sig-1", "sig-2"),
            records=(),
            diagnosis_incident_ids=("inc-1", "inc-1", "inc-2"),
        )
        assert outcome.diagnosis_incident_ids == ("inc-1", "inc-2")

    def test_run_id_required(self) -> None:
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            PromotionSucceeded(
                run_id="",
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=(),
            )
        assert "run_id" in str(exc_info.value)

"""ADT construction and exhaustiveness tests for automatic-diagnosis dispositions.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

Covers Sections 9.1 (ADT construction tests) and 9.2 (exhaustiveness evidence).
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    DiagnosisBudgetDiagnostic,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    SCHEMA_VERSION,
    AutomaticDiagnosisEvaluationFailed,
    DiagnosisDispositionKind,
    DiagnosisEvaluationFailureReason,
    DiagnosisIneligibleReason,
    DiagnosisSkipReason,
    EligibleForAutomaticDiagnosis,
    IneligibleForAutomaticDiagnosis,
    SkippedFromAutomaticDiagnosis,
    disposition_kind,
)


class TestDispositionVariantsConstruct:
    """Each variant must construct with its valid fields."""

    def test_eligible_constructs_with_reason_and_diagnostics(self):
        diag = DiagnosisBudgetDiagnostic(
            name="review_packet_budget",
            used=1,
            limit=2,
            remaining=1,
            exhausted=False,
            source="test",
        )
        d = EligibleForAutomaticDiagnosis(
            eligibility_reason="active_incident_with_suggested_checks",
            budget_diagnostics=(diag,),
        )
        assert d.eligibility_reason == "active_incident_with_suggested_checks"
        assert d.budget_diagnostics == (diag,)

    def test_skipped_constructs_with_reason_and_detail(self):
        d = SkippedFromAutomaticDiagnosis(
            reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
            detail="10 review packets already exist",
        )
        assert d.reason == DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED
        assert d.detail == "10 review packets already exist"

    def test_ineligible_constructs(self):
        d = IneligibleForAutomaticDiagnosis(
            reason=DiagnosisIneligibleReason.TERMINAL_STATUS,
            detail="status=resolved",
        )
        assert d.reason == DiagnosisIneligibleReason.TERMINAL_STATUS
        assert d.detail == "status=resolved"

    def test_evaluation_failed_constructs(self):
        d = AutomaticDiagnosisEvaluationFailed(
            reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED,
            detail="connection refused",
        )
        assert d.reason == DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED
        assert d.detail == "connection refused"


class TestDispositionVariantsAreImmutable:
    """Frozen dataclasses cannot be mutated."""

    @pytest.mark.parametrize(
        "disposition",
        [
            EligibleForAutomaticDiagnosis(eligibility_reason="x"),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
            IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS),
            AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED),
        ],
    )
    def test_variant_is_frozen(self, disposition):
        with pytest.raises((AttributeError, Exception)):
            disposition.detail = "mutate"


class TestDispositionVariantsHaveNoBooleanState:
    """Prove the new variants no longer expose overlapping booleans.

    The legacy ``AutoLoopIncidentResult`` still carries
    ``eligible``/``skipped``/``error`` booleans, but the new
    disposition dataclasses MUST NOT expose them. This is checked by
    inspecting the declared fields of each frozen dataclass.
    """

    @pytest.mark.parametrize(
        "variant",
        [
            EligibleForAutomaticDiagnosis,
            SkippedFromAutomaticDiagnosis,
            IneligibleForAutomaticDiagnosis,
            AutomaticDiagnosisEvaluationFailed,
        ],
    )
    def test_variant_has_no_eligible_flag(self, variant):
        from dataclasses import fields
        names = {f.name for f in fields(variant)}
        assert "eligible" not in names
        assert "skipped" not in names
        assert "error" not in names


class TestDispositionKindMapping:
    """Coarse-kind mapping must be exhaustive and correct."""

    def test_eligible_maps_to_eligible(self):
        assert (
            disposition_kind(EligibleForAutomaticDiagnosis(eligibility_reason="x"))
            == DiagnosisDispositionKind.ELIGIBLE
        )

    def test_skipped_maps_to_skipped(self):
        assert (
            disposition_kind(SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY))
            == DiagnosisDispositionKind.SKIPPED
        )

    def test_ineligible_maps_to_ineligible(self):
        assert (
            disposition_kind(IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS))
            == DiagnosisDispositionKind.INELIGIBLE
        )

    def test_evaluation_failed_maps_to_error(self):
        assert (
            disposition_kind(
                AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED)
            )
            == DiagnosisDispositionKind.ERROR
        )


class TestSchemaVersionIsExplicit:
    """Schema version must be exported as 2 for downstream consumers."""

    def test_schema_version_is_two(self):
        assert SCHEMA_VERSION == 2

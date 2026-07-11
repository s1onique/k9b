"""Legacy projection tests for ``disposition_from_legacy_result``.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

Covers Section 4.4 (legacy compatibility projection validation) and
the legacy projection half of Section 9 (required tests).
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    AutomaticDiagnosisEvaluationFailed,
    DiagnosisEvaluationFailureReason,
    DiagnosisSkipReason,
    EligibleForAutomaticDiagnosis,
    IneligibleForAutomaticDiagnosis,
    SkippedFromAutomaticDiagnosis,
    disposition_from_legacy_result,
    legacy_result_from_disposition,
)


class TestLegacyProjectionFromDispositions:
    """One-way projection back to the legacy result shape."""

    def test_eligible_projects_to_eligible_true(self):
        legacy = legacy_result_from_disposition(
            incident_id="inc-1",
            disposition=EligibleForAutomaticDiagnosis(eligibility_reason="active"),
        )
        assert legacy.incident_id == "inc-1"
        assert legacy.eligible is True
        assert legacy.skipped is False
        assert legacy.error is None

    def test_skipped_projects_to_skipped_true(self):
        legacy = legacy_result_from_disposition(
            incident_id="inc-2",
            disposition=SkippedFromAutomaticDiagnosis(
                reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
                detail="10 review packets",
            ),
        )
        assert legacy.eligible is False
        assert legacy.skipped is True
        assert legacy.error is None
        assert legacy.skip_reason == "10 review packets"

    def test_ineligible_projects_to_neither_eligible_nor_skipped(self):
        legacy = legacy_result_from_disposition(
            incident_id="inc-3",
            disposition=IneligibleForAutomaticDiagnosis(
                reason=__import__(
                    "k8s_diag_agent.collect.incident_diagnosis_disposition",
                    fromlist=["DiagnosisIneligibleReason"],
                ).DiagnosisIneligibleReason.TERMINAL_STATUS,
                detail="status=resolved",
            ),
        )
        assert legacy.eligible is False
        assert legacy.skipped is False
        assert legacy.error is None

    def test_evaluation_failed_projects_to_error_set(self):
        legacy = legacy_result_from_disposition(
            incident_id="inc-4",
            disposition=AutomaticDiagnosisEvaluationFailed(
                reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED,
                detail="connection refused",
            ),
        )
        assert legacy.eligible is False
        assert legacy.skipped is False
        assert legacy.error == "connection refused"


class TestLegacyProjectionRoundTrip:
    """The forward projection should be near-lossless for valid states."""

    @pytest.mark.parametrize(
        "disposition",
        [
            EligibleForAutomaticDiagnosis(eligibility_reason="active"),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
            AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED),
        ],
    )
    def test_round_trip_via_legacy(self, disposition):
        # Use the closed-vocabulary enum values to set legacy fields
        # so the reverse projection reconstructs the same variant.
        legacy = legacy_result_from_disposition(incident_id="inc-x", disposition=disposition)
        if isinstance(disposition, EligibleForAutomaticDiagnosis):
            legacy.eligibility_reason = disposition.eligibility_reason
        elif isinstance(disposition, SkippedFromAutomaticDiagnosis):
            legacy.eligibility_reason = disposition.reason.value
            legacy.skip_reason = disposition.detail or disposition.reason.value
        elif isinstance(disposition, AutomaticDiagnosisEvaluationFailed):
            legacy.eligibility_reason = disposition.reason.value
        rebuilt = disposition_from_legacy_result(legacy)
        assert type(rebuilt) is type(disposition)


class TestLegacyProjectionRejectsContradictions:
    """The reverse projection must reject impossible combinations."""

    def test_eligible_and_skipped_raises(self):
        legacy = AutoLoopIncidentResult(
            incident_id="inc",
            eligible=True,
            skipped=True,
            eligibility_reason="active",
        )
        with pytest.raises(ValueError, match="eligible=True and skipped=True"):
            disposition_from_legacy_result(legacy)

    def test_skipped_and_error_raises(self):
        legacy = AutoLoopIncidentResult(
            incident_id="inc",
            eligible=False,
            skipped=True,
            error="boom",
            eligibility_reason="budget_exhausted",
            skip_reason="budget_exhausted",
        )
        with pytest.raises(ValueError, match="skipped=True and an error"):
            disposition_from_legacy_result(legacy)

    def test_neither_eligible_nor_skipped_nor_error_raises(self):
        legacy = AutoLoopIncidentResult(
            incident_id="inc",
            eligible=False,
            skipped=False,
            error=None,
            eligibility_reason="active",
        )
        with pytest.raises(ValueError, match="cannot project"):
            disposition_from_legacy_result(legacy)


class TestLegacyProjectionMapsUnknownStrings:
    """Unknown legacy strings map to bounded legacy reasons."""

    def test_unknown_skip_reason_maps_to_unknown_legacy_reason(self):
        legacy = AutoLoopIncidentResult(
            incident_id="inc",
            eligible=False,
            skipped=True,
            eligibility_reason="some_random_reason_we_dont_know",
            skip_reason="some_random_reason_we_dont_know",
        )
        d = disposition_from_legacy_result(legacy)
        assert isinstance(d, SkippedFromAutomaticDiagnosis)
        assert d.reason == DiagnosisSkipReason.UNKNOWN_LEGACY_REASON


class TestLegacyProjectionRecognizesBudgetReason:
    """Legacy ``budget`` strings map to the closed vocabulary member."""

    def test_budget_string_maps_to_review_packet_budget_exhausted(self):
        legacy = AutoLoopIncidentResult(
            incident_id="inc",
            eligible=False,
            skipped=True,
            eligibility_reason="budget_exhausted",
            skip_reason="budget_exhausted: 10 packets",
        )
        d = disposition_from_legacy_result(legacy)
        assert isinstance(d, SkippedFromAutomaticDiagnosis)
        assert d.reason == DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED


class TestLegacyProjectionTypeChecks:
    def test_non_legacy_result_raises_typeerror(self):
        with pytest.raises(TypeError):
            disposition_from_legacy_result({"eligible": False})

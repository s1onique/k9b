"""Reducer matrix, conservation laws, and reason-vocabulary tests.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

Covers Sections 9.3 (reducer matrix), 9.4 (conservation laws),
and 9.5 (reason vocabulary).
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    AutomaticDiagnosisEvaluationFailed,
    DiagnosisDispositionSummary,
    DiagnosisEvaluationFailureReason,
    DiagnosisIneligibleReason,
    DiagnosisSkipReason,
    EligibleForAutomaticDiagnosis,
    IncidentDiagnosisDisposition,
    IneligibleForAutomaticDiagnosis,
    SkippedFromAutomaticDiagnosis,
    aggregate_summary_event,
    empty_disposition_summary,
    per_incident_disposition_event,
    reduce_disposition,
)

# ---------------------------------------------------------------------------
# 9.3 Reducer matrix
# ---------------------------------------------------------------------------


class TestReducerMatrix:
    """Each variant increments exactly one primary counter and reason key."""

    def test_eligible_increments_eligible_only(self):
        s = reduce_disposition(
            empty_disposition_summary(),
            EligibleForAutomaticDiagnosis(eligibility_reason="active_incident_with_suggested_checks"),
        )
        assert s.eligible == 1
        assert s.skipped == 0
        assert s.ineligible == 0
        assert s.errors == 0
        assert s.processed == 1
        assert dict(s.skip_reasons) == {}
        assert dict(s.ineligible_reasons) == {}
        assert dict(s.error_reasons) == {}

    def test_skipped_increments_skip_counter_and_skip_reasons(self):
        s = reduce_disposition(
            empty_disposition_summary(),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED),
        )
        assert s.skipped == 1
        assert s.skip_reasons[DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED] == 1
        assert s.eligible == 0
        assert s.ineligible == 0
        assert s.errors == 0

    def test_ineligible_increments_ineligible_counter_and_ineligible_reasons(self):
        s = reduce_disposition(
            empty_disposition_summary(),
            IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS),
        )
        assert s.ineligible == 1
        assert s.ineligible_reasons[DiagnosisIneligibleReason.TERMINAL_STATUS] == 1
        assert s.eligible == 0
        assert s.skipped == 0
        assert s.errors == 0

    def test_evaluation_failed_increments_errors_counter_and_error_reasons(self):
        s = reduce_disposition(
            empty_disposition_summary(),
            AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED),
        )
        assert s.errors == 1
        assert s.error_reasons[DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED] == 1
        assert s.eligible == 0
        assert s.skipped == 0
        assert s.ineligible == 0


# ---------------------------------------------------------------------------
# 9.4 Conservation-law tests
# ---------------------------------------------------------------------------


def _reduce_all(dispositions: Iterable[IncidentDiagnosisDisposition]) -> DiagnosisDispositionSummary:
    s = empty_disposition_summary()
    for d in dispositions:
        s = reduce_disposition(s, d)
    return s


def _assert_conservation(summary: DiagnosisDispositionSummary) -> None:
    """Assert all conservation invariants for the given summary."""
    assert summary.processed == summary.eligible + summary.skipped + summary.ineligible + summary.errors
    assert sum(summary.skip_reasons.values()) == summary.skipped
    assert sum(summary.ineligible_reasons.values()) == summary.ineligible
    assert sum(summary.error_reasons.values()) == summary.errors
    assert all(v >= 1 for v in summary.skip_reasons.values())
    assert all(v >= 1 for v in summary.ineligible_reasons.values())
    assert all(v >= 1 for v in summary.error_reasons.values())
    assert summary.is_consistent()


class TestConservationEmptyBatch:
    def test_empty_batch_is_consistent(self):
        s = _reduce_all([])
        assert s.processed == 0
        _assert_conservation(s)


class TestConservationSingleVariant:
    @pytest.mark.parametrize(
        "disposition,counter_attr",
        [
            (EligibleForAutomaticDiagnosis(eligibility_reason="x"), "eligible"),
            (
                SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
                "skipped",
            ),
            (
                IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS),
                "ineligible",
            ),
            (
                AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED),
                "errors",
            ),
        ],
    )
    def test_one_of_each_variant_is_consistent(self, disposition, counter_attr):
        s = _reduce_all([disposition])
        assert getattr(s, counter_attr) == 1
        _assert_conservation(s)


class TestConservationThirtySkipped:
    """Reproduce the production all-skipped scenario."""

    def test_thirty_skipped_is_consistent(self):
        dispositions = [
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED)
            for _ in range(30)
        ]
        s = _reduce_all(dispositions)
        assert s.processed == 30
        assert s.skipped == 30
        assert s.eligible == 0
        assert s.ineligible == 0
        assert s.errors == 0
        assert s.skip_reasons[DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED] == 30
        _assert_conservation(s)


class TestConservationMixedBatch:
    def test_mixed_batch_with_repeated_reasons(self):
        dispositions: list[IncidentDiagnosisDisposition] = [
            EligibleForAutomaticDiagnosis(eligibility_reason="active"),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED),
            IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS),
            AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
        ]
        s = _reduce_all(dispositions)
        assert s.processed == 6
        assert s.eligible == 1
        assert s.skipped == 3
        assert s.ineligible == 1
        assert s.errors == 1
        assert s.skip_reasons[DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED] == 2
        assert s.skip_reasons[DiagnosisSkipReason.LISTING_EMPTY] == 1
        assert s.ineligible_reasons[DiagnosisIneligibleReason.TERMINAL_STATUS] == 1
        assert s.error_reasons[DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED] == 1
        _assert_conservation(s)


class TestConservationAllEligible:
    def test_all_eligible(self):
        s = _reduce_all(
            [EligibleForAutomaticDiagnosis(eligibility_reason="active") for _ in range(10)]
        )
        assert s.eligible == 10
        assert s.processed == 10
        _assert_conservation(s)


class TestConservationAllErrors:
    def test_all_errors(self):
        s = _reduce_all(
            [
                AutomaticDiagnosisEvaluationFailed(reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED)
                for _ in range(10)
            ]
        )
        assert s.errors == 10
        assert s.processed == 10
        _assert_conservation(s)


# ---------------------------------------------------------------------------
# 9.5 Reason vocabulary tests
# ---------------------------------------------------------------------------


class TestReasonVocabulary:
    """Reason codes are closed-vocabulary enum values; details are separate."""

    def test_every_serialized_reason_is_a_declared_enum_member(self):
        dispositions: list[IncidentDiagnosisDisposition] = [
            EligibleForAutomaticDiagnosis(eligibility_reason="active"),
            SkippedFromAutomaticDiagnosis(
                reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
                detail="dynamic detail string with id=incident-abc",
            ),
            IneligibleForAutomaticDiagnosis(
                reason=DiagnosisIneligibleReason.TERMINAL_STATUS,
                detail="status=resolved",
            ),
            AutomaticDiagnosisEvaluationFailed(
                reason=DiagnosisEvaluationFailureReason.BACKEND_FETCH_FAILED,
                detail="connection refused: 0.0.0.0:443",
            ),
        ]
        s = _reduce_all(dispositions)
        event = aggregate_summary_event(
            summary=s,
            collector_run_id="c1",
            stop_reason="loop_completed",
        )
        for code in event["skip_reasons"]:
            assert code in {r.value for r in DiagnosisSkipReason}
        for code in event["ineligible_reasons"]:
            assert code in {r.value for r in DiagnosisIneligibleReason}
        for code in event["error_reasons"]:
            assert code in {r.value for r in DiagnosisEvaluationFailureReason}

    def test_dynamic_details_do_not_become_reason_keys(self):
        """Detail strings (which may contain IDs/URLs) must NOT be keys."""
        s = _reduce_all(
            [
                SkippedFromAutomaticDiagnosis(
                    reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
                    detail="incident-abc123 https://example/secret-token traceback...",
                )
                for _ in range(3)
            ]
        )
        event = aggregate_summary_event(
            summary=s, collector_run_id="c1", stop_reason="loop_completed"
        )
        # The only key is the closed vocabulary member.
        assert list(event["skip_reasons"].keys()) == ["review_packet_budget_exhausted"]
        assert event["skip_reasons"]["review_packet_budget_exhausted"] == 3

    def test_reason_map_ordering_is_deterministic(self):
        """Python dicts are insertion-ordered; the reducer must respect enum order."""
        # Insert skipped reasons in non-natural order; the reducer's
        # bump_reason preserves first-insertion order for new keys.
        dispositions: list[IncidentDiagnosisDisposition] = [
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED),
            SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
        ]
        s = _reduce_all(dispositions)
        assert list(s.skip_reasons.keys()) == [
            DiagnosisSkipReason.LISTING_EMPTY,
            DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
        ]
        assert s.skip_reasons[DiagnosisSkipReason.LISTING_EMPTY] == 2
        assert s.skip_reasons[DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED] == 1

    def test_reason_keys_are_nonempty(self):
        for member in DiagnosisSkipReason:
            assert member.value, f"empty skip reason: {member!r}"
        for member in DiagnosisIneligibleReason:
            assert member.value, f"empty ineligible reason: {member!r}"
        for member in DiagnosisEvaluationFailureReason:
            assert member.value, f"empty error reason: {member!r}"

    def test_reason_keys_use_snake_case(self):
        """Reason values are stable API/logging contracts."""
        import re

        snake_case = re.compile(r"^[a-z][a-z0-9_]*$")
        for member in DiagnosisSkipReason:
            assert snake_case.match(member.value), f"non-snake_case skip: {member!r}"
        for member in DiagnosisIneligibleReason:
            assert snake_case.match(member.value), f"non-snake_case ineligible: {member!r}"
        for member in DiagnosisEvaluationFailureReason:
            assert snake_case.match(member.value), f"non-snake_case error: {member!r}"


class TestPerIncidentEventShape:
    """Per-incident disposition event must include all required fields."""

    def test_event_includes_required_fields(self):
        d = SkippedFromAutomaticDiagnosis(
            reason=DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED,
            detail="budget exhausted",
        )
        event = per_incident_disposition_event(
            disposition=d,
            run_id="health-run-1",
            collector_run_id="auto-diagnosis-1",
            incident_id="incident-1",
        )
        for required in (
            "event",
            "schema_version",
            "run_id",
            "collector_run_id",
            "incident_id",
            "disposition",
            "reason_code",
        ):
            assert required in event
        assert event["event"] == "automatic-diagnosis-incident-disposition"
        assert event["disposition"] == "skipped"
        assert event["reason_code"] == "review_packet_budget_exhausted"
        assert event["incident_id"] == "incident-1"
        assert event["schema_version"] == 2


class TestAggregateSummaryEventShape:
    """Aggregate eligibility summary must include all required fields."""

    def test_event_includes_required_fields(self):
        s = _reduce_all(
            [
                SkippedFromAutomaticDiagnosis(reason=DiagnosisSkipReason.LISTING_EMPTY),
                IneligibleForAutomaticDiagnosis(reason=DiagnosisIneligibleReason.TERMINAL_STATUS),
            ]
        )
        event = aggregate_summary_event(
            summary=s,
            collector_run_id="auto-diagnosis-x",
            stop_reason="loop_completed",
        )
        for required in (
            "event",
            "schema_version",
            "collector_run_id",
            "incidents_processed",
            "incidents_eligible",
            "incidents_skipped",
            "incidents_ineligible",
            "incidents_with_errors",
            "skip_reasons",
            "ineligible_reasons",
            "error_reasons",
            "stop_reason",
        ):
            assert required in event
        assert event["event"] == "automatic-diagnosis-eligibility-summary"
        assert event["stop_reason"] == "loop_completed"
        assert event["schema_version"] == 2
        assert event["incidents_processed"] == 2
        assert event["incidents_skipped"] == 1
        assert event["incidents_ineligible"] == 1

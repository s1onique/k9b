"""Failure-code exact-match self-tests for the backend-outcome verifier."""

from __future__ import annotations

import textwrap

import pytest

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentLookupFailureCode,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    DiagnosisEvaluationFailureReason,
    diagnosis_failure_reason_for_backend_lookup,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition_compat import (
    _map_legacy_error_reason,
)
from tests.unit.automatic_diagnosis_backend_detail_outcomes_verifier_support import (
    _format_violations,
    assert_violation,
    check_compat_source,
    check_disposition_source,
    verifier,
)

CANONICAL_FAILURE_REASON_PAIRS = (
    (
        BackendIncidentLookupFailureCode.INVALID_JSON,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_JSON,
    ),
    (
        BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_PAYLOAD,
    ),
    (
        BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_UNSUPPORTED_SCHEMA,
    ),
    (
        BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_DESERIALIZATION_FAILED,
    ),
    (
        BackendIncidentLookupFailureCode.IDENTITY_MISMATCH,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_IDENTITY_MISMATCH,
    ),
    (
        BackendIncidentLookupFailureCode.UNAUTHORIZED,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_UNAUTHORIZED,
    ),
    (
        BackendIncidentLookupFailureCode.FORBIDDEN,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_FORBIDDEN,
    ),
    (
        BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_HTTP_CLIENT_ERROR,
    ),
    (
        BackendIncidentLookupFailureCode.BACKEND_ERROR,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_BACKEND_ERROR,
    ),
    (
        BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
        DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_TRANSPORT_ERROR,
    ),
)


class TestReasonCodeInvariants:
    def test_missing_backend_incident_reason_code_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = verifier._read(
            verifier.SRC_ROOT / "collect" / "incident_diagnosis_disposition.py"
        )
        assert source is not None
        mutated = source.replace(
            'BACKEND_INCIDENT_UNSUPPORTED_SCHEMA = "backend_incident_unsupported_schema"',
            "",
        )
        violations = check_disposition_source(monkeypatch, mutated)
        assert_violation(violations, "backend_incident_unsupported_schema")


class TestCompatSubstringMatchingRejection:
    def test_substring_match_for_backend_incident_codes_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = textwrap.dedent(
            """
            def _map_legacy_error_reason(raw: str):
                raw_lower = (raw or "").lower()
                if "backend_incident_invalid_json" in raw_lower:
                    return "backend_incident_invalid_json"
                return "eligibility_evaluation_failed"
            """
        ).strip()
        violations = check_compat_source(monkeypatch, source)
        assert_violation(violations, "substring match")

    def test_prefix_backend_incident_invalid_json_suffix_does_not_match(
        self,
    ) -> None:
        canonical = diagnosis_failure_reason_for_backend_lookup(
            BackendIncidentLookupFailureCode.INVALID_JSON
        )
        assert canonical.value == "backend_incident_invalid_json"
        mapped = _map_legacy_error_reason(
            "prefix_backend_incident_invalid_json_suffix"
        )
        assert mapped != DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_JSON

    def test_reversed_containment_match_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = textwrap.dedent(
            """
            def _map_legacy_error_reason(raw: str):
                raw_lower = (raw or "").lower()
                if raw_lower in "backend_incident_invalid_json":
                    return "backend_incident_invalid_json"
                return "eligibility_evaluation_failed"
            """
        ).strip()
        violations = check_compat_source(monkeypatch, source)
        assert_violation(violations, "substring match")

    def test_exact_comparison_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = textwrap.dedent(
            """
            def _map_legacy_error_reason(raw: str):
                raw_lower = (raw or "").lower()
                if raw_lower == "backend_incident_invalid_json":
                    return "backend_incident_invalid_json"
                return "eligibility_evaluation_failed"
            """
        ).strip()
        violations = check_compat_source(monkeypatch, source)
        assert not violations, _format_violations(violations)


@pytest.mark.parametrize(
    ("failure_code", "expected_reason"),
    CANONICAL_FAILURE_REASON_PAIRS,
    ids=[failure_code.value for failure_code, _ in CANONICAL_FAILURE_REASON_PAIRS],
)
def test_each_canonical_failure_code_maps_exactly(
    failure_code: BackendIncidentLookupFailureCode,
    expected_reason: DiagnosisEvaluationFailureReason,
) -> None:
    assert diagnosis_failure_reason_for_backend_lookup(failure_code) is expected_reason
    assert _map_legacy_error_reason(expected_reason.value) is expected_reason


@pytest.mark.parametrize(
    "partial_value",
    [
        "backend_incident_invalid_json_suffix",
        "prefix_backend_incident_invalid_json",
        "prefix_backend_incident_invalid_json_suffix",
        "backend_incident_invalid_json.extra",
    ],
    ids=["prefix-match", "suffix-match", "contained", "punctuated"],
)
def test_partial_failure_code_values_do_not_match_canonical_reason(
    partial_value: str,
) -> None:
    mapped = _map_legacy_error_reason(partial_value)
    assert mapped is not DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_JSON

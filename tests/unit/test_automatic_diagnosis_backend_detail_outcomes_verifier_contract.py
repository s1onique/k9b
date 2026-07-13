"""Contract and canonical-tree self-tests for the backend-outcome verifier."""

from __future__ import annotations

import pytest

from tests.unit.automatic_diagnosis_backend_detail_outcomes_verifier_support import (
    _format_violations,
    assert_no_violation,
    assert_violation,
    check_lookup_source,
    check_outcome_source,
    check_processor_source,
    lookup_source,
    outcome_model_source,
    verifier,
)


class TestCanonicalProductionCodeClean:
    def test_verifier_passes_against_production_code(self) -> None:
        violations = verifier.run_static_checks()
        assert not violations, (
            "Verifier reported violations against the canonical implementation. "
            "Fix the implementation; do not weaken the verifier. "
            f"Violations:\n{_format_violations(violations)}"
        )

    def test_verifier_cli_exits_zero(self) -> None:
        assert verifier.main([]) == 0


class TestOutcomeModelInvariants:
    def test_missing_variant_in_outcomes_module_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = outcome_model_source(
            variants=("BackendIncidentFound", "BackendIncidentLookupFailed")
        )
        violations = check_outcome_source(monkeypatch, source)
        assert_violation(violations, "BackendIncidentNotFound", "missing")

    def test_non_frozen_outcome_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(frozen=False, slots=False),
        )
        assert_violation(violations, "frozen")

    def test_boolean_found_discriminator_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(found_discriminator=True),
        )
        assert_violation(violations, "boolean", "found")

    def test_incident_field_widened_to_object_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(found_incident_annotation="object"),
        )
        assert_violation(violations, "BackendIncidentFound.incident", "object")

    def test_missing_failure_code_enum_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(include_failure_enum=False),
        )
        assert_violation(
            violations,
            "BackendIncidentLookupFailureCode",
            "StrEnum",
        )

    def test_outcome_without_slots_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(slots=False),
        )
        assert_violation(violations, "slots=True")

    @pytest.mark.parametrize("annotation", ["Any", "dict"], ids=["Any", "dict"])
    def test_incident_field_widening_is_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        annotation: str,
    ) -> None:
        violations = check_outcome_source(
            monkeypatch,
            outcome_model_source(found_incident_annotation=annotation),
        )
        assert_violation(violations, "BackendIncidentFound.incident", annotation)


class TestLookupSignatureInvariants:
    def test_lookup_must_invoke_parser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(include_parser_call=False),
        )
        assert_violation(violations, "parser")

    def test_lookup_must_not_return_optional_incident(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(return_annotation="Optional[Incident]"),
        )
        assert_violation(violations, "Optional[Incident]")

    def test_lookup_with_bare_return_none_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(include_bare_none=True),
        )
        assert_violation(violations, "bare", "return None")


class TestProcessorDispatchInvariants:
    def test_processor_missing_dispatch_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_processor_source(
            monkeypatch,
            "def _process_incident(incident_id):\n    return None",
        )
        assert_violation(violations, "BackendIncident")


def test_module_name_from_path_is_fully_qualified() -> None:
    """The helper includes the package prefix without touching production files."""
    target = verifier.SRC_ROOT / "collect" / "_verifier_self_test_tmp.py"
    name = verifier._module_name_from_path(target)
    assert name == "k8s_diag_agent.collect._verifier_self_test_tmp"


class TestClosedUnionVerifier:
    def test_extra_fourth_variant_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = outcome_model_source(
            union_members=(
                "BackendIncidentFound",
                "BackendIncidentNotFound",
                "BackendIncidentLookupFailed",
                "BackendIncidentRetryable",
            )
        )
        violations = check_outcome_source(monkeypatch, source)
        assert_violation(violations, "BackendIncidentRetryable")

    def test_union_with_all_three_required_passes_identifier_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_outcome_source(monkeypatch, outcome_model_source())
        assert_no_violation(violations, "EXACTLY the closed union")

    def test_missing_one_variant_is_detected_via_strict_identifier_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = outcome_model_source(
            variants=("BackendIncidentFound", "BackendIncidentLookupFailed")
        )
        violations = check_outcome_source(monkeypatch, source)
        assert_violation(violations, "BackendIncidentNotFound", "missing")

    @pytest.mark.parametrize(
        "forbidden_member",
        ["Incident", "object", "Any"],
        ids=["Incident", "object", "Any"],
    )
    def test_union_rejects_forbidden_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        forbidden_member: str,
    ) -> None:
        source = outcome_model_source(
            union_members=(*verifier.REQUIRED_VARIANTS, forbidden_member)
        )
        violations = check_outcome_source(monkeypatch, source)
        assert_violation(violations, forbidden_member, "extra forbidden")

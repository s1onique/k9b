"""Self-tests for the AST/static verifier introduced by
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 (R1).

The verifier must:

* pass against the current canonical implementation;
* detect every forbidden mutation listed in the ACT contract:

    - ``except Exception: return None``
    - ``except Exception: return BackendIncidentNotFound(...)``
    - ``if not incident: reason = "incident_not_found"``
    - ``if not payload: return BackendIncidentNotFound(...)``
    - missing ``BackendIncidentLookupFailureCode`` enum
    - non-frozen outcome dataclass
    - boolean ``found`` discriminator
    - union missing a required variant / union mentioning ``Incident`` /
      ``object`` / ``Any``
    - ``_process_incident`` that does not dispatch on a variant
    - ``BackendIncidentFound.incident`` widened to ``object`` / ``Any`` /
      ``dict``
    - ``BackendIncidentNotFound`` constructed without
      ``source=BackendIncidentLookupSource.BACKEND_API``
    - local-mode dispatcher synthesising ``http_status=404``
    - 404 branch mutated to ``!= 404`` / ``in {400, 404}`` /
      ``404 <= response.http_status`` / plain truthiness
    - substring match for ``backend_incident_*`` codes

These self-tests construct synthetic snippets that represent each
forbidden mutation and verify the verifier reports them. They also
verify that the canonical production code is clean.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

# Make the verifier importable.
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verifiers import (  # noqa: E402  (sys.path setup precedes import)
    automatic_diagnosis_backend_detail_outcomes as verifier,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_violations(violations: list[str]) -> str:
    return "\n".join(f"- {v}" for v in violations)


def _build_source(tmp_path: Path, *snippets: str) -> Path:
    """Write a synthetic module file containing the given snippets."""
    body = "\n\n".join(snippets)
    path = tmp_path / "synthetic_forbidden_module.py"
    path.write_text(body)
    return path


def _snip_return_none() -> str:
    return textwrap.dedent(
        """
        def fetch_incident(incident_id):
            try:
                raise ValueError('boom')
            except Exception:
                return None
        """
    ).strip()


def _snip_broad_exc_to_not_found() -> str:
    return textwrap.dedent(
        """
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentNotFound,
        )
        def fetch_incident(incident_id):
            try:
                raise ValueError('boom')
            except Exception:
                return BackendIncidentNotFound(
                    requested_incident_id=incident_id,
                    http_status=404,
                )
        """
    ).strip()


def _snip_truthy_to_reason() -> str:
    return textwrap.dedent(
        """
        def lookup(incident_id):
            incident = None
            if not incident:
                reason = "incident_not_found"
            return reason
        """
    ).strip()


def _snip_empty_payload_to_not_found() -> str:
    return textwrap.dedent(
        """
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentNotFound,
        )
        def lookup(incident_id, payload):
            if not payload:
                return BackendIncidentNotFound(
                    requested_incident_id=incident_id,
                    http_status=404,
                )
        """
    ).strip()


# ---------------------------------------------------------------------------
# 1. Canonical production code passes
# ---------------------------------------------------------------------------


class TestCanonicalProductionCodeClean:
    def test_verifier_passes_against_production_code(self) -> None:
        violations = verifier.run_static_checks()
        assert not violations, (
            "ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 verifier "
            "reported violations against the canonical implementation. "
            "Fix the implementation; do not weaken the verifier. "
            f"Violations:\n{_format_violations(violations)}"
        )

    def test_verifier_cli_exits_zero(self) -> None:
        # The verifier's CLI must exit 0 against clean production code.
        rc = verifier.main([])
        assert rc == 0


# ---------------------------------------------------------------------------
# 2. Verifier detects forbidden mutations in synthetic snippets
# ---------------------------------------------------------------------------


class TestForbiddenPatternsDetected:
    @pytest.fixture
    def probe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Callable[[str], list[str]]:
        """Helper that writes a synthetic module and runs the per-file
        not-found / broad-exception checks against it.

        The synthetic file's canonical module name (as computed by
        :func:`_module_name_from_path`) is automatically added to
        :data:`TOUCHED_SEAM_MODULES` so the broad-exception check
        actually inspects the synthetic file.
        """

        def _run(snippet: str) -> list[str]:
            path = _build_source(tmp_path, snippet)
            from verifiers.automatic_diagnosis_backend_detail_outcomes import (
                _module_name_from_path as mfp,
            )

            module_name = mfp(path)
            original_touched = verifier.TOUCHED_SEAM_MODULES
            verifier.TOUCHED_SEAM_MODULES = (module_name,) + tuple(original_touched)
            try:
                violations: list[str] = []
                violations.extend(verifier._check_not_found_construction(path))
                violations.extend(verifier._check_no_broad_exception_to_not_found(path))
                violations.extend(verifier._check_no_truthiness_to_not_found(path))
            finally:
                verifier.TOUCHED_SEAM_MODULES = original_touched
            return violations

        return _run

    def test_broad_exception_return_none_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(_snip_return_none())
        assert any(
            "bare" in v and "return None" in v for v in violations
        ), f"Expected detection of bare except/return None, got:\n{_format_violations(violations)}"

    def test_broad_exception_returning_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(_snip_broad_exc_to_not_found())
        assert any(
            "BackendIncidentNotFound" in v and "forbidden" in v.lower()
            for v in violations
        ), f"Expected detection of broad-exception-to-not-found, got:\n{_format_violations(violations)}"

    def test_truthiness_check_then_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        """Real check: the truthiness mutation is genuinely detected."""
        violations = probe(_snip_truthy_to_reason())
        assert any(
            "forbidden truthiness" in v.lower() for v in violations
        ), f"Expected truthiness detection, got:\n{_format_violations(violations)}"

    def test_empty_payload_returning_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(_snip_empty_payload_to_not_found())
        # The broad ``except Exception`` handler is NOT used here, but
        # ``BackendIncidentNotFound(...)`` is constructed outside any
        # permission list and ``if not payload`` truthiness is a
        # forbidden collapse.
        assert any(
            "BackendIncidentNotFound" in v
            and ("forbidden" in v.lower() or "truthiness" in v.lower())
            for v in violations
        ), f"Expected detection of empty-payload-to-not-found, got:\n{_format_violations(violations)}"


# ---------------------------------------------------------------------------
# 3. Verifier invariants about the outcome model itself
# ---------------------------------------------------------------------------


class TestOutcomeModelInvariants:
    def test_missing_variant_in_outcomes_module_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a required variant is removed, the verifier must flag it."""
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                incident: object

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "BackendIncidentNotFound" in v and "missing" in v.lower()
            for v in violations
        ), f"Expected missing-variant detection, got:\n{_format_violations(violations)}"

    def test_non_frozen_outcome_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            # Note: NOT frozen, NOT slots.
            @dataclass
            class BackendIncidentFound:
                requested_incident_id: IncidentId

            @dataclass
            class BackendIncidentNotFound:
                requested_incident_id: IncidentId

            @dataclass
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "frozen" in v.lower() for v in violations
        ), f"Expected non-frozen detection, got:\n{_format_violations(violations)}"

    def test_boolean_found_discriminator_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                found: bool

            @dataclass(frozen=True, slots=True)
            class BackendIncidentNotFound:
                requested_incident_id: IncidentId

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "boolean" in v.lower() and "found" in v.lower()
            for v in violations
        ), f"Expected boolean-found detection, got:\n{_format_violations(violations)}"

    def test_incident_field_widened_to_object_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                incident: object

            @dataclass(frozen=True, slots=True)
            class BackendIncidentNotFound:
                requested_incident_id: IncidentId
                source: str

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "BackendIncidentFound.incident" in v and "object" in v.lower()
            for v in violations
        ), (
            "Expected BackendIncidentFound.incident widened-to-object "
            f"detection, got:\n{_format_violations(violations)}"
        )


# ---------------------------------------------------------------------------
# 4. Verifier invariants about the lookup signature
# ---------------------------------------------------------------------------


class TestLookupSignatureInvariants:
    def test_lookup_must_invoke_parser(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the canonical lookup drops the parser call, the verifier flags it."""
        original_open = verifier._read
        fake_source = textwrap.dedent(
            """
            def lookup_backend_incident(client, incident_id):
                return None
            """
        )

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_lookup.py":
                return fake_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_lookup_signature()
        assert any(
            "parser" in v.lower() for v in violations
        ), f"Expected parser-missing detection, got:\n{_format_violations(violations)}"

    def test_lookup_must_not_return_optional_incident(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_open = verifier._read
        fake_source = textwrap.dedent(
            """
            from typing import Optional
            from k8s_diag_agent.collect.incident_lifecycle import Incident

            def lookup_backend_incident(
                client, incident_id,
            ) -> Optional[Incident]:
                return None
            """
        )

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_lookup.py":
                return fake_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_lookup_signature()
        assert any(
            "Optional[Incident]" in v or "Incident | None" in v
            for v in violations
        ), f"Expected Optional/None detection, got:\n{_format_violations(violations)}"

    def test_lookup_with_bare_return_none_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_open = verifier._read
        fake_source = textwrap.dedent(
            """
            from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
                BackendIncidentLookupOutcome,
            )

            def lookup_backend_incident(client, incident_id) -> BackendIncidentLookupOutcome:
                if not incident_id:
                    return None
                return None
            """
        )

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_lookup.py":
                return fake_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_lookup_signature()
        assert any(
            "bare" in v.lower() and "return None" in v
            for v in violations
        ), f"Expected bare-return-None detection, got:\n{_format_violations(violations)}"


# ---------------------------------------------------------------------------
# 5. Verifier invariants about reason codes
# ---------------------------------------------------------------------------


class TestReasonCodeInvariants:
    def test_missing_backend_incident_reason_code_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_disposition.py":
                text = original_open(path) or ""
                return text.replace(
                    'BACKEND_INCIDENT_UNSUPPORTED_SCHEMA = "backend_incident_unsupported_schema"',
                    "",
                )
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_reason_codes()
        assert any(
            "backend_incident_unsupported_schema" in v for v in violations
        ), f"Expected missing reason code detection, got:\n{_format_violations(violations)}"


# ---------------------------------------------------------------------------
# 6. Verifier invariants about the processor dispatch
# ---------------------------------------------------------------------------


class TestProcessorDispatchInvariants:
    def test_processor_missing_dispatch_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_auto_loop_evidence_processor.py":
                return textwrap.dedent(
                    """
                    def _process_incident(incident_id, external_analysis_dir, config, collector_run_id, now):
                        return None
                    """
                )
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_processor_dispatch(
            verifier.SRC_ROOT
            / "collect"
            / "incident_diagnosis_auto_loop_evidence_processor.py"
        )
        assert any(
            "BackendIncident" in v for v in violations
        ), f"Expected missing dispatch detection, got:\n{_format_violations(violations)}"


# ---------------------------------------------------------------------------
# 7. R1 helpers (shared utility verification)
# ---------------------------------------------------------------------------


def test_module_name_from_path_is_fully_qualified(tmp_path: Path) -> None:
    """The module-name helper must include the ``k8s_diag_agent`` prefix."""
    src_dir = verifier.SRC_ROOT / "collect"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "_verifier_self_test_tmp.py"
    target.write_text("")
    try:
        name = verifier._module_name_from_path(target)
        assert name == "k8s_diag_agent.collect._verifier_self_test_tmp", (
            f"Module name should be fully qualified, got {name!r}"
        )
    finally:
        target.unlink(missing_ok=True)


def test_ast_round_trip_on_synthetic_snippet() -> None:
    """The forbidden-pattern snippets must be parseable Python."""
    snippets = (
        _snip_return_none(),
        _snip_broad_exc_to_not_found(),
        _snip_truthy_to_reason(),
        _snip_empty_payload_to_not_found(),
    )
    for snippet in snippets:
        ast.parse(snippet)


# ---------------------------------------------------------------------------
# 8. R1 substring-matching rejection (compat layer)
# ---------------------------------------------------------------------------


class TestCompatSubstringMatchingRejection:
    def test_substring_match_for_backend_incident_codes_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_open = verifier._read
        fake_compat = textwrap.dedent(
            """
            from .incident_diagnosis_disposition import DiagnosisEvaluationFailureReason

            def _map_legacy_error_reason(raw: str):
                raw_lower = (raw or '').lower()
                if "backend_incident_invalid_json" in raw_lower:
                    return DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_JSON
                return DiagnosisEvaluationFailureReason.ELIGIBILITY_EVALUATION_FAILED
            """
        )

        def _patched(path: Path):
            if path.name == "incident_diagnosis_disposition_compat.py":
                return fake_compat
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_no_substring_backend_incident_matching()
        assert any(
            "substring match" in v.lower() for v in violations
        ), (
            "Expected substring-match rejection, got:\n"
            f"{_format_violations(violations)}"
        )

    def test_prefix_backend_incident_invalid_json_suffix_does_not_match(
        self,
    ) -> None:
        """Demonstrate that an embedded substring is NOT classified as
        the canonical reason by the typed mapping (the mapping is exact).
        """
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentLookupFailureCode,
        )
        from k8s_diag_agent.collect.incident_diagnosis_disposition import (
            diagnosis_failure_reason_for_backend_lookup,
        )

        # The typed mapping is total and exact; prefix/suffix substrings
        # are not accepted as canonical reason codes (the helper returns
        # the enum for the exact code, not for any embedded substring).
        canonical = diagnosis_failure_reason_for_backend_lookup(
            BackendIncidentLookupFailureCode.INVALID_JSON
        )
        assert canonical.value == "backend_incident_invalid_json"
        # And the legacy compat layer's substring path no longer matches
        # the canonical prefix-suffix construction either; only an
        # EXACT value match passes.
        from k8s_diag_agent.collect.incident_diagnosis_disposition_compat import (
            _map_legacy_error_reason,
        )

        mapped = _map_legacy_error_reason("prefix_backend_incident_invalid_json_suffix")
        # ``_map_legacy_error_reason`` falls through to the heuristic
        # branches; it must NOT silently map to the canonical reason.
        from k8s_diag_agent.collect.incident_diagnosis_disposition import (
            DiagnosisEvaluationFailureReason,
        )
        assert mapped != DiagnosisEvaluationFailureReason.BACKEND_INCIDENT_INVALID_JSON, (
            "Embedded substring must NOT be classified as the canonical "
            f"backend_incident_invalid_json reason, got {mapped!r}"
        )


# ---------------------------------------------------------------------------
# 9. R1 closed-union verifier (exact three-variant set)
# ---------------------------------------------------------------------------


class TestClosedUnionVerifier:
    """The closed-union check must reject arbitrary extra members.

    The previous count(required) == 1 regex-style check would silently
    pass a mutation such as
    ``BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed | BackendIncidentRetryable``
    because every required identifier still appears exactly once. The
    verifier MUST parse the union expression, collect the identifier
    names, and compare the result EXACTLY against the closed set
    {BackendIncidentFound, BackendIncidentNotFound, BackendIncidentLookupFailed}.
    """

    def test_extra_fourth_variant_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An extra (forbidden) fourth member must be flagged."""
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId
            from k8s_diag_agent.collect.incident_lifecycle import Incident

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                incident: Incident
                source: str
                http_status: int | None

            @dataclass(frozen=True, slots=True)
            class BackendIncidentNotFound:
                requested_incident_id: IncidentId
                source: str

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            @dataclass(frozen=True, slots=True)
            class BackendIncidentRetryable:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentNotFound "
                "| BackendIncidentLookupFailed | BackendIncidentRetryable"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "BackendIncidentRetryable" in v for v in violations
        ), (
            "Expected extra-fourth-variant detection, got:\n"
            f"{_format_violations(violations)}"
        )

    def test_union_with_all_three_required_passes_identifier_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact closed-union set must NOT raise a union violation.

        The fixture omits the ``incident: object`` mutation so the only
        check exercised is the closed-union identifier comparison.
        """
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId
            from k8s_diag_agent.collect.incident_lifecycle import Incident

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                incident: Incident
                source: str
                http_status: int | None

            @dataclass(frozen=True, slots=True)
            class BackendIncidentNotFound:
                requested_incident_id: IncidentId
                source: str

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert not any("EXACTLY the closed union" in v for v in violations), (
            "Closed-union identifier check should pass for canonical union; "
            f"got:\n{_format_violations(violations)}"
        )

    def test_missing_one_variant_is_detected_via_strict_identifier_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing a variant must also be flagged by the strict identifier check."""
        new_source = textwrap.dedent(
            """
            from dataclasses import dataclass
            from enum import StrEnum
            from typing import TypeAlias
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId
            from k8s_diag_agent.collect.incident_lifecycle import Incident

            class BackendIncidentLookupFailureCode(StrEnum):
                INVALID_JSON = "invalid_json"

            @dataclass(frozen=True, slots=True)
            class BackendIncidentFound:
                requested_incident_id: IncidentId
                incident: Incident
                source: str
                http_status: int | None

            @dataclass(frozen=True, slots=True)
            class BackendIncidentLookupFailed:
                requested_incident_id: IncidentId

            BackendIncidentLookupOutcome: TypeAlias = (
                "BackendIncidentFound | BackendIncidentLookupFailed"
            )
            """
        )
        original_open = verifier._read

        def _patched(path: Path):
            if path.name == "incident_diagnosis_backend_detail_outcomes.py":
                return new_source
            return original_open(path)

        monkeypatch.setattr(verifier, "_read", _patched)
        violations = verifier._check_outcome_model()
        assert any(
            "BackendIncidentNotFound" in v and "missing" in v.lower()
            for v in violations
        ), (
            "Expected strict-identifier missing-variant detection, got:\n"
            f"{_format_violations(violations)}"
        )

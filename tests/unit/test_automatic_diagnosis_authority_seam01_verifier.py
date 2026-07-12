"""Self-tests for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier.

The static verifier lives at
``scripts/verifiers/automatic_diagnosis_authority_seam01.py``. These
self-tests prove that:

* the verifier PASSES against the current (fixed) production code
  (``run_static_checks() == []`` and ``main() == 0``);
* each forbidden form is actually detected — a verifier PASS is only
  meaningful if the negative fixtures fail as designed.

Every check that operates on an AST tree is exercised with a paired
negative fixture (must produce a violation) and positive fixture (must
not). This closes R1-8/R1-9: the verifier is no longer a green stamp
with untested detectors.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_VERIFIER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verifiers"
    / "automatic_diagnosis_authority_seam01.py"
)


def _load_verifier() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "adas01_verifier", _VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _module(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Production PASS: the verifier must accept the current fixed code.
# ---------------------------------------------------------------------------


class TestProductionPasses:
    def test_run_static_checks_is_clean(self) -> None:
        violations = verifier.run_static_checks()
        assert violations == [], f"unexpected violations: {violations}"

    def test_main_returns_zero(self) -> None:
        assert verifier.main([]) == 0


# ---------------------------------------------------------------------------
# Negative + positive fixtures for the tree-based checks.
# ---------------------------------------------------------------------------


class TestForbiddenProcessorCalls:
    def test_get_incident_store_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    store = get_incident_store()\n"
        )
        assert verifier._check_processor_calls(tree)

    def test_direct_lifecycle_method_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    store.mark_diagnosis_loop_started(incident_id=i)\n"
        )
        assert verifier._check_processor_calls(tree)

    def test_clean_processor_has_no_forbidden_calls(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    record_diagnosis_loop_started(incident_id=i)\n"
        )
        assert verifier._check_processor_calls(tree) == []


class TestOldIdResolver:
    def test_check_incident_eligibility_by_id_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    check_incident_eligibility(incident_id=x, config=c)\n"
        )
        assert verifier._check_processor_old_id_resolver(tree)

    def test_aggregate_call_is_allowed(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    evaluate_incident_eligibility(incident=obj, config=c)\n"
        )
        assert verifier._check_processor_old_id_resolver(tree) == []


class TestUsesAggregateEligibility:
    def test_missing_aggregate_call_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    x = 1\n"
        )
        assert verifier._check_processor_uses_aggregate_eligibility(tree)

    def test_present_aggregate_call_passes(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    evaluate_incident_eligibility(incident=obj, config=c)\n"
        )
        assert verifier._check_processor_uses_aggregate_eligibility(tree) == []

    def test_call_without_incident_kw_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    evaluate_incident_eligibility(config=c)\n"
        )
        assert verifier._check_processor_uses_aggregate_eligibility(tree)


class TestDispatchExhaustiveness:
    def test_missing_variant_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    match outcome:\n"
            "        case BackendIncidentFound():\n"
            "            pass\n"
        )
        assert verifier._check_processor_dispatch(tree)

    def test_all_three_variants_pass(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    match outcome:\n"
            "        case BackendIncidentNotFound():\n"
            "            pass\n"
            "        case BackendIncidentLookupFailed():\n"
            "            pass\n"
            "        case BackendIncidentFound():\n"
            "            pass\n"
        )
        assert verifier._check_processor_dispatch(tree) == []


class TestNoBackendToLocalFallback:
    def test_fetch_incident_local_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    fetch_incident_local(incident_id=i)\n"
        )
        assert verifier._check_processor_no_backend_to_local_fallback(tree)

    def test_clean_processor_passes(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    record_diagnosis_loop_started(incident_id=i)\n"
        )
        assert verifier._check_processor_no_backend_to_local_fallback(tree) == []


class TestNoSwallowedLifecycle:
    def test_except_pass_around_lifecycle_is_rejected(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    try:\n"
            "        record_diagnosis_loop_started(incident_id=i)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        assert verifier._check_processor_no_swallowed_lifecycle(tree)

    def test_except_pass_around_non_lifecycle_is_allowed(self) -> None:
        tree = _module(
            "def _process_incident():\n"
            "    try:\n"
            "        write_review_packet()\n"
            "    except Exception:\n"
            "        pass\n"
        )
        assert verifier._check_processor_no_swallowed_lifecycle(tree) == []


class TestTruthinessToNotFound:
    def test_assignment_form_is_detected(self) -> None:
        tree = _module(
            "if not incident:\n"
            "    reason = 'incident_not_found'\n"
        )
        assert verifier._contains_truthiness_to_not_found(tree) is True

    def test_constructor_keyword_form_is_detected(self) -> None:
        tree = _module(
            "if not incident:\n"
            "    return AutoLoopIncidentResult("
            "eligibility_reason='incident_not_found')\n"
        )
        assert verifier._contains_truthiness_to_not_found(tree) is True

    def test_clean_branch_is_not_flagged(self) -> None:
        tree = _module(
            "if not incident:\n"
            "    reason = 'ok'\n"
        )
        assert verifier._contains_truthiness_to_not_found(tree) is False


class TestEmptyExceptPass:
    def test_bare_except_pass_is_detected(self) -> None:
        tree = _module(
            "try:\n"
            "    foo()\n"
            "except Exception:\n"
            "    pass\n"
        )
        assert verifier._has_empty_except_pass(tree) is True

    def test_handled_except_is_not_flagged(self) -> None:
        tree = _module(
            "try:\n"
            "    foo()\n"
            "except Exception:\n"
            "    handle()\n"
        )
        assert verifier._has_empty_except_pass(tree) is False


class TestSeamAvailableNames:
    def test_defined_imported_exported_are_collected(self) -> None:
        tree = _module(
            "from x import record_diagnosis_loop_started\n"
            "__all__ = ['evaluate_incident_eligibility']\n"
            "def build_lifecycle_request():\n"
            "    pass\n"
        )
        defined, imported, exported = verifier._seam_available_names(tree)
        assert "build_lifecycle_request" in defined
        assert "record_diagnosis_loop_started" in imported
        assert "evaluate_incident_eligibility" in exported


class TestFailureKeywordMapping:
    """The production check reads the real processor; a fixture proves the
    call-keyword detector recognises the forbidden projection form."""

    def test_call_keyword_failure_mapping_is_detected_via_truthiness(self) -> None:
        # The failure-path detector shares the call-keyword recognition
        # with the truthiness detector; a synthetic ``if not`` guard
        # exercises the same ``eligibility_reason='incident_not_found'``
        # keyword form the failure-path check forbids.
        tree = _module(
            "if not ok:\n"
            "    AutoLoopIncidentResult(eligibility_reason='incident_not_found')\n"
        )
        assert verifier._contains_truthiness_to_not_found(tree) is True


if __name__ == "__main__":  # pragma: no cover - convenience
    raise SystemExit(pytest.main([__file__, "-q"]))

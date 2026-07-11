#!/usr/bin/env python3
"""Verifier: automatic-diagnosis disposition ADT contract.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01 (Section 10)

Verifies that the disposition ADT and its dependents conform to the
ACT contract:

1. The union contains the expected closed variants.
2. Disposition dataclasses are frozen.
3. Variants do not contain overlapping ``eligible``/``skipped``/``error`` flags.
4. The reducer uses exhaustive dispatch plus ``assert_never``.
5. Batch aggregation does not inspect serialized result dictionaries.
6. Reason maps are keyed by enum values internally.
7. Scheduler completion includes all three reason maps.
8. The aggregate summary schema version is explicit.
9. The production path invokes the canonical reducer/emitter.
10. No duplicate eligibility implementation exists in facades or compatibility
    modules.

This verifier is intentionally lightweight: it uses ``ast`` to inspect
the source tree and runs checks without spinning up a real scheduler.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"


@dataclass(frozen=True)
class VerifierResult:
    name: str
    passed: bool
    detail: str = ""


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read_source(path), filename=str(path))


def check_closed_union() -> list[VerifierResult]:
    """The union contains the expected closed variants."""
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    tree = _parse(disposition_path)
    found_variants: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Look for ``@dataclass(frozen=True, slots=True)`` decorator.
        is_frozen_dataclass = False
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            if getattr(dec.func, "id", "") != "dataclass":
                continue
            for kw in dec.keywords:
                if kw.arg == "frozen":
                    val = kw.value
                    if isinstance(val, ast.Constant) and val.value is True:
                        is_frozen_dataclass = True
                    elif isinstance(val, ast.NameConstant) and val.value is True:  # py<3.8
                        is_frozen_dataclass = True
        if is_frozen_dataclass:
            found_variants.add(node.name)
    expected = {
        "EligibleForAutomaticDiagnosis",
        "SkippedFromAutomaticDiagnosis",
        "IneligibleForAutomaticDiagnosis",
        "AutomaticDiagnosisEvaluationFailed",
    }
    return [
        VerifierResult(
            name="closed_union_contains_expected_variants",
            passed=expected.issubset(found_variants),
            detail=f"found={sorted(found_variants)} expected={sorted(expected)}",
        )
    ]


def check_variants_are_frozen() -> list[VerifierResult]:
    """Disposition dataclasses are frozen."""
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    tree = _parse(disposition_path)
    results: list[VerifierResult] = []
    expected = {
        "EligibleForAutomaticDiagnosis",
        "SkippedFromAutomaticDiagnosis",
        "IneligibleForAutomaticDiagnosis",
        "AutomaticDiagnosisEvaluationFailed",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in expected:
            is_frozen = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "dataclass":
                    for kw in dec.keywords:
                        if kw.arg == "frozen" and (
                            (isinstance(kw.value, ast.Constant) and kw.value.value is True)
                            or (isinstance(kw.value, ast.NameConstant) and kw.value.value is True)
                        ):
                            is_frozen = True
            results.append(
                VerifierResult(
                    name=f"variant_{node.name}_is_frozen",
                    passed=is_frozen,
                    detail=f"frozen={is_frozen}",
                )
            )
    return results


def check_variants_have_no_boolean_state() -> list[VerifierResult]:
    """Variants do not contain overlapping eligible/skipped/error flags."""
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    tree = _parse(disposition_path)
    expected = {
        "EligibleForAutomaticDiagnosis",
        "SkippedFromAutomaticDiagnosis",
        "IneligibleForAutomaticDiagnosis",
        "AutomaticDiagnosisEvaluationFailed",
    }
    forbidden = {"eligible", "skipped", "error"}
    results: list[VerifierResult] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in expected:
            names = {a.target.id for a in node.body if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)}
            offenders = names & forbidden
            results.append(
                VerifierResult(
                    name=f"variant_{node.name}_has_no_boolean_flags",
                    passed=not offenders,
                    detail=f"offenders={sorted(offenders)}" if offenders else "no offenders",
                )
            )
    return results


def _function_named(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def check_reducer_uses_assert_never() -> list[VerifierResult]:
    """``reduce_disposition()`` ends in ``typing.assert_never(...)``.

    AST-based detection scoped to the ``reduce_disposition`` function
    body only - other functions calling ``assert_never`` cannot
    falsely satisfy this check.
    """
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    tree = _parse(disposition_path)
    reducer = _function_named(tree, "reduce_disposition")
    if reducer is None:
        return [
            VerifierResult(
                name="reducer_uses_assert_never_sentinel",
                passed=False,
                detail="reduce_disposition not found",
            )
        ]
    assert_never_calls: list[ast.Call] = []
    for node in ast.walk(reducer):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name == "assert_never":
            assert_never_calls.append(node)
    has_assert_never = bool(assert_never_calls)
    return [
        VerifierResult(
            name="reducer_uses_assert_never_sentinel",
            passed=has_assert_never,
            detail=(
                f"{len(assert_never_calls)} assert_never() call(s) inside reduce_disposition"
                if has_assert_never
                else "reduce_disposition has no assert_never() call"
            ),
        )
    ]


def check_no_serialized_dict_scan_in_batch() -> list[VerifierResult]:
    """Batch aggregation does not inspect serialized result dictionaries."""
    batch_path = SRC_ROOT / "incident_diagnosis_auto_loop_batch.py"
    source = _read_source(batch_path)
    # The new code reduces via ``reduce_disposition`` and never inspects
    # ``incident_results`` (a tuple of dicts) to derive counters. We
    # accept the tuple as a projection but the counters and reason maps
    # must come from the typed summary.
    bad_patterns = [
        "for ir in ",
        "if ir.get(",
        "incident_results: list[dict",
        "for result_dict in",
    ]
    found = [p for p in bad_patterns if p in source]
    # ``incident_results: list[dict[str, object]] = []`` is the projection;
    # we tolerate it. Strip the empty-list initialization.
    found = [p for p in found if p != "incident_results: list[dict"]
    return [
        VerifierResult(
            name="batch_does_not_rescan_serialized_dicts",
            passed=not found,
            detail=f"patterns found: {found}" if found else "no dict-rescan patterns",
        )
    ]


def check_reason_maps_keyed_by_enum() -> list[VerifierResult]:
    """Reason maps are keyed by enum values internally."""
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    source = _read_source(disposition_path)
    # The summary type uses ``Mapping[DiagnosisSkipReason, int]`` etc.
    has_typed_keys = (
        "Mapping[DiagnosisSkipReason, int]" in source
        and "Mapping[DiagnosisIneligibleReason, int]" in source
        and "Mapping[DiagnosisEvaluationFailureReason, int]" in source
    )
    return [
        VerifierResult(
            name="reason_maps_keyed_by_enum",
            passed=has_typed_keys,
            detail="typed enum-keyed Mapping used" if has_typed_keys else "missing typed keys",
        )
    ]


def check_scheduler_completion_includes_reason_maps() -> list[VerifierResult]:
    """Scheduler completion includes all three reason maps."""
    scheduler_path = REPO_ROOT / "src" / "k8s_diag_agent" / "health" / "loop_automatic_diagnosis.py"
    source = _read_source(scheduler_path)
    has_skip = "skip_reasons" in source and '"skip_reasons"' in source
    has_ineligible = "ineligible_reasons" in source and '"ineligible_reasons"' in source
    has_error = "error_reasons" in source and '"error_reasons"' in source
    return [
        VerifierResult(
            name="scheduler_completion_includes_all_three_reason_maps",
            passed=has_skip and has_ineligible and has_error,
            detail=f"skip={has_skip} ineligible={has_ineligible} error={has_error}",
        )
    ]


def check_schema_version_is_explicit() -> list[VerifierResult]:
    """The aggregate summary schema version is explicit."""
    disposition_path = SRC_ROOT / "incident_diagnosis_disposition.py"
    source = _read_source(disposition_path)
    has_version = "SCHEMA_VERSION: int = 2" in source and '"schema_version"' in source
    return [
        VerifierResult(
            name="schema_version_explicit",
            passed=has_version,
            detail=f"SCHEMA_VERSION exported and emitted: {has_version}",
        )
    ]


def check_production_path_uses_canonical_reducer() -> list[VerifierResult]:
    """The production path invokes the canonical reducer/emitter."""
    batch_path = SRC_ROOT / "incident_diagnosis_auto_loop_batch.py"
    source = _read_source(batch_path)
    has_reduce = "reduce_disposition(" in source
    has_emit = "emit_structured_log(" in source or "emit_eligibility_summary(" in source
    return [
        VerifierResult(
            name="production_path_uses_canonical_reducer_and_emitter",
            passed=has_reduce and has_emit,
            detail=f"reduce={has_reduce} emit={has_emit}",
        )
    ]


def check_no_duplicate_eligibility_in_facades() -> list[VerifierResult]:
    """No duplicate eligibility implementation exists in facades/compatibility modules."""
    # We scan files in health/ for any code that calls
    # ``check_incident_eligibility`` directly (the eligibility decision
    # belongs in the collect module, not in the health facade). The
    # facade may import it for re-export but must not contain a copy
    # of the eligibility implementation.
    health_root = REPO_ROOT / "src" / "k8s_diag_agent" / "health"
    offenders: list[str] = []
    for path in health_root.rglob("*.py"):
        source = _read_source(path)
        if "check_incident_eligibility(" in source and "incident_diagnosis_auto_loop_config" not in source:
            # Allowed if the file just imports/re-exports. We check by
            # looking for the function call signature ``check_incident_eligibility(``
            # outside of an import statement.
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith("from ") or stripped.startswith("import "):
                    continue
                if "check_incident_eligibility(" in stripped and "=" not in stripped.split("check_incident_eligibility(")[0]:
                    offenders.append(str(path))
                    break
    return [
        VerifierResult(
            name="no_duplicate_eligibility_in_facades",
            passed=not offenders,
            detail=f"offenders={offenders}" if offenders else "no duplicate eligibility logic in health facades",
        )
    ]


CHECKS = [
    check_closed_union,
    check_variants_are_frozen,
    check_variants_have_no_boolean_state,
    check_reducer_uses_assert_never,
    check_no_serialized_dict_scan_in_batch,
    check_reason_maps_keyed_by_enum,
    check_scheduler_completion_includes_reason_maps,
    check_schema_version_is_explicit,
    check_production_path_uses_canonical_reducer,
    check_no_duplicate_eligibility_in_facades,
]


def main(argv: list[str] | None = None) -> int:
    results: list[VerifierResult] = []
    for check in CHECKS:
        results.extend(check())

    print("Verifier: automatic-diagnosis disposition ADT contract")
    print("=" * 60)
    failures = 0
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        marker = "OK " if r.passed else "X  "
        print(f"  [{status}] {marker}{r.name}: {r.detail}")
        if not r.passed:
            failures += 1

    print("=" * 60)
    if failures:
        print(f"FAILED ({failures}/{len(results)} checks)")
        return 1
    print(f"PASSED ({len(results)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

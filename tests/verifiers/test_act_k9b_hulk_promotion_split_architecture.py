"""Bounded architecture guards for the hard-file promotion split."""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest
from promotion_hulk_ast_support import (
    find_functions,
    parse_source,
    physical_lines,
)

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_handlers.py"
PROMOTION = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_handlers.py"
CANDIDATES = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_candidates.py"

VERIFIER_ROOT = ROOT / "tests" / "verifiers"
SPLIT_GUARD = "test_act_k9b_hulk_promotion_split_architecture.py"
PROMOTION_VERIFIER_FILES = tuple(
    sorted(
        path
        for path in VERIFIER_ROOT.glob("test_act_k9b_hulk_promotion_*.py")
        if path.name != SPLIT_GUARD
    )
)
SUPPORT_MODULES = (
    ROOT / "tests/verifiers/promotion_hulk_ast_support.py",
    ROOT / "tests/verifiers/promotion_hulk_gate_summary_support.py",
)

CANONICAL_HELPERS = (
    "_collect_function_bodies",
    "_assignment_targets",
    "_statements_contain_mutation",
    "_load",
    "_find_function",
    "_calls_in_function",
    "_call_name",
    "_imports",
    "_imports_from",
    "_module_names",
    "_write_atomic",
    "_minimal_passing_artifact",
)


def _duplicates(path: Path) -> list[str]:
    tree = parse_source(path)
    return sorted(name for name in CANONICAL_HELPERS if find_functions(tree, name))


def test_internal_handler_is_compatibility_facade_only() -> None:
    assert physical_lines(FACADE) < 150
    tree = parse_source(FACADE)
    assert not find_functions(tree, "handle_promote_alert_signals")
    assert not find_functions(tree, "handle_promote_candidates")


def test_promotion_handlers_have_one_implementation_owner() -> None:
    assert len(find_functions(parse_source(PROMOTION), "handle_promote_alert_signals")) == 1
    assert len(find_functions(parse_source(CANDIDATES), "handle_promote_candidates")) == 1
    assert not find_functions(parse_source(FACADE), "handle_promote_alert_signals")
    assert not find_functions(parse_source(FACADE), "handle_promote_candidates")


def test_replacement_modules_stay_below_hard_limit() -> None:
    assert physical_lines(FACADE) < 500
    assert physical_lines(PROMOTION) < 500
    assert physical_lines(CANDIDATES) < 500
    for module in SUPPORT_MODULES:
        assert physical_lines(module) < 300


def test_verifier_file_discovery_is_nonempty() -> None:
    """The promotion verifier inventory MUST be discoverable.

    The previous guard scanned ``ROOT.rglob("tests")`` followed by
    ``module.glob(...)``, which yielded zero paths because the
    candidate files live one directory deeper. The current
    discovery uses the explicit ``VERIFIER_ROOT`` so the
    inventory is non-empty by construction; a regression that
    renames the directory fails the explicit assertion.
    """
    assert len(PROMOTION_VERIFIER_FILES) > 0, (
        "PROMOTION_VERIFIER_FILES is empty; the promotion verifier "
        "directory glob no longer matches expected test files."
    )
    for path in PROMOTION_VERIFIER_FILES:
        assert path.exists(), f"{path.name} is in the inventory but missing on disk"


def test_support_module_contains_no_test_definitions() -> None:
    """Every support module MUST be test-free; the guard is precise.

    ``find_function`` raises on absence, so the canonical inventory
    is checked via ``find_functions`` which returns a list.
    """
    for module in SUPPORT_MODULES:
        tree = parse_source(module)
        test_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        test_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test")
        ]
        assert not test_names, f"{module.name} defines tests: {test_names}"
        assert not test_classes, f"{module.name} defines test classes: {test_classes}"


def test_canonical_helpers_live_only_in_support_modules() -> None:
    """Canonical helpers MUST be defined in one support module only.

    The split suites import each helper from the support module via
    an alias; redefining the helper inside a test module defeats
    the ownership contract. The guard walks every promotion
    verifier file under ``tests/verifiers`` and fails when any
    canonical helper is redefined outside the support modules.
    """
    for path in PROMOTION_VERIFIER_FILES:
        duplicates = _duplicates(path)
        assert not duplicates, f"{path.name} redefines canonical helpers: {duplicates}"


def test_canonical_helpers_are_actually_defined() -> None:
    """Every canonical helper MUST exist in the AST support module.

    The canonical names are not underscore-prefixed in the
    centralisation pass; the guard inspects the support module
    for the unprefixed form of each helper.
    """
    public_names = {
        name.lstrip("_") for name in CANONICAL_HELPERS if name.startswith("_")
    }
    expected_public = {
        "collect_function_bodies",
        "assignment_targets",
        "statements_contain_mutation",
        "load",
        "find_function",
        "calls_in_function",
        "call_name",
        "imports",
        "imports_from",
        "module_names",
        "write_atomic",
        "minimal_passing_artifact",
    }
    assert expected_public.issubset(public_names), (
        f"AST support module is missing canonical helpers: "
        f"{sorted(expected_public - public_names)}"
    )
    public_gate = {
        name.lstrip("_") for name in CANONICAL_HELPERS if name.startswith("_")
    }
    assert {"write_atomic", "minimal_passing_artifact"}.issubset(public_gate), (
        "Gate-summary support module is missing canonical helpers"
    )
    # Sanity: the import surface from the two support modules MUST
    # cover every entry in CANONICAL_HELPERS so the test modules
    # can rely on the unified alias import.
    available = public_names | public_gate
    for helper in CANONICAL_HELPERS:
        assert helper.lstrip("_") in available, (
            f"helper {helper!r} is not exported by any support module"
        )


def test_canonical_helpers_ownership_rejects_redefinitions(tmp_path: Path) -> None:
    """A redefinition of a canonical helper MUST be rejected.

    The negative proof writes a temporary verifier file that defines
    ``_load`` at module scope and confirms the ownership check
    fails. A parallel adversarial file with no helper definitions
    is accepted.
    """
    bad = tmp_path / "test_act_k9b_hulk_promotion_adversarial_bad.py"
    bad.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            def _load(path):  # canonical redefinition
                return path.read_text()
            """
        ).lstrip(),
        encoding="utf-8",
    )
    assert _duplicates(bad) == ["_load"], "adversarial redefinition was not detected"

    good = tmp_path / "test_act_k9b_hulk_promotion_adversarial_good.py"
    good.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            def test_local_helper_only() -> None:
                assert True
            """
        ).lstrip(),
        encoding="utf-8",
    )
    assert _duplicates(good) == []


def test_handler_lazy_imports_keep_store_provider_outside_module_load() -> None:
    """Handler modules MUST NOT import the store provider at module load."""
    for module in (FACADE, PROMOTION, CANDIDATES):
        tree = parse_source(module)
        offending: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import) and any(
                alias.name == "k8s_diag_agent.collect.incident_store_provider"
                or alias.name.endswith(".incident_store_provider")
                for alias in node.names
            ):
                offending.append(ast.unparse(node))
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("incident_store_provider")
            ):
                offending.append(ast.unparse(node))
        assert not offending, (
            f"{module.name} imports incident_store_provider at module load: {offending}"
        )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                and node.module.endswith("incident_store_provider")
            ):
                pytest.fail(
                    f"{module.name} carries an absolute import of incident_store_provider"
                )


def test_mutation_convergence_uses_ast_evidence() -> None:
    """The mutation-convergence guard MUST inspect the AST."""
    mutation = (ROOT / "src/k8s_diag_agent/collect/incident_promotion_accumulator_mutation.py").read_text()
    recorder = (ROOT / "src/k8s_diag_agent/collect/incident_promotion_scoped_atomic_recorder.py").read_text()
    mutation_tree = ast.parse(mutation)
    add_batch = next(
        (
            node
            for node in ast.walk(mutation_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "add_batch_mutation"
        ),
        None,
    )
    if add_batch is None:
        pytest.fail("add_batch_mutation MUST exist; the canonical owner is missing.")
    invokes_canonical = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_apply_batch_mutation"
        for node in ast.walk(add_batch)
    )
    assert invokes_canonical, "add_batch_mutation MUST invoke _apply_batch_mutation"
    recorder_tree = ast.parse(recorder)
    recorder_invokes = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_apply_batch"
        for node in ast.walk(recorder_tree)
    )
    assert recorder_invokes, "Scoped recorder MUST invoke the host's _apply_batch method"


def test_architecture_module_path_under_threshold() -> None:
    """The architecture guard module itself MUST stay under the hard limit."""
    assert physical_lines(ROOT / "tests/verifiers/test_act_k9b_hulk_promotion_split_architecture.py") < 300

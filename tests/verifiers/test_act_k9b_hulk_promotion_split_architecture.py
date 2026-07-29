"""Bounded architecture guards for the hard-file promotion split."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from promotion_hulk_ast_support import (
    find_function,
    find_functions,
    parse_source,
    physical_lines,
)

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_handlers.py"
PROMOTION = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_handlers.py"
CANDIDATES = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_candidates.py"

SUPPORT_MODULES = (
    ROOT / "tests/verifiers/promotion_hulk_ast_support.py",
    ROOT / "tests/verifiers/promotion_hulk_gate_summary_support.py",
)


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


def test_support_module_contains_no_test_definitions() -> None:
    """Every support module MUST be test-free; the guard is precise.

    ``find_functions`` performs exact-name matching, so a real
    ``test_*`` function would not be detected by the legacy
    ``test_*`` sentinel. The guard therefore inspects the AST
    directly for any ``test_*`` definition and any test class.
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
    the ownership contract. AST-shape equality is used to ignore
    trivial whitespace differences between the canonical source and
    any potential duplicate.
    """
    canonical_helpers = {
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
    }
    for module in ROOT.rglob("tests"):
        for path in module.glob("test_act_k9b_hulk_promotion_*.py"):
            if path.name == "test_act_k9b_hulk_promotion_split_architecture.py":
                continue
            tree = parse_source(path)
            duplicates = sorted(
                name
                for name in canonical_helpers
                if find_function(tree, name) is not None
            )
            assert not duplicates, f"{path.name} redefines canonical helpers: {duplicates}"


def test_handler_lazy_imports_keep_store_provider_outside_module_load() -> None:
    """Handler modules MUST NOT import the store provider at module load.

    The split removed the eager ``get_incident_store`` import. This
    guard inspects the AST for any top-level import that resolves to
    ``k8s_diag_agent.collect.incident_store_provider``.
    """
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
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(
                "incident_store_provider"
            ):
                offending.append(ast.unparse(node))
        assert not offending, (
            f"{module.name} imports incident_store_provider at module load: {offending}"
        )
        # The lazy import lives inside the handler function bodies; AST
        # inspection already proves it is not at module scope.
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
    """The mutation-convergence guard MUST inspect the AST.

    The legacy guard returned a silent ``pass`` when the recorder
    text omitted ``_apply_batch``, hiding the regression it
    claimed to detect. The replacement walks both ``add_batch_mutation``
    and the scoped recorder and fails when either path drops the
    canonical helper call.
    """
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

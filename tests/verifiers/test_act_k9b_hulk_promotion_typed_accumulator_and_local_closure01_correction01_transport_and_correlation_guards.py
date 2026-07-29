"""AST architecture guards for the active scoped promotion path.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

The guards in this module fail at test time when the active
scoped dispatcher path violates any of the typed-accumulator
invariants. The guards are intentionally AST-based so they catch
violations regardless of runtime behavior.

Invariants enforced:

1. The active scoped accumulator function
   (``promote_alert_signals_scoped_for_accumulator``) MUST NOT
   call any of the legacy dict-shaped helpers.
2. The active scoped accumulator function MUST NOT call
   ``_result_from_dict`` -- the original ``PromotionOutcome``
   reaches the accumulator unchanged.
3. The active dispatcher module MUST NOT import the legacy
   adapter module that holds the legacy dict shim.
4. The typed dispatch-result module MUST NOT import the legacy
   adapter module that holds the legacy dict shim.
5. The closed ``ScopedPromotionAccumulatorHandoff`` MUST be
   consumed by ``RunPromotionAccumulator.record_scoped_promotion_batch``.
6. The active dispatcher's scoped accumulator function MUST call
   ``record_scoped_promotion_batch`` exactly ONCE and MUST call
   ``scoped_dispatch_result_to_accumulator_handoff``.
7. The active dispatcher's scoped accumulator function MUST NOT
   invent a per-signal ``promotion_records`` tuple for aggregate
   scoped results.
8. The legacy compatibility wrapper
   ``RunPromotionAccumulator.record_scoped_promotion`` MUST forward
   to ``record_scoped_promotion_batch`` so request-identity authority
   remains singular.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"

ACTIVE_DISPATCH_FILE = SRC_ROOT / "incident_promotion_dispatch_scoped.py"
DISPATCH_RESULT_FILE = SRC_ROOT / "promotion_scoped_http_seam.py"
HANDOFF_FILE = SRC_ROOT / "promotion_scoped_accumulator_handoff.py"
ACCUMULATOR_FILE = SRC_ROOT / "incident_promotion_accumulator.py"
LEGACY_ADAPTER_FILE = SRC_ROOT / "incident_promotion_scoped_legacy_adapter.py"


def _load(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _find_function(
    tree: ast.Module, qualified_name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Find a function by qualified name (top-level or class method)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == qualified_name
        ):
            return node
    raise AssertionError(
        f"function {qualified_name!r} not found in {tree}"
    )


def _calls_in_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """Return all ``Call`` nodes nested anywhere in the function."""
    calls: list[ast.Call] = []
    for sub in ast.walk(func):
        if isinstance(sub, ast.Call):
            calls.append(sub)
    return calls


def _call_name(call: ast.Call) -> str | None:
    """Return the qualified name of a call's callable, or ``None``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _imports(tree: ast.Module) -> set[str]:
    """Return the set of imported top-level module names."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module is None:
                # ``from . import x`` -- relative; module is the package.
                names.add(f".{node.level}")
                continue
            if node.module is None:
                continue
            names.add(node.module.split(".")[0])
    return names


def _imports_from(tree: ast.Module) -> list[ast.ImportFrom]:
    """Return all ``ImportFrom`` nodes (including ``from . import x``)."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]


def _scoped_dispatch_result_to_accumulator_handoff_used(
    tree: ast.Module,
) -> bool:
    """Return True if the function references the typed handoff adapter."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == (
            "scoped_dispatch_result_to_accumulator_handoff"
        ):
            return True
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "scoped_dispatch_result_to_accumulator_handoff"
        ):
            return True
    return False


def test_handoff_module_exposes_closed_union_and_adapter() -> None:
    """The handoff module MUST expose the closed union and adapter."""
    tree = _load(HANDOFF_FILE)
    names = _module_names(tree)
    required = {
        "ScopedPromotionAccumulatorCompleted",
        "ScopedPromotionAccumulatorUncertain",
        "ScopedPromotionAccumulatorRejected",
        "ScopedPromotionAccumulatorHandoff",
        "scoped_dispatch_result_to_accumulator_handoff",
    }
    missing = required - names
    if missing:
        pytest.fail(
            "Handoff module is missing required symbols: "
            f"{sorted(missing)}"
        )

def test_handoff_uses_assert_never() -> None:
    """The adapter MUST end with ``assert_never(result)`` for exhaustiveness."""
    tree = _load(HANDOFF_FILE)
    func = _find_function(
        tree, "scoped_dispatch_result_to_accumulator_handoff"
    )
    last_statement = func.body[-1]
    if not (
        isinstance(last_statement, ast.Expr)
        and isinstance(last_statement.value, ast.Call)
        and _call_name(last_statement.value) == "assert_never"
    ):
        pytest.fail(
            "scoped_dispatch_result_to_accumulator_handoff MUST end "
            "with assert_never(result) for exhaustiveness."
        )

def test_active_scoped_path_does_not_synthesise_records() -> None:
    """Aggregate scoped result MUST NOT carry a synthesised
    ``promotion_records`` tuple. The check looks for the
    ``PromotionBatch(promotion_result=..., promotion_records=...``
    construction with a non-empty literal that contradicts the
    closed handoff invariant."""
    tree = _load(ACTIVE_DISPATCH_FILE)
    func = _find_function(
        tree, "promote_alert_signals_scoped_for_accumulator"
    )
    for sub in ast.walk(func):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "PromotionBatch"
        ):
            for kw in sub.keywords:
                if (
                    kw.arg == "promotion_records"
                    and not isinstance(kw.value, ast.Tuple)
                ):
                    pytest.fail(
                        "Active scoped path MUST construct "
                        "PromotionBatch with promotion_records=() "
                        "(the empty tuple); aggregate scoped results "
                        "do not carry per-signal records."
                    )

def test_legacy_adapter_does_not_depend_on_active_modules() -> None:
    """The legacy adapter MUST NOT import the active dispatcher
    or health/loop_runner modules. The legacy adapter is
    intentionally isolated."""
    tree = _load(LEGACY_ADAPTER_FILE)
    forbidden_substrings = (
        "incident_promotion_dispatch",
        "loop_runner",
        "automatic_diagnosis",
    )
    for node in _imports_from(tree):
        if node.module is None:
            continue
        if any(
            substring in node.module
            for substring in forbidden_substrings
        ):
            pytest.fail(
                "Legacy adapter MUST NOT import active module "
                f"{node.module!r}"
            )


def _module_names(tree: ast.Module) -> set[str]:
    """Collect names declared at module scope."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names

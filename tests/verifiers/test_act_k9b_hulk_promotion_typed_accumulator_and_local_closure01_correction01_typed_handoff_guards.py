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


def test_active_scoped_path_does_not_call_legacy_dict_helpers() -> None:
    """Active scoped accumulator function MUST NOT call legacy dict shims."""
    tree = _load(ACTIVE_DISPATCH_FILE)
    func = _find_function(
        tree, "promote_alert_signals_scoped_for_accumulator"
    )
    forbidden = {
        "scoped_dispatch_result_to_promotion_result_dict",
        "promote_alert_signals_via_scoped_backend_api_as_dict",
        "_result_from_dict",
        "_response_to_promotion_result",
        "_coerce_promotion_response",
    }
    for call in _calls_in_function(func):
        name = _call_name(call)
        if name is None:
            continue
        bare = name.split(".")[-1]
        if bare in forbidden:
            pytest.fail(
                "Active scoped accumulator path "
                f"{func.name!r} must not call legacy dict helper "
                f"{bare!r}; use "
                "scoped_dispatch_result_to_accumulator_handoff instead."
            )

def test_active_scoped_path_calls_typed_handoff_adapter() -> None:
    """Active scoped path MUST use the typed accumulator handoff adapter."""
    tree = _load(ACTIVE_DISPATCH_FILE)
    _find_function(
        tree, "promote_alert_signals_scoped_for_accumulator"
    )
    if not _scoped_dispatch_result_to_accumulator_handoff_used(tree):
        pytest.fail(
            "Active scoped path MUST reference "
            "scoped_dispatch_result_to_accumulator_handoff"
        )

def test_active_scoped_path_calls_record_scoped_promotion_batch_once() -> None:
    """The active scoped dispatcher MUST call the atomic recorder exactly once.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
    CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01: the
    single-call invariant forbids the dispatcher from also calling
    ``record_scoped_promotion``, ``add_batch``, or
    ``record_promotion_outcome`` for the same scoped handoff.
    """
    tree = _load(ACTIVE_DISPATCH_FILE)
    func = _find_function(
        tree, "promote_alert_signals_scoped_for_accumulator"
    )
    seen_atomic = 0
    legacy_names: set[str] = set()
    for call in _calls_in_function(func):
        name = _call_name(call)
        if name is None:
            continue
        bare = name.split(".")[-1]
        if bare == "record_scoped_promotion_batch":
            seen_atomic += 1
        elif bare == "record_scoped_promotion":
            legacy_names.add(bare)
        elif bare == "add_batch":
            legacy_names.add(bare)
        elif bare == "record_promotion_outcome":
            legacy_names.add(bare)
    if seen_atomic != 1:
        pytest.fail(
            "Active scoped dispatcher MUST call "
            "RunPromotionAccumulator.record_scoped_promotion_batch "
            f"exactly once (found {seen_atomic} calls)"
        )
    if legacy_names:
        pytest.fail(
            "Active scoped dispatcher MUST NOT call legacy accumulator "
            f"mutators {sorted(legacy_names)}; route every mutation "
            "through record_scoped_promotion_batch."
        )

def test_active_dispatcher_does_not_import_legacy_adapter() -> None:
    """The active dispatcher MUST NOT import the legacy dict adapter."""
    tree = _load(ACTIVE_DISPATCH_FILE)
    for node in _imports_from(tree):
        if node.module is None:
            continue
        if node.module.endswith(
            "incident_promotion_scoped_legacy_adapter"
        ):
            pytest.fail(
                "Active dispatcher imports the legacy adapter "
                f"({node.module!r}); the active scoped path must "
                "consume the typed dispatch result directly."
            )

def test_dispatch_result_module_does_not_import_legacy_adapter() -> None:
    """The dispatch-result module MUST NOT depend on the legacy adapter."""
    tree = _load(DISPATCH_RESULT_FILE)
    for node in _imports_from(tree):
        if node.module is None:
            continue
        if node.module.endswith(
            "incident_promotion_scoped_legacy_adapter"
        ):
            pytest.fail(
                "Dispatch-result module imports the legacy adapter; "
                "the seam cannot own the mapper+adapter cycle."
            )

def test_handoff_module_does_not_import_legacy_adapter() -> None:
    """The handoff module MUST NOT depend on the legacy adapter."""
    tree = _load(HANDOFF_FILE)
    for node in _imports_from(tree):
        if node.module is None:
            continue
        if node.module.endswith(
            "incident_promotion_scoped_legacy_adapter"
        ):
            pytest.fail(
                "Handoff module imports the legacy adapter; the "
                "active accumulator handoff is the typed authority."
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

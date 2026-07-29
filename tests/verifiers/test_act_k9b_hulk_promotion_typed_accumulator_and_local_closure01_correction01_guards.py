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

ACTIVE_DISPATCH_FILE = SRC_ROOT / "incident_promotion_dispatch.py"
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


def _calls_in_function(func: ast.FunctionDef) -> list[ast.Call]:
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
    """Collect names declared at the module top level."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(
            node.target, ast.Name
        ):
            names.add(node.target.id)
    return names


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


def test_active_scoped_path_forwards_outcome_by_identity() -> None:
    """Active scoped path MUST NOT reconstruct a second ``PromotionOutcome``.

    The handoff carries the original outcome by identity. The
    active scoped path MUST NOT call ``PromotionSucceeded(...)``
    or any sibling constructor directly.
    """
    tree = _load(ACTIVE_DISPATCH_FILE)
    func = _find_function(
        tree, "promote_alert_signals_scoped_for_accumulator"
    )
    forbidden_constructors = {
        "PromotionSucceeded",
        "PromotionCommitUnknown",
        "PromotionRejected",
    }
    for sub in ast.walk(func):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            if sub.func.id in forbidden_constructors:
                pytest.fail(
                    "Active scoped path MUST NOT reconstruct a "
                    f"PromotionOutcome ({sub.func.id}); the handoff "
                    "carries the original by identity."
                )


def test_handoff_carries_original_outcome_by_identity() -> None:
    """The adapter MUST NOT reconstruct a ``PromotionOutcome``;
    the original is forwarded unchanged."""
    tree = _load(HANDOFF_FILE)
    func = _find_function(
        tree, "scoped_dispatch_result_to_accumulator_handoff"
    )
    forbidden_constructors = {
        "PromotionSucceeded",
        "PromotionCommitUnknown",
        "PromotionRejected",
    }
    for sub in ast.walk(func):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            if sub.func.id in forbidden_constructors:
                pytest.fail(
                    "Adapter MUST NOT reconstruct a PromotionOutcome; "
                    f"the original is forwarded by identity ({sub.func.id})."
                )


def test_record_scoped_promotion_forwards_to_atomic_recorder() -> None:
    """``record_scoped_promotion`` MUST forward to the atomic recorder.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
    CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01: the legacy
    one-argument wrapper exists only as a compatibility shim for
    direct unit tests; it MUST funnel every mutation through
    ``record_scoped_promotion_batch`` so the
    single-request-identity-authority invariant is preserved.
    """
    tree = _load(ACCUMULATOR_FILE)
    func = _find_function(tree, "record_scoped_promotion")
    seen_atomic = False
    seen_legacy = False
    for call in _calls_in_function(func):
        name = _call_name(call)
        if name is None:
            continue
        bare = name.split(".")[-1]
        if bare == "record_scoped_promotion_batch":
            seen_atomic = True
        elif bare == "record_promotion_outcome":
            seen_legacy = True
        elif bare == "add_batch":
            seen_legacy = True
    if not seen_atomic:
        pytest.fail(
            "RunPromotionAccumulator.record_scoped_promotion MUST "
            "forward through record_scoped_promotion_batch."
        )
    if seen_legacy:
        pytest.fail(
            "RunPromotionAccumulator.record_scoped_promotion MUST NOT "
            "mutate via record_promotion_outcome/add_batch; route "
            "everything through record_scoped_promotion_batch."
        )


def test_atomic_recorder_module_exposes_mixin_and_helpers() -> None:
    """The atomic recorder module MUST expose the required public surface."""
    tree = _load(
        SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py"
    )
    names = _module_names(tree)
    required = {
        "ScopedPromotionAtomicRecorderMixin",
        "_validate_scoped_handoff_batch_consistency",
        "_scoped_handoff_equivalent",
        "_batch_accounting_equivalent",
        "_build_compatibility_batch_from_handoff",
    }
    missing = required - names
    if missing:
        pytest.fail(
            "Atomic recorder module is missing required symbols: "
            f"{sorted(missing)}"
        )


def test_accumulator_does_not_assign_to_derived_request_id_fields() -> None:
    """The accumulator MUST NOT assign to ``scoped_promotion_request_id`` /
    ``scoped_promotion_request_fingerprint`` -- both are derived @property
    projections of ``scoped_promotion_handoff`` and assignment is forbidden.
    """
    tree = _load(ACCUMULATOR_FILE)
    accumulator_cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RunPromotionAccumulator"
    )
    forbidden_targets = {
        "scoped_promotion_request_id",
        "scoped_promotion_request_fingerprint",
    }
    forbidden_field_anns = []
    for stmt in accumulator_cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.target, ast.Name
        ):
            if stmt.target.id in forbidden_targets:
                forbidden_field_anns.append(stmt.target.id)
    if forbidden_field_anns:
        pytest.fail(
            "RunPromotionAccumulator MUST NOT declare mutable fields "
            f"{forbidden_field_anns!r}; they are derived projections "
            "of scoped_promotion_handoff."
        )
    # Walk methods to ensure no plain assignment is performed on
    # these names either.
    for node in ast.walk(accumulator_cls):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id in forbidden_targets
                ):
                    pytest.fail(
                        f"RunPromotionAccumulator MUST NOT assign to "
                        f"{target.id!r}; assignment is forbidden."
                    )

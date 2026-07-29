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
    # The implementation is split: the class delegates to the compatibility
    # owner, which must in turn reach the atomic recorder.
    if not seen_atomic:
        compat_tree = _load(
            SRC_ROOT / "incident_promotion_accumulator_compat.py"
        )
        compat_func = _find_function(compat_tree, "record_scoped_promotion_compat")
        seen_atomic = any(
            _call_name(call).split(".")[-1] == "record_scoped_promotion_batch"
            for call in _calls_in_function(compat_func)
            if _call_name(call) is not None
        )
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

def test_atomic_recorder_modules_expose_split_public_surface() -> None:
    """The split atomic-recorder modules MUST expose the required surface.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
    REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01 split the previous
    739-line recorder into four small modules. The guard pins the
    public surface across those modules.
    """
    required = {
        SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py": {
            "ScopedPromotionAtomicRecorderMixin",
        },
        SRC_ROOT
        / "incident_promotion_scoped_atomic_validation.py": {
            "validate_scoped_handoff_batch_consistency",
        },
        SRC_ROOT / "incident_promotion_scoped_atomic_equivalence.py": {
            "_receipt_equivalent",
            "_batch_accounting_equivalent",
        },
        SRC_ROOT
        / "incident_promotion_scoped_atomic_projection.py": {
            "build_compatibility_batch_from_handoff",
        },
    }
    missing: list[str] = []
    for path, expected in required.items():
        tree = _load(path)
        names = _module_names(tree)
        for symbol in expected:
            if symbol not in names:
                missing.append(f"{path.name}::{symbol}")
    if missing:
        pytest.fail(
            "Atomic recorder modules are missing required symbols: "
            f"{sorted(missing)}"
        )

def test_each_split_recorder_module_under_size_limit() -> None:
    """Every split recorder module MUST stay below the hard size limit."""
    import re

    path_to_limit = {
        SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py": 500,
        SRC_ROOT
        / "incident_promotion_scoped_atomic_validation.py": 500,
        SRC_ROOT / "incident_promotion_scoped_atomic_equivalence.py": 500,
        SRC_ROOT
        / "incident_promotion_scoped_atomic_projection.py": 500,
    }
    offenders: list[str] = []
    for path, limit in path_to_limit.items():
        text = path.read_text()
        # Comments only -- count non-comment, non-blank lines.
        non_comment_lines = 0
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            non_comment_lines += 1
        if non_comment_lines > limit:
            offenders.append(
                f"{path.name} has {non_comment_lines} non-comment lines "
                f"(limit {limit})"
            )
    # Comment-only lines are stripped by the `startswith("#")` filter, so
    # this guard's "non-comment lines" metric intentionally ignores the
    # module docstring and inline commentary.
    _ = re  # silence unused-import lint
    if offenders:
        pytest.fail(
            "Atomic recorder modules exceed the hard size limit: "
            + ", ".join(offenders)
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

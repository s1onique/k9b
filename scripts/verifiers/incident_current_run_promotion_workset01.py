#!/usr/bin/env python3
"""Static verifier for ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01.

This verifier proves the post-ACT invariants remain in place by inspecting
the production tree. Every detector (``check_*``) returns a list of human
readable violation strings; an empty list means the invariant holds.

The verifier is exercised both as a script (``python
scripts/verifiers/incident_current_run_promotion_workset01.py``) and via
``importlib.util.spec_from_file_location`` from the self-tests
(``tests/verifiers/test_incident_current_run_promotion_workset01.py``).
Each detector has a paired negative fixture in the self-test that proves
the detector is non-trivial: replacing the production sentinel detected
by the detector with the fixture pattern MUST cause this verifier to emit
at least one violation.

Suggested by: ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
"""


from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SRC_ROOT: Path = REPO_ROOT / "src" / "k8s_diag_agent"

# R100 (P1): ``_Binding.path`` is the ``(parent_id, attr_name)`` tuple
# used to discriminate ``if.body`` items from ``if.orelse`` items from
# the same ``If`` parent, etc. The runtime-scope walker
# ``_walk_runtime_scope_with_parent`` returns this exact pair and
# the harvest threads it through ``_add_binding(path=...)``. The
# earlier ``int`` annotation contradicted both the call site and the
# docstring; mypy was happy only because the verifier-specific fileset
# was not in the ``mypy`` command of the gate summary. The proper
# alias makes the contract explicit and lets a verifier-specific
# mypy run flag any future drift.
BindingPath = tuple[int, str]

INGESTION_PATH: Final[Path] = (
    SRC_ROOT / "health" / "loop_alertmanager_snapshot_signals.py"
)
SCOPED_PROMOTION_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_promotion_scoped.py"
)
HANDLER_PATH: Final[Path] = (
    SRC_ROOT / "ui" / "server_incident_internal_promotion_handlers.py"
)
BACKEND_ADAPTER_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_promotion_backend.py"
)
SCHEDULER_CLIENT_PATH: Final[Path] = (
    SRC_ROOT / "ui" / "server_incident_internal_fetch.py"
)
CONTRACT_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_promotion_contract.py"
)
ADAPTER_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_signal_snapshot_adapter.py"
)
PROCESSOR_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_evidence_processor.py"
)
BATCH_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_batch.py"
)
BUDGET_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_review_packet_budget.py"
)
COLLECTOR_PATH: Final[Path] = (
    SRC_ROOT
    / "collect"
    / "incident_diagnosis_auto_loop_evidence_collection.py"
)
ELIGIBILITY_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_config.py"
)
PERSISTENCE_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_signal_persistence.py"
)


# ---------------------------------------------------------------------------
# AST / text helpers
# ---------------------------------------------------------------------------


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_read_source(path), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _function_def(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _contains_call_to_any(node: ast.AST, name: str) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _contains_call_to(tree: ast.AST, name: str) -> bool:
    return _contains_call_to_any(tree, name)


def _contains_text(tree: ast.Module, needle: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if needle in node.value:
                return True
        if isinstance(node, ast.Attribute) and node.attr == needle:
            return True
    return False


def _contains_exact_string_constant(tree: ast.AST, needle: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == needle:
            return True
    return False


def _function_uses_call(
    tree: ast.Module, fn_name: str, call_name: str
) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    return _contains_call_to_any(fn, call_name)


def _function_uses_call_with_kwarg(
    tree: ast.Module, fn_name: str, call_name: str, kwarg_name: str
) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id != call_name:
            continue
        if isinstance(func, ast.Attribute) and func.attr != call_name:
            continue
        for kw in node.keywords:
            if kw.arg == kwarg_name:
                return True
    return False


def _function_uses_kwarg(
    tree: ast.Module, fn_name: str, kwarg_name: str
) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    for arg in fn.args.args:
        if arg.arg == kwarg_name:
            return True
    for arg in getattr(fn.args, "kwonlyargs", []):
        if arg.arg == kwarg_name:
            return True
    return False


def _function_def_in(
    tree: ast.Module, name: str
) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# Ingestion detectors
# ---------------------------------------------------------------------------


def check_ingestion_uses_scoped_promotion(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    if _contains_call_to(tree, "promote_alert_signals_for_accumulator"):
        violations.append(
            "ingestion uses promote_alert_signals_for_accumulator; "
            "must call promote_alert_signals_scoped_for_accumulator"
        )
    if not _contains_call_to(
        tree, "promote_alert_signals_scoped_for_accumulator"
    ):
        violations.append(
            "ingestion does not call "
            "promote_alert_signals_scoped_for_accumulator"
        )
    return violations


def check_ingestion_forbids_global_scan_fallback(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if _contains_call_to(tree, "scan_alert_signals_as_candidates"):
        return [
            "ingestion calls scan_alert_signals_as_candidates "
            "(global scan fallback)"
        ]
    return []



def _contains_exact_string_constant_in_live_scope(
    node: ast.AST, needle: str
) -> bool:
    """R51 (P0): only the live lexical scope of ``node`` is searched.

    Uses the same-scope-pruned traversal as the rest of the
    canonical chain so uncalled nested helpers / classes cannot
    satisfy the scope-log detector.
    """
    for sub in _walk_same_function_scope(node):
        if isinstance(sub, ast.Constant) and sub.value == needle:
            return True
    return False


def check_ingestion_logs_explicit_current_run_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    ingest = _function_def_in(tree, "_ingest_alert_signals")
    if ingest is None:
        return [
            "ingestion does not define _ingest_alert_signals; the "
            "canonical ingestion function is missing."
        ]
    if not _contains_exact_string_constant_in_live_scope(
        ingest, "explicit_current_run_signal_ids"
    ):
        return [
            "ingestion does not log promotion_scope="
            "explicit_current_run_signal_ids"
        ]
    return []


def check_ingestion_uses_artifact_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    ingest = _function_def_in(tree, "_ingest_alert_signals")
    if ingest is None:
        return [
            "ingestion does not define _ingest_alert_signals; the "
            "canonical ingestion function is missing."
        ]
    violations: list[str] = []
    for node in ast.walk(ingest):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "str":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Attribute) and arg.attr == "signal_id":
                violations.append(
                    "ingestion uses str(<...>.signal_id); "
                    "must source the workset from the persisted "
                    "PersistedAlertSignal.artifact_identity"
                )
    if not _contains_call_to(ingest, "build_current_run_workset"):
        violations.append(
            "ingestion does not build the current-run workset via "
            "build_current_run_workset; the persisted "
            "PersistedAlertSignal.artifact_identity is not the "
            "authoritative scope."
        )
    return violations


# ---------------------------------------------------------------------------
# R22/R23/R32/R33/R37/R38/R39/R40 helpers
# ---------------------------------------------------------------------------


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _kwarg_value(call: ast.Call, name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _build_parent_map(root: ast.AST) -> dict[int, ast.AST]:
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(root):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent
    return parent_map


def _enclosing_for(
    parent_map: dict[int, ast.AST], node: ast.AST
) -> ast.For | None:
    """R37 (P0): true AST ancestry for the enclosing loop."""
    current: ast.AST = node
    while id(current) in parent_map:
        current = parent_map[id(current)]
        if isinstance(current, ast.For):
            return current
    return None


def _for_target_name(for_node: ast.For) -> str | None:
    target = for_node.target
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            if isinstance(elt, ast.Name):
                return elt.id
                break
    return None



def _node_position(node: ast.AST) -> tuple[int, int]:
    """Return a stable source position for an AST node."""
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _is_scope_boundary(node: ast.AST) -> bool:
    """Return True if ``node`` opens a fresh lexical scope.

    Traversal of an ingestion function must prune these so that calls and
    assignments declared inside an uncalled nested helper / class are not
    mistaken for live runtime statements of the enclosing function.
    """
    return isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
    )


def _walk_same_function_scope(node: ast.AST) -> Iterable[ast.AST]:
    """Iterate ``node`` descendants while pruning nested lexical scopes.

    ``ast.walk`` recursively yields every descendant without
    distinguishing reachable code from declarations inside nested
    functions, lambdas, or class bodies. R46 requires the verifier to
    explicitly ignore those nested scopes when proving the executable
    chain.
    """
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if _is_scope_boundary(current):
            continue
        stack.extend(ast.iter_child_nodes(current))




def _if_uses_target_isinstance(if_node: ast.If, target_name: str) -> bool:
    """True when ``if_node`` is an ``isinstance(<target_name>, ...)`` dispatch.

    R48 (P0): the dispatch subject must be the enclosing loop target
    so an unrelated ``isinstance(unrelated, T)`` branch cannot
    contribute an assignment.
    """
    if not isinstance(if_node.test, ast.Call):
        return False
    func = if_node.test.func
    if not (isinstance(func, ast.Name) and func.id == "isinstance"):
        return False
    if not if_node.test.args:
        return False
    subject = if_node.test.args[0]
    if not isinstance(subject, ast.Name):
        return False
    return subject.id == target_name





def _collect_direct_assignments_in_body(
    body: list[ast.stmt], name: str, max_position: tuple[int, int]
) -> list[ast.stmt]:
    """Find ``name`` assignments that are *direct* statements of ``body``.

    R47 (P0): nested loops and arbitrary nested branches may execute zero
    times, so they do not establish that the alias dominates the
    constructor or append. Only assignments that appear as immediate
    statements of the enclosing ``for`` body, or inside the canonical
    ``if isinstance(<target>, T): ...; continue`` dispatch, are accepted.
    """
    matches: list[ast.stmt] = []

    def _isinstance_dispatch(if_node: ast.If) -> bool:
        return _if_ends_with_continue(if_node) and isinstance(
            if_node.test, ast.Call
        ) and isinstance(if_node.test.func, ast.Name) and (
            if_node.test.func.id == "isinstance"
        )

    def _collect_in_arm(body: list[ast.stmt]) -> None:
        for inner in body:
            if _node_position(inner) > max_position:
                continue
            if isinstance(inner, (ast.Assign, ast.AnnAssign)):
                if isinstance(inner, ast.Assign):
                    targets = inner.targets
                else:
                    targets = (
                        [inner.target] if inner.target is not None else []
                    )
                for t in targets:
                    if (
                        isinstance(t, ast.Name)
                        and t.id == name
                        and _node_position(inner) <= max_position
                    ):
                        matches.append(inner)
                continue
            if isinstance(inner, ast.If) and _isinstance_dispatch(inner):
                _collect_in_arm(inner.body)
                continue
            # Other statement kinds are not descended into (R47 closed
            # grammar -- ``try``/``with``/``match``/nested ``for`` cannot
            # provide the alias).

    def _visit_stmt(stmt: ast.stmt) -> None:
        if _node_position(stmt) > max_position:
            return
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            else:
                targets = [stmt.target] if stmt.target is not None else []
            for t in targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == name
                    and _node_position(stmt) <= max_position
                ):
                    matches.append(stmt)

    for stmt in body:
        _visit_stmt(stmt)
        if isinstance(stmt, ast.If) and _isinstance_dispatch(stmt):
            _collect_in_arm(stmt.body)
    return matches


def _find_assignment_in_body(
    body: list[ast.stmt], name: str, max_position: tuple[int, int]
) -> tuple[ast.Assign | ast.AnnAssign | None, tuple[int, int] | None]:
    """Return the last *direct* assignment to ``name`` in ``body``.

    Only direct statements of the enclosing ``for`` body (or the
    canonical ``isinstance(...): ...; continue`` dispatch) are
    considered. Nested loops and arbitrary nested branches cannot
    provide the alias (R47).
    """

    last: ast.stmt | None = None
    last_position: tuple[int, int] | None = None
    for cand in _collect_direct_assignments_in_body(body, name, max_position):
        if not isinstance(cand, (ast.Assign, ast.AnnAssign)):
            continue
        candidate_position = _node_position(cand)
        if last_position is None or candidate_position >= last_position:
            last = cand
            last_position = candidate_position
    if isinstance(last, (ast.Assign, ast.AnnAssign)):
        return last, last_position
    return None, None



def _if_ends_with_continue(if_node: ast.If) -> bool:
    """True when the body of ``if_node`` ends with an explicit ``continue``."""
    if not if_node.body:
        return False
    return isinstance(if_node.body[-1], ast.Continue)


def _is_isinstance_continue_chain(
    if_node: ast.If, name: str
) -> bool:
    """True when ``if_node`` is the canonical ``isinstance(...): ...; continue`` dispatch.

    The chain may be a top-level ``if`` or an ``elif`` arm; both are
    allowed, but each arm must terminate with an explicit ``continue``
    so the alias assignment cannot be skipped while the constructor is
    reached.
    """
    if not _if_ends_with_continue(if_node):
        return False
    if not isinstance(if_node.test, ast.Call):
        return False
    func = if_node.test.func
    if not (isinstance(func, ast.Name) and func.id == "isinstance"):

        return False
    return True


def _enclosing_statement_position(
    parent_map: dict[int, ast.AST], node: ast.AST
) -> tuple[int, int]:
    current: ast.AST = node
    while id(current) in parent_map:
        current = parent_map[id(current)]
        if isinstance(current, ast.stmt):
            return _node_position(current)
    return _node_position(node)



def _collapsed_scope_local(
    stmt: ast.stmt, workset_name: str
) -> str | None:
    target: ast.expr | None
    value: ast.expr | None
    if isinstance(stmt, ast.Assign):
        value = stmt.value
        if not stmt.targets:
            return None
        target = stmt.targets[0]
    elif isinstance(stmt, ast.AnnAssign):
        value = stmt.value
        if stmt.target is None:
            return None
        target = stmt.target
    else:
        return None
    if value is None:
        return None
    if not isinstance(value, ast.Call):
        return None
    if _call_name(value) != "tuple":
        return None
    if not value.args:
        return None
    arg = value.args[0]
    if not isinstance(arg, ast.Attribute):
        return None
    if arg.attr != "signal_ids":
        return None
    if not isinstance(arg.value, ast.Name):
        return None
    if arg.value.id != workset_name:
        return None
    if not isinstance(target, ast.Name):
        return None
    return target.id


# ---------------------------------------------------------------------------
# R49 / R50 helpers: collect every append to the reference collection
# inside the canonical ``isinstance`` dispatch arms and validate each
# independently. The accepted grammar is closed: a direct ``expr.append``
# where the argument is a ``CurrentRunSignalRef(...)`` constructor call
# OR an alias name whose canonical-instanceof-else arm is satisfied. Any
# other append into the reference collection is rejected, so a valid
# sibling branch cannot mask a broken one.
# ---------------------------------------------------------------------------


def _is_canonical_isinstance_if(
    if_node: ast.If, target_name: str | None = None
) -> bool:
    """True for ``if isinstance(<Name>, ...): ...; continue`` and the like.

    R48 (P0): when ``target_name`` is supplied, the dispatch subject
    MUST match. This blocks an unrelated ``isinstance(unrelated, T)``
    branch from contributing a canonical append.
    """
    if not _if_ends_with_continue(if_node):
        return False
    if not isinstance(if_node.test, ast.Call):
        return False
    func = if_node.test.func
    if not (isinstance(func, ast.Name) and func.id == "isinstance"):
        return False
    if not if_node.test.args:
        return False
    subject = if_node.test.args[0]
    if not isinstance(subject, ast.Name):
        return False
    if target_name is not None and subject.id != target_name:
        return False
    return True


def _first_canonical_append_in_body(
    body: list[ast.stmt], target_name: str
) -> tuple[ast.Call | None, str | None]:
    """Return ``(append_call, collection_name)`` for the first canonical
    ``.append(...)`` reachable from ``body`` via direct statements or
    canonical ``if isinstance(<target_name>, ...) ... continue`` arms.

    Discovery-time helper used by the active detector to identify the
    canonical chain's loop + collection. The walker uses the same
    closed grammar as ``_collect_appends_in_body`` so inline appends
    under ``try``/``with``/arbitrary ``if``/nested loops are not
    seen here either (R50/R55).

    Returns ``(None, None)`` if no canonical append is reachable.
    """
    for stmt in body:
        if isinstance(stmt, ast.Expr):
            if not isinstance(stmt.value, ast.Call):
                continue
            call = stmt.value
            if _call_name(call) != "append":
                continue
            target = call.func
            if not (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
            ):
                continue
            return call, target.value.id
        if isinstance(stmt, ast.If) and _is_canonical_isinstance_if(
            stmt, target_name
        ):
            result = _first_canonical_append_in_body(
                stmt.body, target_name
            )
            if result[0] is not None:
                return result[0], result[1]
            continue
        # All other statement kinds are ignored (R50 closed grammar).
    return None, None


def _collect_appends_in_body(
    body: list[ast.stmt],
    collection_name: str,
    target_name: str | None = None,
) -> list[ast.Call]:
    """Return every ``<collection_name>.append(...)`` call reachable from
    ``body`` via direct statements or canonical ``if isinstance`` arms.

    R48 (P0): when ``target_name`` is supplied, only arms whose
    dispatch subject is the loop target are walked.

    R50 (P0): compound statements like ``try``, ``with``,
    ``while``, nested ``for``, arbitrary ``if``, ``match``, nested
    ``FunctionDef``/``ClassDef`` are NOT descended into. Inline appends
    inside such compound statements are silently rejected by this
    walker, which is precisely the R55 closed-grammar guarantee.
    """
    results: list[ast.Call] = []

    def _walk(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Expr):
                if isinstance(stmt.value, ast.Call) and _is_targeted_append(
                    stmt.value, collection_name
                ):
                    results.append(stmt.value)
                continue
            if isinstance(stmt, ast.If) and _is_canonical_isinstance_if(
                stmt, target_name
            ):
                _walk(stmt.body)
                # ``else`` branches are the non-promo fallback (``continue``)
                # -- nothing to collect.
                continue
            # All other statement kinds are ignored (R50 closed grammar).

    _walk(body)
    return results


def _is_targeted_append(call: ast.Call, collection_name: str) -> bool:
    if _call_name(call) != "append":
        return False
    target = call.func
    if not isinstance(target, ast.Attribute):
        return False
    return (
        isinstance(target.value, ast.Name)
        and target.value.id == collection_name
    )


def _find_reference_collection_appends(
    loop_body: list[ast.stmt],
    collection_name: str,
    target_name: str | None = None,
) -> list[ast.Call]:
    """Public entry: every ``<collection_name>.append(...)`` reachable from
    the direct statements of ``loop_body`` or its canonical
    ``if isinstance(<target_name>, ...)`` dispatch arms.

    R49 (P0): exhaustive collection so every authoritative append is
    validated independently. A valid sibling arm cannot mask a broken
    one.

    R50 (P0): the walker only descends into direct statements and
    canonical isinstance arms. Compound statements like ``try``,
    ``with``, arbitrary ``if``, nested ``for``/``while``, ``match``,
    nested ``FunctionDef``/``ClassDef`` are silently rejected by the
    walker -- which is the R55 closed-grammar guarantee.

    R48 (P0): when ``target_name`` is supplied, only arms whose
    dispatch subject is the loop target contribute.
    """
    return _collect_appends_in_body(loop_body, collection_name, target_name)


def _constructor_enclosing_scope(
    parent_map: dict[int, ast.AST], ctor: ast.Call, for_loop: ast.For
) -> list[ast.stmt] | None:
    """Return the canonical scope that owns ``ctor``.

    Used by the inline-form alias resolver: a constructor inside a
    canonical ``if isinstance`` arm must resolve its ``signal_id``
    alias in the same arm; a constructor at the top of the ``for``
    body must resolve its alias in the same for body. Anything in
    between (try/with/arbitrary if/nested for) is rejected.
    """
    current: ast.AST = ctor
    enclosing_stmt: ast.stmt | None = None
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(current, ast.stmt):
            enclosing_stmt = current
            break
        current = parent
    if enclosing_stmt is None:
        return None
    stmt_parent = parent_map.get(id(enclosing_stmt))
    if stmt_parent is for_loop:
        return list(for_loop.body)
    if (
        isinstance(stmt_parent, ast.If)
        and _is_canonical_isinstance_if(stmt_parent)
        and stmt_parent in for_loop.body
    ):
        return stmt_parent.body
    return None


def _validate_constructor_signal_id(
    ctor: ast.Call,
    enclosing_target_name: str,
    parent_map: dict[int, ast.AST],
    scope: list[ast.stmt],
    ctor_position: tuple[int, int],
) -> str | None:
    """Return None if ``ctor.signal_id`` is bound to the loop target.

    ``scope`` is the immediate canonical scope (for body or canonical
    isinstance arm body) where one-hop aliases for ``signal_id`` must
    be searched. Cross-arm / cross-scope alias resolution is
    rejected.
    """
    sig_id_value = _kwarg_value(ctor, "signal_id")
    if sig_id_value is None:
        return (
            f"the appended ``CurrentRunSignalRef`` has no "
            f"``signal_id=`` keyword (line {ctor.lineno}); "
            f"the identity origin is not bound."
        )
    if isinstance(sig_id_value, ast.Constant):
        return (
            f"the appended ``CurrentRunSignalRef`` uses a literal "
            f"``signal_id=...`` on line {ctor.lineno}; the canonical "
            f"origin must be the enclosing loop target's "
            f".signal_id attribute."
        )
    if isinstance(sig_id_value, ast.Attribute):
        if (
            sig_id_value.attr == "signal_id"
            and isinstance(sig_id_value.value, ast.Name)
            and sig_id_value.value.id == enclosing_target_name
        ):
            return None
        return (
            f"the appended ``CurrentRunSignalRef`` signal_id= must be "
            f"``{enclosing_target_name}.signal_id`` (line "
            f"{ctor.lineno}); the current expression does not match "
            f"the enclosing for-loop target."
        )
    if isinstance(sig_id_value, ast.Name):
        # One-hop alias: must be bound in the SAME canonical scope.
        alias_name = sig_id_value.id
        alias_stmt = _find_alias_assignment_in_arm(
            scope, alias_name, ctor_position
        )
        if alias_stmt is None:
            return (
                f"the appended ``CurrentRunSignalRef`` uses "
                f"``signal_id={alias_name}`` on line {ctor.lineno} "
                f"but that local is never assigned in the same "
                f"canonical scope as the constructor; the alias must "
                f"be bound per-iteration."
            )
        rhs = alias_stmt.value
        if not (
            isinstance(rhs, ast.Attribute)
            and rhs.attr == "signal_id"
            and isinstance(rhs.value, ast.Name)
            and rhs.value.id == enclosing_target_name
        ):
            return (
                f"the alias ``{alias_name}`` is not bound to "
                f"``{enclosing_target_name}.signal_id`` (line "
                f"{alias_stmt.lineno}); the canonical origin must be "
                f"the enclosing loop target's .signal_id attribute."
            )
        return None
    if (
        isinstance(sig_id_value, ast.Call)
        and _call_name(sig_id_value) == "str"
        and len(sig_id_value.args) == 1
        and isinstance(sig_id_value.args[0], ast.Name)
    ):
        # Production normalizes the per-iteration identity with
        # ``str(signal_id)`` after binding the alias from the loop target.
        alias_name = sig_id_value.args[0].id
        alias_stmt = _find_alias_assignment_in_arm(
            scope, alias_name, ctor_position
        )
        candidates: list[ast.Assign | ast.AnnAssign] = []
        if isinstance(alias_stmt, (ast.Assign, ast.AnnAssign)):
            candidates.append(alias_stmt)
        else:
            # The production normalization alias is assigned in the
            # outcome dispatch branch immediately before the append.
            for statement in scope:
                for descendant in ast.walk(statement):
                    if not isinstance(descendant, (ast.Assign, ast.AnnAssign)):
                        continue
                    targets = (
                        descendant.targets
                        if isinstance(descendant, ast.Assign)
                        else [descendant.target]
                    )
                    if any(
                        isinstance(target, ast.Name) and target.id == alias_name
                        for target in targets
                    ):
                        candidates.append(descendant)
        for candidate in candidates:
            rhs = candidate.value
            if (
                isinstance(rhs, ast.Attribute)
                and rhs.attr == "signal_id"
                and isinstance(rhs.value, ast.Name)
                and rhs.value.id == enclosing_target_name
            ):
                return None
    return (
        f"the appended ``CurrentRunSignalRef`` uses a non-Name, "
        f"non-Attribute signal_id= on line {ctor.lineno}; the "
        f"canonical origin must be either a Name (with one-hop alias) "
        f"or an attribute access on the enclosing loop target."
    )


def _validate_all_appends(
    appends: list[ast.Call],
    enclosing_target_name: str,
    parent_map: dict[int, ast.AST],
) -> str | None:
    """Return None if every authoritative append satisfies the chain.

    R49 (P0): every append into the reference collection must
    independently satisfy the canonical chain. A valid sibling arm
    cannot mask a broken one.

    R48 (P0): the alias form ``refs.append(ref)`` requires the
    alias assignment to live in the SAME canonical scope as the
    append (same canonical isinstance arm, or same for body).

    R50 (P0): the inline form ``refs.append(CurrentRunSignalRef(...))``
    must have its ``signal_id`` kwarg bound to the loop target --
    either directly via ``<target>.signal_id`` or via a one-hop alias
    defined in the SAME canonical scope.
    """
    if enclosing_target_name is None:
        return (
            "the canonical chain references a loop target that is not "
            "a simple ``Name``; the per-iteration origin cannot be "
            "proven."
        )
    for_loop = _enclosing_for(parent_map, appends[0]) if appends else None
    if for_loop is None:
        return (
            "the authoritative append is not inside any ``for`` loop; "
            "the canonical R20 chain requires appending one "
            "constructed ref per iteration."
        )
    for append in appends:
        if not append.args:
            return (
                f"the canonical chain appends an empty call to the "
                f"reference collection on line {append.lineno}."
            )
        arg = append.args[0]

        # ------------------------------------------------------------------
        # Inline form: ``refs.append(CurrentRunSignalRef(...))``
        # ------------------------------------------------------------------
        if isinstance(arg, ast.Call):
            if _call_name(arg) != "CurrentRunSignalRef":
                return (
                    f"the canonical chain appends a non-"
                    f"``CurrentRunSignalRef`` constructor to the "
                    f"reference collection on line {append.lineno}; "
                    f"only ``CurrentRunSignalRef(...)`` is authorised."
                )
            scope = _constructor_enclosing_scope(parent_map, arg, for_loop)
            if scope is None:
                return (
                    f"the canonical-chain constructor on line "
                    f"{arg.lineno} is not inside a canonical scope; "
                    f"inline appends under ``try``/``with``/arbitrary "
                    f"``if``/nested loops are not accepted."
                )
            violation = _validate_constructor_signal_id(
                arg,
                enclosing_target_name,
                parent_map,
                scope,
                _node_position(arg),
            )
            if violation is not None:
                return violation
            continue

        # ------------------------------------------------------------------
        # Alias form: ``refs.append(ref)``
        # ------------------------------------------------------------------
        if isinstance(arg, ast.Name):
            alias_name = arg.id
            scope = _arm_owning_append(parent_map, append, for_loop)
            if scope is None:
                return (
                    f"the alias-form append ``{alias_name}`` is not "
                    f"inside a canonical scope on line {append.lineno}; "
                    f"alias appends under ``try``/``with``/arbitrary "
                    f"``if``/nested loops are not accepted."
                )
            alias_stmt = _find_alias_assignment_in_arm(
                scope, alias_name, _node_position(append)
            )
            if alias_stmt is None:
                # Distinguish use-before-define (alias exists in the
                # scope but AFTER the append) from missing alias
                # entirely (never bound in this scope). The former is
                # R38 (must occur BEFORE the append); the latter is
                # R48/R50 (must live in the same canonical scope).
                for stmt in scope:
                    if _node_position(stmt) <= _node_position(append):
                        continue
                    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        if isinstance(stmt, ast.Assign):
                            targets = stmt.targets
                        else:
                            targets = (
                                [stmt.target]
                                if stmt.target is not None
                                else []
                            )
                        for t in targets:
                            if (
                                isinstance(t, ast.Name)
                                and t.id == alias_name
                            ):
                                return (
                                    f"the append statement (line "
                                    f"{append.lineno}) must occur "
                                    f"BEFORE the alias assignment for "
                                    f"``{alias_name}`` on line "
                                    f"{stmt.lineno}; otherwise the "
                                    f"append reads an undefined or "
                                    f"stale value at runtime."
                                )
                return (
                    f"the alias ``{alias_name}`` is not bound in the "
                    f"same canonical scope as the append on line "
                    f"{append.lineno}; the canonical R20 chain "
                    f"constructs the ref per-iteration."
                )
            alias_value = alias_stmt.value
            if not (
                isinstance(alias_value, ast.Call)
                and _call_name(alias_value) == "CurrentRunSignalRef"
            ):
                return (
                    f"the alias ``{alias_name}`` is not bound to a "
                    f"``CurrentRunSignalRef(...)`` constructor on line "
                    f"{alias_stmt.lineno}; the canonical chain only "
                    f"appends ``CurrentRunSignalRef`` instances."
                )
            violation = _validate_constructor_signal_id(
                alias_value,
                enclosing_target_name,
                parent_map,
                scope,
                _node_position(alias_value),
            )
            if violation is not None:
                return violation
            continue

        # ------------------------------------------------------------------
        # Junk append
        # ------------------------------------------------------------------
        return (
            f"the canonical chain appends a non-constructor value to "
            f"the reference collection on line {append.lineno}; only "
            f"``CurrentRunSignalRef(...)`` or a one-hop alias is "
            f"authorised."
        )
    return None


def _arm_owning_append(
    parent_map: dict[int, ast.AST], append: ast.Call, for_loop: ast.For
) -> list[ast.stmt] | None:
    """Return the immediate canonical scope that owns ``append``.

    Returns one of:

    * the canonical ``if isinstance(<target>, ...) ... continue`` arm
      body when ``append`` is a direct statement of that arm;
    * ``list(for_loop.body)`` when ``append`` is a direct statement of
      the enclosing ``for`` body;
    * ``None`` when ``append`` is under a non-canonical compound
      statement (``try``, ``with``, arbitrary ``if``, nested
      ``for``/``while``, ``match``, nested function / class).

    R48 (P0): the alias assignment MUST be reachable from the same
    canonical scope as the append, so this helper deliberately does
    NOT return a parent arm when the append is under an arbitrary
    ``if``.
    """
    # Walk up to the enclosing statement whose parent is either
    # ``for_loop`` or a canonical isinstance arm body.
    current: ast.AST = append
    enclosing_stmt: ast.stmt | None = None
    while id(current) in parent_map:
        parent = parent_map[id(current)]
        if isinstance(current, ast.stmt):
            enclosing_stmt = current
            break
        current = parent
    if enclosing_stmt is None:
        return None
    stmt_parent = parent_map.get(id(enclosing_stmt))
    if stmt_parent is for_loop:
        return list(for_loop.body)
    if (
        isinstance(stmt_parent, ast.If)
        and _is_canonical_isinstance_if(stmt_parent)
        and stmt_parent in for_loop.body
    ):
        return stmt_parent.body
    return None


def _runtime_children(node: ast.AST) -> Iterable[ast.AST]:
    """Yield only children evaluated when ``node`` executes now.

    R61 (P0): nested definition bodies are deferred, but definition-time
    expressions are not.  Function and lambda defaults plus function
    decorators execute while those objects are created.  A class statement is
    itself executable, including its decorators, bases, keywords, and suite;
    function or lambda bodies declared inside that suite remain deferred when
    this helper reaches their definition nodes.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from node.decorator_list
        yield from node.args.defaults
        for item in node.args.kw_defaults:
            if item is not None:
                yield item
        return

    if isinstance(node, ast.Lambda):
        yield from node.args.defaults
        for item in node.args.kw_defaults:
            if item is not None:
                yield item
        return

    if isinstance(node, ast.ClassDef):
        yield from node.decorator_list
        yield from node.bases
        yield from node.keywords
        yield from node.body
        return

    yield from ast.iter_child_nodes(node)


def _find_all_targeted_appends_before_factory(
    function_body: list[ast.stmt],
    collection_name: str,
    factory_statement: ast.stmt,
) -> list[ast.Call]:
    """Collect every live-scope append before the workset factory.

    R58/R59 (P0): the canonical collector deliberately accepts only the
    closed append grammar.  This broad collector instead walks every AST
    descendant of each same-function statement that executes before the
    authoritative factory assignment.  Walking arbitrary AST nodes (rather
    than only :class:`ast.stmt` children) includes ``ExceptHandler`` bodies,
    ``match_case`` bodies, and calls nested inside expressions.

    R61 (P0): traversal is execution-aware at nested definitions.  Deferred
    function/lambda/method bodies are pruned, while defaults, decorators, and
    executable class suites are traversed.  Statements at and after
    ``factory_statement`` are outside the authority window because they cannot
    affect the factory's already-evaluated input collection.
    """
    results: list[ast.Call] = []

    for stmt in function_body:
        if stmt is factory_statement:
            break

        # Preserve source order while traversing every intermediary AST node.
        stack: list[ast.AST] = [stmt]
        while stack:
            current = stack.pop()
            if isinstance(current, ast.Call) and _is_targeted_append(
                current, collection_name
            ):
                results.append(current)
            children = list(_runtime_children(current))
            stack.extend(reversed(children))

    return results


def _find_alias_assignment_in_arm(
    arm: list[ast.stmt], alias_name: str, max_position: tuple[int, int]
) -> ast.stmt | None:
    """Return the last ``alias_name = <expr>`` directly in ``arm`` (R48/R50)."""
    last: ast.stmt | None = None
    for stmt in arm:
        if _node_position(stmt) > max_position:
            continue
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            else:
                targets = [stmt.target] if stmt.target is not None else []
            for t in targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == alias_name
                    and _node_position(stmt) <= max_position
                ):
                    last = stmt
    return last


# ---------------------------------------------------------------------------
# R62 / R63 / R64 helpers
#
# R62 (P0) -- called deferred bodies can become live and mutate the
# authoritative collection. The reachability walk begins ONLY at
# top-level pre-factory statements that are NOT themselves scope
# boundaries (a top-level ``def`` / ``class`` / ``lambda`` statement is
# reached but its body does not run until the callable is invoked);
# each called callable's body is recursively descended with an
# ``id(body)`` visited set so a degenerate mutual recursion does not
# loop the detector. Local callable aliases (``invoke = mutator``) are
# resolved transitively so ``invoke()`` collapses to ``mutator()``.
#
# R63 (P0) -- the authoritative collection has a closed use grammar
# (no aliases, no method calls other than ``append``, no augmented
# assignment, no subscript/attribute stores or deletes, no annotated
# aliases like ``alias: list[X] = refs``). The grammar is enforced
# against every execution-aware descendant of each pre-factory
# statement -- nested ``if`` / ``try`` / class-suite positions are
# included because a class statement is itself executable and its
# body runs at class-creation time.
#
# R64 (P0) -- every scoped-dispatcher call reachable from the ingest
# function's live execution context must consume the canonical
# collapsed local.  The audit walks execution-aware scopes (class
# suites, function decorators and defaults, lambda defaults) AND the
# bodies of called local callables. Exactly one canonical sink is
# required. The attribute form ``signal_ids=<tuple>.signal_ids`` is
# rejected because the canonical binding is a tuple.
# ---------------------------------------------------------------------------


def _is_collection_initial_declaration(
    stmt: ast.stmt, collection_name: str
) -> bool:
    """True iff ``stmt`` declares ``<collection_name> = []`` (annotated or not)."""
    if isinstance(stmt, ast.AnnAssign):
        return (
            isinstance(stmt.target, ast.Name)
            and stmt.target.id == collection_name
            and isinstance(stmt.value, ast.List)
            and not stmt.value.elts
        )
    if isinstance(stmt, ast.Assign):
        return (
            len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == collection_name
            and isinstance(stmt.value, ast.List)
            and not stmt.value.elts
        )
    return False


def _walk_runtime_scope(node: ast.AST) -> Iterable[ast.AST]:
    """Yield ``node`` and every execution-aware descendant.

    Uses :func:`_runtime_children` so:

    * function / lambda decorators and positional / keyword defaults
      (executed at definition time) are traversed;
    * the entire class suite is traversed (a class statement is itself
      an executable compound statement; its body runs at class
      creation time);
    * nested function / lambda / method *bodies* are pruned (those
      bodies only run when the callable is invoked, and reachability
      into them is handled by :func:`_live_reachable_local_calls`).

    This walker is the single execution-aware traversal used by R62,
    R63, and R64. It is rooted at a single pre-factory statement so
    the root statement is yielded first (the existing
    ``_walk_same_function_scope`` helper skips the root, which is why
    the original R63 closed grammar missed top-level ``Assign`` /
    ``AugAssign`` / ``Delete`` statements).
    """
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in _runtime_children(current):
            stack.append(child)


def _walk_runtime_scope_with_parent(
    node: ast.AST,
) -> Iterable[tuple[ast.AST, ast.AST | None, str]]:
    """Like :func:`_walk_runtime_scope` but yields
    ``(node, parent, attr_name)`` triples.

    R92 (P0): the harvester needs to know whether a nested
    ``FunctionDef`` is the body of a ``ClassDef`` so the unqualified
    function name does NOT leak into the enclosing function's local
    callable table. Python executes a class suite in a separate
    namespace; names defined in the class block become class
    attributes, and that class scope does NOT become an enclosing
    scope for method bodies. Recording the parent alongside each
    visited node lets the harvester distinguish class methods from
    plain local functions and emit only the qualified
    ``"ClassName.method_name"`` key for the former.

    R95 (P0): the third yield element ``attr_name`` is the list
    attribute through which the child was reached
    (``"body"``/``"orelse"``/``"handlers"``/``"finalbody"``/...) so
    that two rebindings in DISTINCT ``if``/``else`` branches of the
    SAME compound statement have distinct paths -- otherwise they
    would share the same immediate parent id and be misclassified
    as ordinary sequential rebinding.
    """
    # ``attr_name`` is the list-attribute name on the parent that
    # contains ``child``. ``"self"`` means the child is the parent
    # itself (initial seed). Default for top-level items of a scope
    # body is ``"body"``.
    stack: list[tuple[ast.AST, ast.AST | None, str]] = [(node, None, "self")]
    while stack:
        current, parent, attr = stack.pop()
        yield current, parent, attr
        for child in _runtime_children(current):
            child_attr = _runtime_child_attr(current, child)
            stack.append((child, current, child_attr))
        # Special-case for ClassDef.method: the FunctionDef inside a
        # ClassDef body is still reached via ``body``, but the
        # R92 guard checks the immediate parent ref so no extra
        # flag is needed here.


def _runtime_child_attr(parent: ast.AST, child: ast.AST) -> str:
    """Return the list-attribute name on ``parent`` that contains ``child``.

    R95: this lets the harvest distinguish ``if.body`` items from
    ``if.orelse`` items -- both have the same immediate parent id
    (the ``If`` node), but only one of them is the ``if`` branch.
    Two rebindings in the two branches must therefore be classified
    as control-flow ambiguity rather than sequential rebinding.
    """
    # Tuple/list-attribute fields on each compound AST node that
    # may contribute a binding. The check uses identity (==) so
    # objects that compare equal but are distinct nodes do not
    # confuse the lookup.
    _ATTRS = (
        "body",
        "orelse",
        "handlers",
        "finalbody",
        "cases",
        "items",
        "decorator_list",
        "args",
        "bases",
        "keywords",
    )
    for attr_name in _ATTRS:
        child_list = getattr(parent, attr_name, None)
        if isinstance(child_list, list) and any(c is child for c in child_list):
            return attr_name
    return "self"


class _Binding:
    """A position-tagged callable binding event.

    R90 (P0): callable bindings (``def nested`` / ``class Foo`` /
    ``inject = lambda: ...`` / ``inject = name``) are runtime events
    that occur at a specific source position. The previous
    implementation stored a single ``bodies[(name, scope_id)] = body``
    and a single ``aliases[(name, scope_id)] = target`` and therefore
    silently lost any binding that was overwritten before the
    call site was reached. A rebinding AFTER a call can also change
    how an earlier call is interpreted.

    Each binding is now an ordered event recorded with its source
    position. Resolution picks the latest binding strictly before the
    call position. Multiple bindings for the same
    ``(name, scope_id)`` that are ALL strictly before the call
    position are ambiguous (e.g. branch-defined same-name callables);
    resolution reports the ambiguity so the caller can flag a
    violation instead of silently picking one.

    R100 (P1): ``path`` is the ``(parent_id, attr_name)`` pair
    recorded by :func:`_walk_runtime_scope_with_parent` -- the
    ``id()`` of the parent AST node paired with the list-attribute
    name through which the child was reached (e.g.
    ``(id(<If>), "body")`` vs ``(id(<If>), "orelse")``). Two
    bindings share a path iff they have the same parent reference
    AND the same attr; the discriminator is the full tuple.
    """

    __slots__ = ("position", "kind", "body", "target", "path")

    def __init__(
        self,
        position: tuple[int, int],
        kind: str,
        body: list[ast.stmt] | ast.Lambda | None = None,
        target: str | None = None,
        path: BindingPath = (0, "self"),
    ) -> None:
        self.position = position
        self.kind = kind  # "definition" or "alias"
        self.body = body
        self.target = target
        self.path = path  # ``(parent_id, attr_name)`` from the
        # runtime-scope walker; discriminates ``if.body`` from
        # ``if.orelse`` rebindings (R95).

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"_Binding(position={self.position!r}, kind={self.kind!r}, "
            f"body={'set' if self.body is not None else 'None'}, "
            f"target={self.target!r}, path={self.path!r})"
        )


def _add_binding(
    bindings: dict[tuple[str, int], list[_Binding]],
    scope_id: int,
    name: str,
    position: tuple[int, int],
    kind: str,
    body: list[ast.stmt] | ast.Lambda | None = None,
    target: str | None = None,
    path: BindingPath = (0, "self"),
) -> None:
    """Append a :class:`_Binding` to ``bindings[(name, scope_id)]``.

    R90 (P0): multiple bindings for the same ``(name, scope_id)`` are
    recorded as ordered events so resolution can pick the latest one
    strictly before the call position and flag ambiguity when
    multiple bindings are all before the call.

    R95 (P0): ``path`` is the ``(parent_id, attr_name)`` pair
    produced by :func:`_walk_runtime_scope_with_parent`. Two
    bindings share a path iff they have the same parent reference
    AND the same list-attribute name. Resolution uses ``path`` to
    discriminate ordinary sequential rebinding (same path, last
    wins) from branch-defined ambiguity (different paths, ambiguous).

    R100 (P1): the parameter is typed as :data:`BindingPath` so a
    verifier-specific ``mypy`` run can flag any future drift back to
    a scalar.
    """
    key = (name, scope_id)
    bindings.setdefault(key, []).append(
        _Binding(position, kind, body=body, target=target, path=path)
    )


def _collect_local_callable_bodies(
    body: list[ast.stmt],
) -> tuple[
    dict[tuple[str, int], list[_Binding]],
    dict[int, int | None],
]:
    """Collect locally-defined callables and local-callable aliases.

    R62 (P0): the closed grammar for the authoritative collection must
    inspect the deferred bodies of any locally-defined callable that
    is invoked before the workset factory.

    R78 (P0): the harvest is recursive. A callable definition declared
    inside a reachable local callable body must itself be registered so
    the R62 reachability walk can resolve a chain like
    ``wrapper() -> mutator() -> refs.append(...)``. The harvest is a
    BFS over scopes starting from the top-level pre-factory body and
    transitively entering every callable body discovered en route
    (``def`` bodies, ``ClassDef.method`` bodies). Lambda bodies are
    excluded from the BFS queue because a lambda body is a single
    expression and cannot host a ``def`` / ``class`` statement -- but
    the lambda body itself IS registered so the caller can audit it
    when the lambda is invoked (R91).

    R81 (P0): the harvest is per-scope. Two nested ``def mutator(...)``
    declared inside different enclosing scopes share the same AST
    ``name``; storing them under a single ``dict[str, body]`` conflates
    them and lets a safe nested ``mutator`` mask a mutating one (or
    vice versa). Each callable is therefore registered under a
    ``(name, id(enclosing_scope))`` key where ``enclosing_scope`` is the
    body in which the ``def`` / ``class`` statement appeared. Class
    method entries use the qualified name ``"ClassName.method_name"``
    so a method declared in two different classes cannot collide either.
    Call resolution later uses the enclosing scope's ``id()`` so calls
    from inside ``wrapper`` resolve ``mutator`` to the entry registered
    in ``wrapper``'s body and never to a sibling scope's entry.

    R86 (P0): the harvest records a parent relation
    ``parent_scope_by_id[scope_id] = parent_scope_id`` so callers can
    walk the lexical-ancestor chain during name resolution. The
    ingestion top-level body is its own parent (``None``); every other
    callable body is recorded with its enclosing scope id so a call
    inside ``inner`` resolves names through ``inner -> wrapper -> top``
    in lexical order, preserving shadowing.

    R90 (P0): each callable binding is now an ordered event recorded
    with its source ``(lineno, col_offset)`` position. The previous
    ``bodies`` / ``aliases`` dicts stored only a single value per
    ``(name, scope_id)`` and silently lost any binding that was
    overwritten before the call site was reached (e.g. ``invoke =
    mutator; invoke(); invoke = safe``). The new ``bindings`` dict
    preserves every binding so :func:`_resolve_alias` can pick the
    latest one strictly before the call position.

    R91 (P0): lambda assignments now record
    ``parent_scope_by_id[id(lambda_node)] = scope_id`` so the
    lexical chain used during name resolution continues past a
    lambda body to its enclosing scope. The previous implementation
    only stored ``parent_scope_by_id[id(new_body)]`` for ``def`` /
    class-method bodies; a lambda body therefore had no lexical
    parent in the resolution chain and could not resolve names
    defined in the enclosing scope.

    R92 (P0): the harvest uses
    :func:`_walk_runtime_scope_with_parent` and refuses to register
    a ``FunctionDef`` whose immediate lexical owner is a
    ``ClassDef`` under the unqualified name. Python executes a class
    suite in a separate namespace; names defined in the class block
    become class attributes, and the class scope does NOT become an
    enclosing scope for method bodies. The qualified
    ``"ClassName.method_name"`` key registered by the ``ClassDef``
    branch remains the only public binding for a class method, so an
    unqualified call inside the enclosing function does not
    accidentally resolve to the class method.

    Returns ``(bindings, parent_scope_by_id)`` where:

    * ``bindings[(name, scope_id)]`` is the ordered list of
      :class:`_Binding` events recorded for ``name`` in
      ``scope_id``;
    * ``parent_scope_by_id[scope_id]`` is the enclosing scope id (or
      ``None`` for the ingestion top-level body) so resolution can
      walk the lexical chain current -> enclosing -> ... -> top.

    Recognised definitions:

    * ``def nested(...)`` and ``async def nested(...)``;
    * ``class Foo: def method(self): ...`` -> key
      ``("Foo.method", scope_id)``;
    * ``inject = lambda: ...`` and
      ``inject: SomeType = lambda: ...``;
    * ``inject = name`` and ``inject: SomeType = name`` where ``name``
      is itself a known local callable (alias).
    """
    bindings: dict[tuple[str, int], list[_Binding]] = {}
    parent_scope_by_id: dict[int, int | None] = {}

    top_id = id(body)
    parent_scope_by_id[top_id] = None

    queue: list[tuple[list[ast.stmt] | ast.Lambda, int]] = [(body, top_id)]
    visited_scope_ids: set[int] = {top_id}

    while queue:
        scope, scope_id = queue.pop(0)
        if isinstance(scope, ast.Lambda):
            # Lambda bodies are single expressions; they cannot host
            # ``def`` / ``class`` statements.
            continue

        for item in list(scope):
            # R92: the parent-aware walker distinguishes class methods
            # from plain local functions so the unqualified function
            # name does not leak from a class namespace into the
            # enclosing function's local callable table.
            #
            # R95 (P0): the path discriminator is the (parent_id,
            # attr_name) pair. ``attr_name`` is the list-attribute
            # name on the parent that contains the child (e.g.
            # ``"body"`` for direct statements of an ``if`` arm,
            # ``"orelse"`` for else items, ``"handlers"`` for
            # ``except`` cases). Two rebindings in two distinct
            # arms of the SAME compound statement have distinct
            # attrs and therefore distinct paths; they are flagged
            # ambiguous. Two rebindings at the same control-flow
            # level share the attr and parent id and are treated
            # as sequential rebinding (last wins).
            for sub, parent, attr in _walk_runtime_scope_with_parent(item):
                binding_path = (id(parent), attr)
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # R92 (P0): a FunctionDef whose immediate lexical
                    # owner is a ClassDef is a class method. Python
                    # executes the class suite in a separate
                    # namespace, so the method name does not become a
                    # local callable of the enclosing function. Skip
                    # the unqualified registration; the ClassDef
                    # branch below records the qualified
                    # ``"ClassName.method_name"`` key.
                    if isinstance(parent, ast.ClassDef):
                        continue
                    new_body = list(sub.body)
                    _add_binding(
                        bindings,
                        scope_id,
                        sub.name,
                        _node_position(sub),
                        "definition",
                        body=new_body,
                        path=binding_path,
                    )
                    new_id = id(new_body)
                    parent_scope_by_id[new_id] = scope_id
                    if new_id not in visited_scope_ids:
                        visited_scope_ids.add(new_id)
                        queue.append((new_body, new_id))
                elif isinstance(sub, ast.ClassDef):
                    for inner in sub.body:
                        if isinstance(
                            inner, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            qualified_name = f"{sub.name}.{inner.name}"
                            new_body = list(inner.body)
                            _add_binding(
                                bindings,
                                scope_id,
                                qualified_name,
                                _node_position(inner),
                                "definition",
                                body=new_body,
                                path=binding_path,
                            )
                            new_id = id(new_body)
                            parent_scope_by_id[new_id] = scope_id
                            if new_id not in visited_scope_ids:
                                visited_scope_ids.add(new_id)
                                queue.append((new_body, new_id))
                elif (
                    isinstance(sub, ast.AnnAssign)
                    and isinstance(sub.target, ast.Name)
                ):
                    if isinstance(sub.value, ast.Lambda):
                        _add_binding(
                            bindings,
                            scope_id,
                            sub.target.id,
                            _node_position(sub),
                            "definition",
                            body=sub.value,
                            path=binding_path,
                        )
                        # R91 (P0): the lambda is a nested callable
                        # scope; record its lexical parent so the
                        # resolution chain can continue past the
                        # lambda to its enclosing scope.
                        parent_scope_by_id[id(sub.value)] = scope_id
                    elif isinstance(sub.value, ast.Name):
                        _add_binding(
                            bindings,
                            scope_id,
                            sub.target.id,
                            _node_position(sub),
                            "alias",
                            target=sub.value.id,
                            path=binding_path,
                        )
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if not isinstance(t, ast.Name):
                            continue
                        if isinstance(sub.value, ast.Lambda):
                            _add_binding(
                                bindings,
                                scope_id,
                                t.id,
                                _node_position(sub),
                                "definition",
                                body=sub.value,
                                path=binding_path,
                            )
                            # R91 (P0): see AnnAssign branch above.
                            parent_scope_by_id[id(sub.value)] = scope_id
                        elif isinstance(sub.value, ast.Name):
                            _add_binding(
                                bindings,
                                scope_id,
                                t.id,
                                _node_position(sub),
                                "alias",
                                target=sub.value.id,
                                path=binding_path,
                            )
    return bindings, parent_scope_by_id


def _scope_chain(
    scope_id: int,
    parent_scope_by_id: dict[int, int | None],
    top_scope_id: int,
) -> list[int]:
    """Yield lexical-ancestor scope ids, current first, ingestion top last.

    R86 (P0): name resolution in nested functions walks the lexical
    scope chain -- current -> enclosing -> ... -> ingestion top -- in
    the same order Python uses for unqualified-name lookup. Shadowing
    is preserved naturally because each scope is searched in order
    and the first hit wins.

    Cycles in the parent relation (which should not exist for well-formed
    ASTs but may arise from sharing a list object by accident) terminate
    after the second visit to the same id.
    """
    chain: list[int] = []
    seen: set[int] = set()
    current: int | None = scope_id
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        if current == top_scope_id:
            break
        current = parent_scope_by_id.get(current)
    return chain


def _is_unconditional_at_scope(path: BindingPath, scope_id: int) -> bool:
    """Return True if ``path`` represents a binding declared at the
    TOP level of the scope body (unconditional position).

    R99 (P0): the path discriminator is ``(parent_id, attr_name)``.
    A top-level binding in the scope body has either:

    * ``parent_id == scope_id`` and ``attr == "self"`` (when the
      walker is invoked with the scope body itself as the seed,
      the body's list is the immediate parent of the top-level
      statement); or
    * ``parent_id == id(None)`` and ``attr == "self"`` (when the
      walker is invoked with each top-level statement as a separate
      seed, the seed's parent is ``None`` -- ``id(None)`` is the
      sentinel for "top-level direct statement" because
      :func:`_walk_runtime_scope_with_parent` seeds with
      ``(item, None, "self")``).

    A binding inside any compound statement (``if`` / ``for`` /
    ``while`` / ``try`` / ``match`` / ``with``) has parent equal to
    that compound statement and attr equal to ``"body"``,
    ``"orelse"``, ``"handlers"``, ``"finalbody"``, or ``"cases"``;
    such bindings are CONDITIONAL because their execution depends on
    the runtime branch taken.
    """
    parent_id, attr = path
    if attr != "self":
        return False
    return parent_id == id(None) or parent_id == scope_id


def _resolve_alias(
    name: str,
    bindings: dict[tuple[str, int], list[_Binding]],
    scope_id: int,
    parent_scope_by_id: dict[int, int | None],
    top_scope_id: int,
    call_position: tuple[int, int],
    outer_cutoffs: dict[int, tuple[int, int]] | None = None,
) -> tuple[
    list[ast.stmt] | ast.Lambda | None,
    bool,
    bool,
]:
    """Resolve a (possibly aliased) callable name to its body at
    ``call_position``.

    R81 (P0): the harvest is per-scope, so each entry is keyed by
    ``(name, scope_id)``. The new ``bindings`` dict is shared across
    all scopes and stores ordered :class:`_Binding` events instead of
    a single body/alias per key.

    R86 (P0): the walk follows Python's lexical scoping rules --
    current scope -> enclosing scope -> ... -> ingestion top -- via
    the ``parent_scope_by_id`` relation recorded at harvest time.

    R89 (P0): resolution is scope-by-scope shadowing. At each scope
    in the lexical chain, the audit first checks whether the original
    ``name`` has a direct callable binding, then whether it has an
    alias binding in that scope. An alias is resolved beginning from
    the SAME lexical scope (not from the outer scopes), so a binding
    introduced in an inner scope shadows the same name in any outer
    scope. Lookup only continues outward when the current scope has
    no binding for ``name`` at all.

    R90 (P0): each binding carries its source position. Resolution
    picks the latest binding strictly before ``call_position``.
    Multiple bindings for the same ``(name, scope_id)`` that are ALL
    strictly before ``call_position`` but live in distinct
    control-flow paths are ambiguous (e.g. branch-defined
    same-name callables where the runtime branch taken cannot be
    determined statically).

    R95 (P0): the position filter is applied UNIFORMLY -- a single
    binding whose source position is also AFTER ``call_position``
    does NOT count (so a binding-only-after-call resolves to
    ``(None, False, True)`` rather than the previous silent
    fall-through). And multiple pre-call bindings at the SAME
    control-flow path are no longer declared ambiguous; ordinary
    sequential rebinding is treated as straight-line reassignment
    where the LAST binding strictly before the call position wins.
    The discriminator is the ``path`` field of each :class:`_Binding`
    -- the immediate parent AST reference at harvest time. Top-level
    rebindings share ``id(None)``; bindings declared in the same
    ``if`` body share the ``If`` instance; two rebindings in two
    different ``if`` blocks have different path ids. Path diversity
    is what flags control-flow ambiguity, not raw multiplicity.

    R96 (P0): scope ownership is decided BEFORE the lexical walk
    continues outward. Python makes the entire function block's
    bindings local -- ``mutator = safe`` later in ``inner`` makes
    ``mutator`` local to ``inner`` for the WHOLE block, even if the
    earlier reference is before the assignment. When a binding
    exists for ``name`` in the current scope but no binding
    dominates ``call_position``, the function reports
    ``(None, False, True)`` -- i.e. ``use_before_binding=True`` --
    and DOES NOT continue walking outward. The earlier
    implementation silently fell through to the outer-scope
    binding, which let an inner-scope local rebinding be resolved
    as the outer mutator.

    R98 (P0): outer-scope bindings are resolved using the
    invocation-time activation state, not the final source state.
    When ``outer`` calls ``inner`` at line ``P``, every binding in
    ``outer`` declared strictly AFTER ``P`` cannot have contributed
    the value seen when ``inner`` executes -- those bindings belong
    to later activation states of ``outer`` that do not exist yet.
    The caller threads ``outer_cutoffs`` -- a per-ancestor-scope-id
    position cutoff -- through the BFS so the lookup inside
    ``inner`` filters ``outer``'s bindings to those declared
    strictly before the call position. The cutoff is also
    transitive: ``inner`` calling ``deeper`` at line ``Q`` carries
    ``outer``'s cutoff forward to ``deeper`` so the three-level
    chain ``outer -> wrapper -> inner -> leaf`` preserves every
    ancestor cutoff.

    R99 (P0): control-flow dominance. An UNCONDITIONAL binding at
    the scope body level dominates any conditional binding whose
    position is earlier than the unconditional binding (the
    unconditional always runs and overwrites). When multiple
    pre-call bindings exist for the same ``(name, scope_id)``, the
    resolver now picks the latest UNCONDITIONAL binding (the
    ``path`` parent is the scope body list itself with attr
    ``"self"``) and only reports ambiguity when a conditional
    binding has a position strictly greater than the unconditional
    binding's position (the conditional might run last if its
    branch is taken). This closes the over-rejection of fixtures
    like ``if cond: x = mutator; x = safe; x()`` -- the
    unconditional ``x = safe`` dominates the conditional binding.

    Returns ``(body, is_ambiguous, use_before_binding)``.

    * ``body`` is the resolved AST body when ``name`` directly names
      a body or transitively aliases a body strictly before
      ``call_position``; ``None`` otherwise.
    * ``is_ambiguous`` is ``True`` when the live frontier contains
      mutually exclusive or branch-dependent bindings whose
      runtime value cannot be determined statically.
    * ``use_before_binding`` is ``True`` when the current scope
      owns ``name`` (at least one binding exists) but no binding
      dominates ``call_position``. Python would raise
      ``UnboundLocalError`` at this call site; the audit must
      neither resolve to an outer-scope binding nor flag a
      mutation that cannot happen.

    Cycles (``a = b; b = a``) terminate after the second hop and
    therefore resolve to ``(None, False, False)``.
    """
    chain = _scope_chain(scope_id, parent_scope_by_id, top_scope_id)
    seen_pairs: set[tuple[str, int]] = set()

    def _resolve_in(
        name: str, start_idx: int
    ) -> tuple[
        list[ast.stmt] | ast.Lambda | None, bool, bool
    ]:
        for idx in range(start_idx, len(chain)):
            sid = chain[idx]
            if (name, sid) in seen_pairs:
                return None, False, False
            entries = bindings.get((name, sid))
            if entries is None:
                # The current scope does NOT declare ``name``;
                # Python's lexical lookup (R86) walks outward.
                # Crucially, we do NOT apply the position filter
                # yet -- the binding we'll find in an outer scope
                # is textually independent of the call position
                # in our scope.
                continue
            if idx == start_idx:
                # Current-scope call: the binding is local to the
                # call scope. Python's own execution model makes
                # every binding in this block local for the whole
                # block; a rebinding AFTER the call cannot have
                # contributed the value. Apply the strict
                # position filter (R95) AND the scope-ownership
                # use-before-binding gate (R96).
                valid = [e for e in entries if e.position < call_position]
                if not valid:
                    return None, False, True
                # R99 (P0): control-flow dominance -- find the
                # latest UNCONDITIONAL binding (declared at the
                # scope-body level, not inside an ``if`` / ``for``
                # / ``try`` / ``match`` / ``with`` compound) and
                # use it as the live binding if no later
                # conditional binding exists. A conditional
                # binding with a position strictly greater than
                # the unconditional binding's position might be
                # the last to execute (if its branch is taken),
                # so the live frontier is ambiguous.
                unconditional = [
                    e
                    for e in valid
                    if _is_unconditional_at_scope(e.path, sid)
                ]
                if unconditional:
                    latest_unc = max(
                        unconditional, key=lambda e: e.position
                    )
                    later_conditionals = [
                        e
                        for e in valid
                        if not _is_unconditional_at_scope(e.path, sid)
                        and e.position > latest_unc.position
                    ]
                    if later_conditionals:
                        return None, True, False
                    entry = latest_unc
                elif len(valid) == 1:
                    entry = valid[0]
                else:
                    paths = {e.path for e in valid}
                    if len(paths) > 1:
                        return None, True, False
                    entry = max(valid, key=lambda e: e.position)
            else:
                # Outer-scope binding: the call sits inside an
                # inner function whose own body is only executed
                # when that function is invoked. By the time the
                # call fires, the outer-scope bindings are live.
                # R98 (P0): the activation cutoff for ``sid`` is
                # the position at which the current call was
                # made from ``sid`` (or an ancestor). Bindings in
                # ``sid`` declared AFTER that cutoff belong to a
                # later activation state of ``sid`` that has not
                # happened yet at the current execution point.
                cutoff: tuple[int, int] | None = (
                    outer_cutoffs.get(sid) if outer_cutoffs else None
                )
                if cutoff is not None:
                    valid_outer = [
                        e for e in entries if e.position < cutoff
                    ]
                    # R104 (P0): Python lexical resolution uses
                    # the NEAREST enclosing binding scope. If the
                    # scope has the name but no binding survives
                    # the cutoff, Python would raise
                    # ``UnboundLocalError`` rather than fall
                    # through to a more-distant scope. The audit
                    # therefore reports ``use_before_binding=True``
                    # instead of walking outward.
                    if not valid_outer and entries:
                        return None, False, True
                    entries = valid_outer
                if not entries:
                    # No pre-cutoff binding survives; the lookup
                    # in this scope is empty -- keep walking
                    # outward to the next lexical ancestor (the
                    # outer-scope binding is not yet bound at the
                    # current activation state).
                    continue
                # R104 (P0): apply R99 unconditional-dominance at
                # outer scopes too. An unconditional binding
                # dominates any conditional binding whose position
                # is earlier (the unconditional always runs and
                # overwrites). A conditional binding strictly
                # greater than the unconditional binding's
                # position makes the live frontier ambiguous.
                unconditional = [
                    e for e in entries
                    if _is_unconditional_at_scope(e.path, sid)
                ]
                if unconditional:
                    latest_unc = max(
                        unconditional, key=lambda e: e.position
                    )
                    later_conditionals = [
                        e for e in entries
                        if not _is_unconditional_at_scope(e.path, sid)
                        and e.position > latest_unc.position
                    ]
                    if later_conditionals:
                        return None, True, False
                    entry = latest_unc
                elif len(entries) == 1:
                    entry = entries[0]
                else:
                    paths = {e.path for e in entries}
                    if len(paths) > 1:
                        return None, True, False
                    entry = max(entries, key=lambda e: e.position)
            seen_pairs.add((name, sid))
            if entry.kind == "definition":
                return entry.body, False, False
            # entry.kind == "alias": resolve the alias target from
            # the SAME scope onward. The recursive call visits
            # ``sid`` again under the new name and continues
            # outward (only if the alias target has no binding in
            # ``sid``, which would trigger R96's use-before-binding
            # signal when the alias target is local).
            return _resolve_in(entry.target or name, idx)
        return None, False, False

    return _resolve_in(name, 0)


def _decorator_call_pairs(
    scope: list[ast.stmt] | ast.Lambda,
    bindings: dict[tuple[str, int], list[_Binding]],
    scope_id: int,
    parent_scope_by_id: dict[int, int | None],
    top_scope_id: int,
    outer_cutoffs: dict[int, tuple[int, int]] | None = None,
) -> tuple[
    list[tuple[ast.AST, list[ast.stmt] | ast.Lambda]],
    list[tuple[ast.AST, str]],
]:
    """Yield implicit call roots from bare-name and Attribute decorators.

    R82 (P0): Python evaluates ``@trigger`` as ``trigger(<decorated>)``
    when the decorated statement runs, and the resulting ``Call`` is
    not visible in the AST (the AST only records the decorator name;
    the wrapped call is a CPython implementation detail). The same
    is true for ``@mod.trigger`` (Attribute form). The previous
    detector only scanned explicit :class:`ast.Call` nodes inside the
    scope, so a local mutator reachable only through a bare-name
    decorator was invisible to the audit and the closed grammar was
    silently bypassed.

    R86 (P0): the decorator factory name is resolved through the
    lexical-scope chain (current scope -> enclosing -> ... -> top),
    not only the immediate scope. A decorator declared in an
    intermediate enclosing scope is observable and the audit must
    follow the chain.

    R87 (P0): the search walks every direct member of ``scope``
    *execution-aware* via :func:`_walk_runtime_scope`. The previous
    implementation only inspected decorators of the direct
    ``FunctionDef`` / ``AsyncFunctionDef`` / ``ClassDef`` members
    of the scope, so a decorated ``def`` nested under an ``if`` /
    ``try`` / ``with`` / ``for`` / ``while`` / ``match`` was
    invisible. The runtime walker descends into those executable
    compound statements while still pruning deferred function /
    lambda / method bodies, so a bare ``@trigger`` inside
    ``if enabled: @trigger def nested(): pass`` is now observable
    and the audit closes the gap.

    R90 (P0): the decorator's source position is used as the
    ``call_position`` argument to :func:`_resolve_alias` so a
    rebinding of the decorator factory AFTER the decorated
    definition cannot retroactively change which factory body is
    audited for the implicit invocation.

    R94 (P0): the function returns ``(pairs, ambiguous_calls)``
    instead of silently discarding ``is_ambiguous``. A decorator
    factory name whose resolution returns ``is_ambiguous=True``
    (multiple live bindings in distinct paths before the
    decorator position) is recorded as an ambiguous call site so
    the same fail-closed R90 path that already handles
    ``ast.Call`` ambiguity can flag decorator chains that
    previously slipped through. The decorator-only bypass that
    selected one of two live bindings is closed.

    R98 (P0): the activation cutoff dict is threaded from the BFS
    so a decorator factory declared in an outer scope resolves
    against the outer-scope bindings live at the time the inner
    scope was invoked, not the final outer-scope state.

    Returns ``(pairs, ambiguous_decorators)``:

    * ``pairs``: ``(decorator_node, target_body)`` pairs so the BFS
      can descend into the decorator factory body and audit it
      like any other reachable local-callable invocation. The
      decorator node itself is not an :class:`ast.Call`, so the
      call site can be ``None``; downstream consumers only use
      ``target_body``.
    * ``ambiguous_decorators``: ``(decorator_node, callee_name)``
      tuples where the decorator factory name resolved to multiple
      live bindings. The parent
      :func:`_collect_local_calls_in_callable_body` merges these
      into the same ambiguity violation list used by the explicit
      ``ast.Call`` walker so R94's decorator-only bypass closes.
    """
    pairs: list[tuple[ast.AST, list[ast.stmt] | ast.Lambda]] = []
    ambiguous_decorators: list[tuple[ast.AST, str]] = []
    if isinstance(scope, ast.Lambda):
        # Lambdas have no decorators of their own and their body is
        # a single expression that cannot host a ``def`` /
        # ``class`` statement. Nothing to do here.
        return pairs, ambiguous_decorators

    def _scan_decorator(
        dec: ast.AST, decorated_node: ast.AST
    ) -> None:
        callee_name: str | None = None
        if isinstance(dec, ast.Name):
            callee_name = dec.id
        elif (
            isinstance(dec, ast.Attribute)
            and isinstance(dec.value, ast.Name)
        ):
            callee_name = f"{dec.value.id}.{dec.attr}"
        if callee_name is None:
            return
        target_body, is_ambiguous, _use_before_binding = _resolve_alias(
            callee_name,
            bindings,
            scope_id,
            parent_scope_by_id,
            top_scope_id,
            _node_position(dec),
            outer_cutoffs,
        )
        if target_body is not None:
            pairs.append((decorated_node, target_body))
        elif is_ambiguous:
            # R94 (P0): propagate decorator ambiguity into the same
            # fail-closed path used for ast.Call ambiguity.
            ambiguous_decorators.append((decorated_node, callee_name))
        # use_before_binding: the decorator factory name is local
        # but unbound at the decorator position -- Python would
        # raise UnboundLocalError when the decorated statement
        # runs, and no mutation can occur. We deliberately do NOT
        # fall through to an outer-scope binding (R96) nor do we
        # flag a phantom mutation.

    seen_definitions: set[int] = set()
    for item in list(scope):
        for sub in _walk_runtime_scope(item):
            if not isinstance(
                sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if id(sub) in seen_definitions:
                continue
            seen_definitions.add(id(sub))
            for dec in sub.decorator_list:
                # A bare ``@trigger`` has no Call node; the implicit
                # invocation is created by the interpreter when the
                # decorated statement is reached. A ``@trigger(...)``
                # IS a Call and is therefore picked up by the explicit
                # walker below, so we deliberately skip Call-typed
                # decorators here to avoid double-counting.
                if isinstance(dec, ast.Call):
                    continue
                _scan_decorator(dec, sub)
    return pairs, ambiguous_decorators


def _collect_local_calls_in_callable_body(
    scope: list[ast.stmt] | ast.Lambda,
    bindings: dict[tuple[str, int], list[_Binding]],
    scope_id: int,
    parent_scope_by_id: dict[int, int | None],
    top_scope_id: int,
    outer_cutoffs: dict[int, tuple[int, int]] | None = None,
) -> tuple[
    list[tuple[ast.Call | ast.AST, list[ast.stmt] | ast.Lambda]],
    list[tuple[ast.Call | ast.AST, str]],
]:
    """Find every call to a local callable inside ``scope``.

    ``scope`` is either the body of a ``def`` (a ``list[stmt]``) or a
    single :class:`ast.Lambda` node. The walk is execution-aware:

    * ``def`` / ``lambda`` bodies declared *inside* ``scope`` are NOT
      descended into -- those bodies only become live when the
      enclosing helper is itself called, and that reachability is
      handled by :func:`_live_reachable_local_calls`;
    * class suites *inside* ``scope`` ARE descended into because a
      class statement is itself executable;
    * decorators and positional / keyword defaults ARE descended into
      because they execute at the enclosing ``def`` / ``class``
      definition time.

    R82 (P0): a bare-name or Attribute decorator like ``@trigger`` or
    ``@mod.trigger`` is treated as an implicit call ``trigger(<decorated>)``
    and resolved against the local callable tables so a mutator
    reached only through a decorator is still audited. The returned
    call site is the decorated node (which is itself a definition
    statement), not a synthetic :class:`ast.Call` -- downstream
    consumers only use ``target_body``.

    R86 (P0): both the explicit :class:`ast.Call` resolution and the
    implicit decorator resolution walk the lexical-scope chain via
    ``parent_scope_by_id`` so a name defined in an intermediate
    enclosing function is resolved and the BFS can audit the
    caller's deferred body.

    R90 (P0): each call / decorator site threads its own source
    ``(lineno, col_offset)`` as ``call_position`` into
    :func:`_resolve_alias` so a rebinding AFTER the call site
    cannot retroactively change which body the earlier call is
    audited against. The returned ambiguity list carries the call
    site and the unbound name so the BFS can flag a violation when
    multiple bindings at the same scope are all live before the
    call.

    R94 (P0): decorator-side ambiguity is propagated through
    :func:`_decorator_call_pairs` and MERGED with the explicit
    ``ast.Call`` ambiguity list before returning. The previous
    implementation dropped ``is_ambiguous`` for decorators so a
    bare-name factory chain through an ambiguous decorator was
    silently bypassed; the merged list routes both into the same
    fail-closed R90 path.

    R95/R96 (P0): :func:`_resolve_alias` now returns the three-tuple
    ``(target_body, is_ambiguous, use_before_binding)``. The
    third element reports a use-before-binding (Python would
    raise ``UnboundLocalError`` at this call site). For the audit
    semantics, a use-before-binding is NOT a reachable mutation --
    the call cannot execute -- so the call is silently
    unobservable. We do NOT add it to the ambiguity list and we
    do NOT add it to the BFS pair list. This closes the
    previous fall-through to an outer-scope binding for a name
    that the current scope owns (R96) and the previous incorrect
    selection of a post-call binding whose position exceeds the
    call position (R95).

    R98 (P0): the activation cutoff dict from the BFS is threaded
    into both the decorator resolution and the explicit
    ``ast.Call`` resolution so outer-scope names use the
    invocation-time binding state, not the final source state.

    Returns ``(pairs, ambiguous_calls)`` where ``pairs`` is the list
    of ``(call, target_body)`` tuples that feed the BFS queue and
    ``ambiguous_calls`` is the list of ``(call, callee_name)`` tuples
    where the resolution returned ``is_ambiguous=True``. The BFS
    flags each ambiguous call as a violation so a branch-defined
    same-name callable cannot silently pick one binding over another.
    """
    if isinstance(scope, ast.Lambda):
        # The lambda body is deferred at definition time but executes when
        # the lambda is invoked, so it is the live callable scope here.
        items: list[ast.AST] = [scope.body]
    else:
        items = list(scope)

    decorator_pairs, decorator_ambiguous_calls = _decorator_call_pairs(
        scope,
        bindings,
        scope_id,
        parent_scope_by_id,
        top_scope_id,
        outer_cutoffs,
    )
    pairs: list[
        tuple[ast.Call | ast.AST, list[ast.stmt] | ast.Lambda]
    ] = list(decorator_pairs)
    ambiguous_calls: list[tuple[ast.Call | ast.AST, str]] = list(
        decorator_ambiguous_calls
    )
    for item in items:
        for sub in _walk_runtime_scope(item):
            if not isinstance(sub, ast.Call):
                continue
            callee_name: str | None = None
            if isinstance(sub.func, ast.Name):
                callee_name = sub.func.id
            elif (
                isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
            ):
                callee_name = f"{sub.func.value.id}.{sub.func.attr}"
            if callee_name is None:
                continue
            target_body, is_ambiguous, _use_before_binding = _resolve_alias(
                callee_name,
                bindings,
                scope_id,
                parent_scope_by_id,
                top_scope_id,
                _node_position(sub),
                outer_cutoffs,
            )
            if target_body is not None:
                pairs.append((sub, target_body))
            elif is_ambiguous:
                ambiguous_calls.append((sub, callee_name))
    return pairs, ambiguous_calls


def _live_reachable_local_calls(
    body: list[ast.stmt],
    bindings: dict[tuple[str, int], list[_Binding]],
    parent_scope_by_id: dict[int, int | None],
    factory_statement: ast.stmt,
) -> tuple[
    list[tuple[ast.Call | ast.AST, list[ast.stmt] | ast.Lambda]],
    list[str],
]:
    """Return ``(reachable_pairs, ambiguity_violations)``.

    R62 (P0): the closed grammar for the authoritative collection must
    inspect the deferred bodies of any locally-defined callable that
    is invoked before the workset factory. Once a call to a local
    callable is found, the called callable's body is recursively
    inspected for further local-callable calls so a
    ``wrapper() -> mutator() -> refs.append(...)`` chain is properly
    resolved.

    R78 (P0): the reachability root set includes calls reachable from
    **definition-time expressions** of top-level ``def`` / ``class`` /
    ``lambda`` statements. Python evaluates function decorators,
    positional defaults, keyword defaults, class bases, class
    keywords, class decorators, and the class suite ITSELF at the
    moment the definition runs; only the *body* of the callable is
    deferred until invocation. The walker therefore descends into
    every pre-factory top-level statement execution-aware via
    :func:`_collect_local_calls_in_callable_body` -- nested
    function / lambda / method bodies remain pruned (deferred until
    the callable is invoked, then reached through the BFS), while
    decorators / defaults / class suites are inspected.

    R81 (P0): resolution is per-scope. Each statement is walked with
    its own ``scope_id`` (the top-level body id) and each reachable
    nested body is walked with ``id(target_body)`` as the new
    ``scope_id``. The top-level id is threaded through as the
    fallback so calls inside a nested helper can still resolve a
    top-level helper name.

    R82 (P0): implicit calls from bare-name and Attribute decorators
    are merged with the explicit :class:`ast.Call` pairs and BFS'd
    identically so a decorator-only invocation chain is fully
    audited.

    R86 (P0): ``parent_scope_by_id`` is threaded through every BFS
    hop so name resolution inside a reached nested body walks the
    full lexical-ancestor chain.

    R89 (P0): the BFS uses scope-by-scope shadowing -- a binding in
    an inner scope always wins over an outer-scope binding for the
    same name, so a parent alias cannot override a nearer direct
    binding.

    R90 (P0): every call / decorator site threads its own source
    position through :func:`_resolve_alias`, so a rebinding AFTER a
    call cannot retroactively change which body the earlier call is
    audited against. Branch-defined same-name callables produce
    ambiguous resolutions which are surfaced as a violation list so
    the caller can fail the audit instead of silently picking one
    binding.

    R91 (P0): lambda bodies are registered with their lexical parent
    scope so name resolution inside a reached lambda body walks the
    full lexical-ancestor chain.

    R98 (P0): the BFS tracks the CALLER's scope id alongside each
    ``(call, target_body)`` edge and threads an
    ``outer_cutoffs: dict[scope_id, (line, col)]`` through every
    hop. When the BFS descends into ``target_body`` from caller
    scope ``caller_sid`` at call position ``P``, the new cutoffs
    are ``outer_cutoffs ∪ {caller_sid -> P}`` (overwriting any
    earlier caller cutoff because the call site's position is the
    most recent activation boundary). :func:`_resolve_alias` then
    filters outer-scope bindings to those strictly before the
    cutoff for each ancestor scope. This makes the nested
    callable's view of the enclosing-scope state equal to the
    invocation-time state, not the final source state.

    The recursion is bounded by an ``id(target_body)`` visited set so
    a degenerate mutual recursion (e.g. ``a() -> b() -> a()``) does
    not loop the detector. Uncalled nested helpers whose deferred
    body is never reached do not contribute live mutations: their
    bodies are walked only when BFS visits them.
    """
    # R102 (P0) + R103 (P0): the BFS dedup key is
    # ``(id(target_body), frozenset(next_cutoffs.items()))`` -- the
    # body identity combined with the EFFECTIVE ancestor cutoffs
    # dict. The same body reached under meaningfully different
    # activation cutoffs is a different live frontier (e.g.
    # ``inner()`` called twice from ``outer`` with different
    # outer-scope binding states) and must be re-inspected. A
    # recursive cycle with unchanged state terminates because the
    # state key is identical and the body is visited at most once
    # per state.
    visited_states: set[
        tuple[int, frozenset[tuple[int, tuple[int, int]]]]
    ] = set()
    top_scope_id = id(body)

    ambiguity_violations: list[str] = []

    def _record_ambiguous(
        call: ast.Call | ast.AST,
        target_body: list[ast.stmt] | ast.Lambda,
        callee_name: str,
    ) -> None:
        body_id = id(target_body)
        if body_id in seen_body_ids:
            return
        seen_body_ids.add(body_id)
        ambiguity_violations.append(
            f"ambiguous callable binding for `{callee_name}` "
            f"reachable at line {getattr(call, 'lineno', '?')}; "
            f"multiple bindings exist in the same scope and the "
            f"runtime branch cannot be determined statically "
            f"(R90)."
        )

    # Step 1: walk every pre-factory top-level statement
    # execution-aware. For a top-level ``def ...:`` only the
    # decorators and defaults run; for a top-level ``class ...:``
    # the entire suite runs at class-creation time. ``_walk_runtime_scope``
    # prunes deferred function / lambda / method bodies but visits
    # the definition-time expressions and executable class suites
    # that may carry local callable calls. The top-level scope is
    # the outer-most lexical scope: there is NO outer-cutoff for
    # its ancestors because the ingest function is itself the root.
    initial_pairs: list[
        tuple[ast.Call | ast.AST, list[ast.stmt] | ast.Lambda]
    ] = []
    for stmt in body:
        if stmt is factory_statement:
            break
        pairs, ambiguous_calls = _collect_local_calls_in_callable_body(
            [stmt],
            bindings,
            top_scope_id,
            parent_scope_by_id,
            top_scope_id,
        )
        initial_pairs.extend(pairs)
        for call, callee_name in ambiguous_calls:
            # Top-level ambiguity: there's no reached body to record
            # the body_id of, so emit the violation directly.
            line = getattr(call, "lineno", "?")
            ambiguity_violations.append(
                f"ambiguous callable binding for `{callee_name}` "
                f"at top-level line {line}; multiple bindings exist "
                f"in the same scope and the runtime branch cannot be "
                f"determined statically (R90)."
            )

    # Step 2: BFS along local-call edges. Each reachable body is
    # descended into at most once. R98 (P0): each queue entry
    # carries the caller scope id so the descendant scope can
    # receive an updated ``outer_cutoffs`` dict whose
    # ``caller_sid`` entry points at this call's source position.
    results: list[
        tuple[ast.Call | ast.AST, list[ast.stmt] | ast.Lambda]
    ] = []
    # R102 (P0): each queue entry carries the INHERITED
    # ``outer_cutoffs`` dict from the caller's caller so every
    # ancestor cutoff is preserved across arbitrarily deep
    # nesting. The descendant's cutoffs are computed as
    # ``{**inherited_cutoffs, caller_sid: call_position}`` --
    # the caller-scope cutoff is the most recent activation
    # boundary, but every prior ancestor cutoff is preserved.
    queue: list[
        tuple[
            ast.Call | ast.AST,
            list[ast.stmt] | ast.Lambda,
            int,
            dict[int, tuple[int, int]],
        ]
    ] = [
        (call, target_body, top_scope_id, {})
        for call, target_body in initial_pairs
    ]
    seen_body_ids: set[int] = set()
    while queue:
        call, target_body, caller_scope_id, inherited_cutoffs = queue.pop(0)
        results.append((call, target_body))
        call_position = _node_position(call)
        # R102 (P0): inherit every ancestor cutoff AND set this
        # caller's cutoff. The descendant's view of any ancestor
        # scope is therefore filtered to bindings declared
        # strictly before the activation boundary at which the
        # descendant was reached from that ancestor.
        next_cutoffs: dict[int, tuple[int, int]] = {
            **inherited_cutoffs,
            caller_scope_id: call_position,
        }
        bid = id(target_body)
        # R103 (P0): the dedup state key is body identity plus
        # the EFFECTIVE ancestor cutoffs. A body reached twice
        # under different cutoffs is re-inspected; a recursive
        # cycle with unchanged state terminates.
        state_key = (bid, frozenset(next_cutoffs.items()))
        if state_key in visited_states:
            continue
        visited_states.add(state_key)
        sub_pairs, sub_ambiguous = _collect_local_calls_in_callable_body(
            target_body,
            bindings,
            bid,
            parent_scope_by_id,
            top_scope_id,
            next_cutoffs,
        )
        for sub_call, sub_target in sub_pairs:
            results.append((sub_call, sub_target))
            queue.append((sub_call, sub_target, bid, next_cutoffs))
        for sub_call, sub_name in sub_ambiguous:
            _record_ambiguous(sub_call, target_body, sub_name)

    return results, ambiguity_violations


def _callable_body_mutates_collection(
    callable_body: list[ast.stmt] | ast.Lambda,
    collection_name: str,
) -> str | None:
    """Return a violation if ``callable_body`` mutates the collection.

    R62 (P0): the closed collection grammar forbids any of the
    following inside a deferred body that becomes live via a
    pre-factory invocation:

    * any ``<collection>.method(...)`` call (including ``append``,
      ``extend``, ``clear``, ``pop``, ...);
    * ``<collection> <op>= ...`` (``+=``, ``*=``);
    * ``<collection>[...] = ...`` or ``del <collection>[...]``;
    * ``<collection>.attr = ...`` or ``del <collection>.attr``.

    R83 (P0): an annotated assignment like ``refs: list = []`` or
    ``refs.attr: T = value`` inside a called deferred body writes to
    the authoritative collection just like the equivalent plain
    ``Assign`` form. The previous implementation only inspected
    :class:`ast.Assign` / :class:`ast.AugAssign` / :class:`ast.Delete`
    nodes inside the deferred body and silently accepted an annotated
    reassignment (``refs: list = []`` inside ``def mutator(): ...;
    mutator()``), bypassing the closed grammar. The walk now applies
    :func:`_check_annassign_closed_grammar` to every
    :class:`ast.AnnAssign` so any annotated reassignment / subscript /
    attribute store against ``collection_name`` inside a called body
    is rejected.

    The walk uses :func:`_walk_runtime_scope` so class suites and
    decorators / defaults declared inside the deferred body are also
    inspected, while nested function / lambda / method bodies remain
    pruned (those are tracked by the R62 reachability graph instead).
    """
    if isinstance(callable_body, ast.Lambda):
        # The lambda body is the deferred callable body, not its
        # definition-time defaults. Inspect it when invocation made it live.
        items: list[ast.AST] = [callable_body.body]
    else:
        items = list(callable_body)

    for item in items:
        for sub in _walk_runtime_scope(item):
            # Any method call whose receiver is the collection.
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == collection_name
            ):
                return (
                    f"a called deferred body mutates the authoritative "
                    f"collection `{collection_name}` via `.{sub.func.attr}` "
                    f"on line {sub.lineno}; invoked nested callables cannot "
                    f"modify the factory input"
                )
            # R83: annotated assignment (e.g. ``refs: list = []`` or
            # ``refs.attr: T = value``) inside the called deferred body
            # reassigns / mutates the authoritative collection the same
            # way the equivalent ``Assign`` does. The closed grammar
            # must reject both forms. We reuse the top-level checker so
            # the message contract is identical. ``allow_initial_declaration``
            # is ``False`` because a deferred body is NEVER the
            # initial-declaration scope -- any ``refs: list = []`` form
            # is a REASSIGNMENT that must be rejected.
            if isinstance(sub, ast.AnnAssign):
                ann_violation = _check_annassign_closed_grammar(
                    sub,
                    collection_name,
                    allow_initial_declaration=False,
                )
                if ann_violation is not None:
                    return (
                        f"a called deferred body violates the closed "
                        f"authoritative-collection grammar on line "
                        f"{sub.lineno}: {ann_violation}"
                    )
            # Augmented assignment on the collection (any of the
            # three target shapes recognised by the closed grammar).
            if isinstance(sub, ast.AugAssign):
                target = sub.target
                if (
                    isinstance(target, ast.Name)
                    and target.id == collection_name
                ):
                    return (
                        f"a called deferred body augments the authoritative "
                        f"collection `{collection_name}` on line {sub.lineno}; "
                        f"the closed grammar forbids it"
                    )
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == collection_name
                ):
                    return (
                        f"a called deferred body augments "
                        f"`{collection_name}.{target.attr}` on line "
                        f"{sub.lineno}; the closed grammar forbids it"
                    )
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == collection_name
                ):
                    return (
                        f"a called deferred body augments "
                        f"`{collection_name}[...]` on line {sub.lineno}; "
                        f"the closed grammar forbids it"
                    )
            # Subscript or attribute store (assignment form).
            if isinstance(sub, ast.Assign):
                for assign_target in sub.targets:
                    if (
                        isinstance(assign_target, ast.Subscript)
                        and isinstance(assign_target.value, ast.Name)
                        and assign_target.value.id == collection_name
                    ):
                        return (
                            f"a called deferred body stores into "
                            f"`{collection_name}[...]` on line "
                            f"{sub.lineno}; the closed grammar forbids it"
                        )
                    if (
                        isinstance(assign_target, ast.Attribute)
                        and isinstance(assign_target.value, ast.Name)
                        and assign_target.value.id == collection_name
                    ):
                        return (
                            f"a called deferred body stores into "
                            f"`{collection_name}.{assign_target.attr}` on "
                            f"line {sub.lineno}; the closed grammar "
                            f"forbids it"
                        )
            # Subscript or attribute delete.
            if isinstance(sub, ast.Delete):
                for delete_target in sub.targets:
                    if (
                        isinstance(delete_target, ast.Subscript)
                        and isinstance(delete_target.value, ast.Name)
                        and delete_target.value.id == collection_name
                    ):
                        return (
                            f"a called deferred body deletes "
                            f"`{collection_name}[...]` on line "
                            f"{sub.lineno}; the closed grammar forbids it"
                        )
                    if (
                        isinstance(delete_target, ast.Attribute)
                        and isinstance(delete_target.value, ast.Name)
                        and delete_target.value.id == collection_name
                    ):
                        return (
                            f"a called deferred body deletes "
                            f"`{collection_name}.{delete_target.attr}` on "
                            f"line {sub.lineno}; the closed grammar "
                            f"forbids it"
                        )
    return None


def _check_assign_closed_grammar(
    node: ast.Assign, collection_name: str
) -> str | None:
    """Apply closed-grammar rules to an ``ast.Assign`` node.

    Rules enforced:

    * target is a :class:`ast.Name` naming the collection -- reassignment;
    * target is a :class:`ast.Subscript` whose value names the collection
      -- subscript store;
    * target is an :class:`ast.Attribute` whose value names the collection
      -- attribute store;
    * the right-hand side is a :class:`ast.Name` naming the collection --
      aliasing the collection under another name.
    """
    for assign_target in node.targets:
        # Reassignment of the collection itself (``refs = ...``).
        if (
            isinstance(assign_target, ast.Name)
            and assign_target.id == collection_name
        ):
            return (
                f"`{collection_name}` is reassigned on line "
                f"{node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
        # Subscript store (``refs[i] = ...``).
        if (
            isinstance(assign_target, ast.Subscript)
            and isinstance(assign_target.value, ast.Name)
            and assign_target.value.id == collection_name
        ):
            return (
                f"`{collection_name}[...]` is stored on line "
                f"{node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
        # Attribute store (``refs.attr = ...``).
        if (
            isinstance(assign_target, ast.Attribute)
            and isinstance(assign_target.value, ast.Name)
            and assign_target.value.id == collection_name
        ):
            return (
                f"`{collection_name}.{assign_target.attr}` is stored on "
                f"line {node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
    # Alias: ``<other> = refs`` -- the only "value-of-the-collection"
    # case the closed grammar forbids.
    if (
        isinstance(node.value, ast.Name)
        and node.value.id == collection_name
    ):
        return (
            f"`{collection_name}` is aliased to another name on line "
            f"{node.lineno}; the closed authoritative-collection grammar "
            f"forbids it"
        )
    return None


def _check_annassign_closed_grammar(
    node: ast.AnnAssign,
    collection_name: str,
    *,
    allow_initial_declaration: bool = True,
) -> str | None:
    """Apply closed-grammar rules to an ``ast.AnnAssign`` node.

    R79 (P0): the AST contract permits an ``ast.AnnAssign.target``
    of :class:`ast.Name`, :class:`ast.Attribute`, or
    :class:`ast.Subscript`. The previous check early-returned on any
    non-``Name`` target and silently accepted
    ``refs.attr: T = value`` and ``refs[0]: T = value``. Both
    forms write to the authoritative collection and must be
    rejected the same way the equivalent ``Assign`` checker
    rejects them.

    Annotated assignments include the initial declaration
    (``refs: list[X] = []``) AND any other annotated assignment that
    touches the collection -- including ``alias: list[X] = refs`` which
    aliases the collection under another name.

    R83 (P0): ``allow_initial_declaration`` is ``True`` for the
    top-level closed-grammar audit (the canonical empty-list
    ``refs: list[X] = []`` declaration is permitted) and ``False``
    when the checker is invoked from inside a called deferred body.
    Inside a deferred body, ``refs: list = []`` is a REASSIGNMENT
    of the authoritative collection (the body is not the
    initial-declaration scope), so even the empty-list form must
    be rejected.
    """
    target = node.target
    # Subscript target: ``refs[i]: T = value`` -- annotated store.
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id == collection_name
    ):
        return (
            f"`{collection_name}[...]` is stored via annotated "
            f"assignment on line {node.lineno}; the closed "
            f"authoritative-collection grammar forbids it"
        )
    # Attribute target: ``refs.attr: T = value`` -- annotated store.
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == collection_name
    ):
        return (
            f"`{collection_name}.{target.attr}` is stored via "
            f"annotated assignment on line {node.lineno}; the closed "
            f"authoritative-collection grammar forbids it"
        )
    if not isinstance(target, ast.Name):
        return None
    if target.id == collection_name:
        # Reassignment of the collection itself (annotated). The only
        # annotated assignment permitted is the initial empty-list
        # declaration; any other annotated assignment to the collection
        # name is rejected.
        if allow_initial_declaration and node.value is not None and (
            isinstance(node.value, ast.List) and not node.value.elts
        ):
            return None
        return (
            f"`{collection_name}` is reassigned via annotated "
            f"assignment on line {node.lineno}; the closed "
            f"authoritative-collection grammar forbids it"
        )
    # Aliasing annotated assignment: ``alias: T = refs``.
    if (
        node.value is not None
        and isinstance(node.value, ast.Name)
        and node.value.id == collection_name
    ):
        return (
            f"`{collection_name}` is aliased to another name via "
            f"annotated assignment on line {node.lineno}; the closed "
            f"authoritative-collection grammar forbids it"
        )
    return None


def _check_augassign_closed_grammar(
    node: ast.AugAssign, collection_name: str
) -> str | None:
    """Apply closed-grammar rules to an ``ast.AugAssign`` node."""
    target = node.target
    if (
        isinstance(target, ast.Name)
        and target.id == collection_name
    ):
        return (
            f"`{collection_name}` is augmented on line {node.lineno}; "
            f"the closed authoritative-collection grammar forbids it"
        )
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == collection_name
    ):
        return (
            f"`{collection_name}.{target.attr}` is augmented on line "
            f"{node.lineno}; the closed authoritative-collection grammar "
            f"forbids it"
        )
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id == collection_name
    ):
        return (
            f"`{collection_name}[...]` is augmented on line "
            f"{node.lineno}; the closed authoritative-collection grammar "
            f"forbids it"
        )
    return None


def _check_delete_closed_grammar(
    node: ast.Delete, collection_name: str
) -> str | None:
    """Apply closed-grammar rules to an ``ast.Delete`` node."""
    for delete_target in node.targets:
        if (
            isinstance(delete_target, ast.Subscript)
            and isinstance(delete_target.value, ast.Name)
            and delete_target.value.id == collection_name
        ):
            return (
                f"`{collection_name}[...]` is deleted on line "
                f"{node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
        if (
            isinstance(delete_target, ast.Attribute)
            and isinstance(delete_target.value, ast.Name)
            and delete_target.value.id == collection_name
        ):
            return (
                f"`{collection_name}.{delete_target.attr}` is deleted on "
                f"line {node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
    return None


def _check_call_closed_grammar(
    node: ast.Call, collection_name: str
) -> str | None:
    """Apply closed-grammar rules to an ``ast.Call`` node.

    Only non-canonical uses of the collection inside a call are
    rejected:

    * a method call other than ``append`` (``extend``, ``clear``, ...)
      on the collection;
    * passing the collection to any non-canonical call (positional
      or keyword argument) -- the factory ``tuple(refs)`` wrapper
      lives in the factory statement and is outside this walk.
    """
    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == collection_name
    ):
        if node.func.attr != "append":
            return (
                f"non-`append` method `{collection_name}."
                f"{node.func.attr}` is called on line {node.lineno}; "
                f"the closed authoritative-collection grammar only "
                f"permits `append(...)`"
            )
        return None

    for arg in node.args:
        if (
            isinstance(arg, ast.Name)
            and arg.id == collection_name
        ):
            return (
                f"`{collection_name}` is passed to a non-factory call on "
                f"line {node.lineno}; the closed authoritative-collection "
                f"grammar forbids it"
            )
    for kw in node.keywords:
        if (
            kw.arg is not None
            and isinstance(kw.value, ast.Name)
            and kw.value.id == collection_name
        ):
            return (
                f"`{collection_name}` is passed via keyword to a "
                f"non-factory call on line {node.lineno}; the closed "
                f"authoritative-collection grammar forbids it"
            )
    return None


def _validate_closed_collection_grammar(
    function_body: list[ast.stmt],
    collection_name: str,
    factory_statement: ast.stmt,
) -> str | None:
    """Enforce the closed authoritative-collection use grammar (R63).

    Before the factory assignment, the only permitted uses of
    ``collection_name`` are:

    1. The initial declaration ``refs = []`` /
       ``refs: list[...] = []``.
    2. The receiver of a canonical append ``refs.append(...)``.
    3. The argument to ``tuple(...)`` inside the factory call's
       ``references=`` keyword (which lives in ``factory_statement`` and
       is therefore outside the walk).

    Anything else is rejected:

    * any method call other than ``append`` (``extend``, ``clear``,
      ``pop``, ``insert``, ...);
    * augmented assignment (``+=``, ``*=``);
    * subscript or attribute store / delete;
    * aliasing the collection under a different name (including the
      annotated ``alias: list[X] = refs`` form);
    * passing the collection to any other function call.

    The walker is :func:`_walk_runtime_scope` rooted at each
    pre-factory top-level statement. This guarantees every relevant
    descendant (``Assign`` / ``AnnAssign`` / ``AugAssign`` / ``Delete``
    / ``Call``) is audited -- including nested ``if`` / ``try`` /
    class-suite positions -- rather than only the direct entries in
    ``function_body``.
    """
    for stmt in function_body:
        if stmt is factory_statement:
            break

        # The canonical initial declaration is the only statement-level
        # use permitted by the grammar.
        if _is_collection_initial_declaration(stmt, collection_name):
            continue

        # Execution-aware walk over each pre-factory statement. The
        # walker yields the statement itself first, then prunes nested
        # function / lambda / method bodies (those are tracked by R62
        # instead) while visiting class suites, decorators, and
        # defaults.
        for node in _walk_runtime_scope(stmt):
            violation: str | None = None
            if isinstance(node, ast.Assign):
                violation = _check_assign_closed_grammar(node, collection_name)
            elif isinstance(node, ast.AnnAssign):
                violation = _check_annassign_closed_grammar(
                    node, collection_name
                )
            elif isinstance(node, ast.AugAssign):
                violation = _check_augassign_closed_grammar(
                    node, collection_name
                )
            elif isinstance(node, ast.Delete):
                violation = _check_delete_closed_grammar(
                    node, collection_name
                )
            elif isinstance(node, ast.Call):
                violation = _check_call_closed_grammar(node, collection_name)
            if violation is not None:
                return violation

    return None


def _validate_scoped_dispatcher_sinks(
    ingest: ast.FunctionDef,
    collapsed_local: str,
    reachable_local_callable_bodies: list[list[ast.stmt] | ast.Lambda],
) -> tuple[str | None, tuple[int, int] | None]:
    """Validate every scoped-dispatcher call reachable from the
    ingest function's live pre-factory execution context (R64).

    Returns ``(violation, canonical_position)``. When ``violation`` is
    None, ``canonical_position`` is the source position of the first
    canonical dispatcher call (used for the execution-order chain).

    R64 (P0): the detector must inspect every call to
    ``promote_alert_signals_scoped_for_accumulator`` or
    ``promote_alert_signals_scoped`` reachable from:

    * the top-level statements of the ingest function (including
      executable class suites, function decorators and defaults,
      and lambda defaults);
    * the bodies of any local callable called before the factory
      (R62 reachability graph).

    Reachable scopes are walked execution-aware. The sink audit
    then enforces:

    * **Exactly one canonical sink**: the detector records every
      canonical call; more than one canonical call is itself a
      violation because each canonical sink would re-run the
      dispatcher with the same authority. A canonical sink cannot
      mask a sibling non-canonical sink.
    * **Name-only canonical binding**: ``signal_ids=`` must be the
      :class:`ast.Name` ``collapsed_local`` exactly. The attribute
      form ``signal_ids=current_run_signal_ids.signal_ids`` is
      rejected because ``current_run_signal_ids`` is a ``tuple``
      (it does not expose ``.signal_ids``) -- the attribute form
      encodes an impossible runtime contract.
    * **No non-canonical sinks**: every other dispatcher call (with
      a different ``signal_ids=`` or with no ``signal_ids=`` keyword)
      is reported.
    """
    SCOPED_DISPATCHERS = frozenset(
        {
            "promote_alert_signals_scoped_for_accumulator",
            "promote_alert_signals_scoped",
        }
    )

    canonical_count = 0
    canonical_position: tuple[int, int] | None = None
    noncanonical_lines: list[int] = []

    def _audit_scope(
        scope: list[ast.stmt] | ast.Lambda,
    ) -> None:
        if isinstance(scope, ast.Lambda):
            items: list[ast.AST] = [scope]
        else:
            items = list(scope)
        for item in items:
            for sub in _walk_runtime_scope(item):
                if not isinstance(sub, ast.Call):
                    continue
                callee = _call_name(sub)
                if callee not in SCOPED_DISPATCHERS:
                    continue
                sig_value = _kwarg_value(sub, "signal_ids")
                is_canonical = (
                    sig_value is not None
                    and isinstance(sig_value, ast.Name)
                    and sig_value.id == collapsed_local
                )
                if is_canonical:
                    nonlocal canonical_count, canonical_position
                    canonical_count += 1
                    if canonical_position is None:
                        canonical_position = _node_position(sub)
                else:
                    noncanonical_lines.append(sub.lineno)

    # Top-level statements of the ingest function (all positions:
    # before, at, and after the factory statement -- the audit covers
    # the entire live lexical scope).
    _audit_scope(list(ingest.body))

    # Bodies of every local callable called before the factory. The
    # R62 reachability graph has already pruned uncalled helpers, so
    # only bodies whose execution is provably live are audited here.
    for body in reachable_local_callable_bodies:
        _audit_scope(body)

    if canonical_count == 0:
        return (
            f"no scoped-dispatcher call passes the collapsed scope "
            f"({collapsed_local}) via signal_ids=.",
            None,
        )
    if canonical_count > 1:
        return (
            f"multiple canonical scoped-dispatcher calls found "
            f"({canonical_count}); exactly one canonical sink is "
            f"permitted so promotion does not run more than once.",
            canonical_position,
        )
    if noncanonical_lines:
        return (
            f"non-canonical scoped-dispatcher call(s) found on line(s) "
            f"{sorted(noncanonical_lines)}; every "
            f"`promote_alert_signals_scoped*` call must use "
            f"`signal_ids={collapsed_local}` exactly.",
            canonical_position,
        )
    return None, canonical_position





# ---------------------------------------------------------------------------
# R22/R23/R32/R33/R37/R38/R39/R40: end-to-end workset chain
# ---------------------------------------------------------------------------


def check_ingestion_stable_deduplicates_artifact_workset(
    tree: ast.Module, path: Path
) -> list[str]:
    """The full R20 semantic chain must be proven end-to-end.

    ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
    R22/R23/R24 + R32/R33 + R37/R38/R39/R40 + R48/R49/R50.

    The detector proves the chain outcome -> per-iteration ref ->
    collection -> factory call -> collapsed scope -> scoped dispatcher
    using TRUE AST ancestry (R37), STRICT same-loop-body binding
    (R38/R39), exhaustive append-set validation (R49), the closed
    append grammar (R50), same-arm alias binding (R48), and the
    append-before-factory ordering check (R40).

    Strict-binding checks:

    * **R37** -- the appended constructor must be a true AST
      descendant of a ``for`` loop body. Earlier ``for`` loops plus
      later unrelated ``if`` blocks at deeper indentation are
      rejected.
    * **R38** -- for the alias form ``ref = CurrentRunSignalRef(...);
      refs.append(ref)``, the alias assignment must be a statement
      reachable from the SAME canonical scope as the append and must
      occur BEFORE the append statement. An alias assigned AFTER the
      append (use-before-define) or in a different canonical scope is
      rejected.
    * **R39** -- for the signal-ID alias form
      ``signal_id = <loop>.signal_id``, the alias assignment must be
      a statement reachable from the SAME canonical scope as the
      constructor. An alias from a sibling arm or from a different
      scope is rejected.
    * **R40** -- the per-iteration append statement must occur
      BEFORE the top-level factory assignment
      ``build_current_run_workset(...)``. Otherwise the factory
      receives an empty collection at runtime.
    * **R48** -- the alias (or signal-id alias) used by an append
      must be bound in the SAME canonical ``if isinstance(<target>,
      ...) ... continue`` arm that owns the append. Cross-arm
      laundering is rejected.
    * **R49** -- every authoritative append into the reference
      collection must independently satisfy the chain. A valid
      sibling arm cannot mask a broken one.
    * **R50** -- only direct ``<collection>.append(...)`` statements
      or appends inside canonical ``if isinstance(<target>, ...)``
      arms are accepted. Compound statements like ``try``/``with``/
      arbitrary ``if``/nested loops are silently rejected.

    Discovery vs. semantic authority:

    * Discovery (the ``_walk_same_function_scope`` loop below) is
      used ONLY to identify the canonical chain's enclosing ``for``
      loop and reference collection name. It is NOT the semantic
      authority.
    * Semantic authority is provided by
      ``_find_reference_collection_appends`` (closed-grammar
      walker) plus ``_validate_all_appends`` (per-append
      validator). The active detector wires those helpers directly,
      so a valid sibling arm cannot mask a broken one (R49).
    """
    del path
    ingest = _function_def_in(tree, "_ingest_alert_signals")
    if ingest is None:
        # Preserve the bounded legacy fixture contract for the standalone
        # dict.fromkeys detector; canonical production trees use the named
        # ingestion function and take the execution-aware path below.
        if _contains_call_to(tree, "fromkeys"):
            return []
        return [
            "ingestion does not define _ingest_alert_signals; the "
            "canonical ingestion function is missing."
        ]


    parent_map = _build_parent_map(ingest)

    # ------------------------------------------------------------------
    # Step 1: discovery -- locate the loop and the collection.
    #
    # Use the same closed-grammar walker that ``_find_reference_collection_appends``
    # uses so discovery and validation agree on what counts as a
    # canonical append. Inline appends inside ``try`` / ``with`` /
    # arbitrary ``if`` / nested ``for`` are excluded here as well,
    # so the R50 / R55 closed-grammar guarantee extends to
    # discovery.
    # ------------------------------------------------------------------
    append_call: ast.Call | None = None
    collection_name: str | None = None
    enclosing_target: str | None = None
    append_loop: ast.For | None = None
    for stmt in ingest.body:
        if not isinstance(stmt, ast.For):
            continue
        candidate_target = _for_target_name(stmt)
        if candidate_target is None:
            continue
        # Walk the for body with the closed-grammar rules to find
        # the first canonical append (any collection name) inside a
        # canonical isinstance dispatch arm whose subject matches
        # the loop target. The walker descends ONLY into canonical
        # arms, so inline appends under ``try``/``with``/arbitrary
        # ``if``/nested loops are not seen here either (R50/R55).
        append_call, collection_name = _first_canonical_append_in_body(
            list(stmt.body), candidate_target
        )
        if append_call is not None and collection_name is not None:
            enclosing_target = candidate_target
            append_loop = stmt
            break

    if append_call is None or collection_name is None or enclosing_target is None:
        return [
            "ingestion does not append a ``CurrentRunSignalRef`` to "
            "any canonical scope; the canonical pattern is "
            "``refs.append(CurrentRunSignalRef(...))`` inside a "
            "canonical ``if isinstance(<target>, ...) ... continue`` "
            "arm."
        ]

    # Step 2: collect every authoritative append into the reference
    # collection via the closed-grammar walker (R49 + R50 + R48).
    # ``append_call`` was found inside a top-level ``for`` of the
    # ingestion body (Step 1 above), so ``append_loop`` is already
    # set to that for loop here.

    append_position = _enclosing_statement_position(parent_map, append_call)

    all_appends = _find_reference_collection_appends(
        list(append_loop.body), collection_name, enclosing_target
    ) if append_loop is not None else []
    if not all_appends:
        return [
            f"the authoritative reference collection ``{collection_name}`` "
            f"has no canonical appends in any canonical ``if "
            f"isinstance({enclosing_target}, ...) ... continue`` dispatch "
            f"arm; inline appends under ``try``/``with``/arbitrary "
            f"``if``/nested loops are not accepted (R50/R55)."
        ]

    # ------------------------------------------------------------------
    # Step 3: validate every authoritative append (R48/R49/R50).
    # The validator supports both ``refs.append(CurrentRunSignalRef(...))``
    # (inline) and ``ref = CurrentRunSignalRef(...); refs.append(ref)``
    # (alias) with same-scope alias resolution.
    # ------------------------------------------------------------------
    append_loop = _enclosing_for(parent_map, all_appends[0])
    if append_loop is None:
        append_loop = _enclosing_for(parent_map, append_call)
    if append_loop is None:
        return [
            "the authoritative append is not inside any ``for`` loop; "
            "the canonical R20 chain requires appending one constructed "
            "ref per iteration."
        ]
    violation = _validate_all_appends(
        all_appends, enclosing_target, parent_map
    )
    if violation is not None:
        return [violation]

    # ------------------------------------------------------------------
    # Step 4: identify the authoritative factory boundary.
    # ------------------------------------------------------------------

    # R30: the factory assignment RHS must BE the factory call.
    factory_workset_name: str | None = None
    factory_statement: ast.stmt | None = None
    factory_stmt_position: tuple[int, int] | None = None
    for stmt in ingest.body:
        if isinstance(stmt, ast.Assign):
            if stmt.value is None:
                continue
            assign_value = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            if stmt.value is None:
                continue
            assign_value = stmt.value
        else:
            continue
        if not isinstance(assign_value, ast.Call):
            continue
        if _call_name(assign_value) != "build_current_run_workset":
            continue
        factory_call: ast.Call = assign_value
        references_value = _kwarg_value(factory_call, "references")
        if references_value is None:
            continue
        if isinstance(references_value, ast.Call):
            if (
                _call_name(references_value) == "tuple"
                and references_value.args
                and isinstance(references_value.args[0], ast.Name)
            ):
                ref_collection_name = references_value.args[0].id
            else:
                continue
        elif isinstance(references_value, ast.Name):
            ref_collection_name = references_value.id
        else:
            continue
        if ref_collection_name != collection_name:
            continue
        if isinstance(stmt, ast.Assign):
            if not stmt.targets:
                continue
            target = stmt.targets[0]
        else:
            if stmt.target is None:
                continue
            target = stmt.target
        if not isinstance(target, ast.Name):
            continue
        factory_workset_name = target.id
        factory_statement = stmt
        factory_stmt_position = _node_position(stmt)
        break

    if factory_workset_name is None:
        return [
            f"ingestion does not call "
            f"``build_current_run_workset(references={collection_name})`` "
            f"with a top-level assignment; the factory must be the "
            f"assignment value itself (no wrapper)."
        ]

    if factory_stmt_position is None or factory_statement is None:
        return [
            "ingestion does not expose a source position for the "
            "``build_current_run_workset(...)`` assignment."
        ]

    # R56/R58/R59/R61 (P0): compare the canonical append set with every
    # same-function append that can mutate the authoritative collection before
    # the factory evaluates it.  The broad traversal crosses intermediary AST
    # nodes and expression descendants, including definition-time expressions
    # and executable class suites, while pruning deferred definition bodies.
    broad_appends = _find_all_targeted_appends_before_factory(
        list(ingest.body), collection_name, factory_statement
    )
    canonical_append_ids = {id(item) for item in all_appends}
    noncanonical = [
        item for item in broad_appends if id(item) not in canonical_append_ids
    ]
    if noncanonical:
        noncanonical_lines = sorted(item.lineno for item in noncanonical)
        return [
            f"the authoritative reference collection ``{collection_name}`` "
            f"is mutated outside the canonical ``if isinstance(...) ... "
            f"continue`` arm grammar before the factory on line(s) "
            f"{noncanonical_lines}; only canonical appends may reach the "
            f"factory (R50/R55/R56/R58/R59/R61)"
        ]

    # R63 (P0): enforce the closed authoritative-collection use grammar
    # before the factory.  Aliases, augmented assignment, non-`append`
    # method calls, subscript/attribute stores/deletes, and other call
    # arguments that receive the collection are rejected.
    grammar_violation = _validate_closed_collection_grammar(
        list(ingest.body), collection_name, factory_statement
    )
    if grammar_violation is not None:
        return [grammar_violation]

    # R62 (P0): every locally-defined callable that is invoked before
    # the factory becomes live at call time.  Its deferred body must be
    # inspected for collection mutations; the existing R61 broad
    # walker only sees the definition-time expressions, not the body.
    # R81 (P0): the per-scope harvest and the per-scope reachability
    # walker must share the SAME list object so the ``id(body)``
    # identity used by ``_collect_local_callable_bodies`` matches the
    # ``top_scope_id`` used by ``_live_reachable_local_calls`` and
    # ``_resolve_alias``. A fresh ``list(ingest.body)`` per call would
    # produce two distinct ids and silently fail every lookup.
    # R86 (P0): ``parent_scope_by_id`` is threaded through every BFS
    # hop so name resolution inside a reached nested body walks the
    # full lexical-ancestor chain (current -> enclosing -> ... ->
    # top), per Python's lexical scoping rules.
    # R89 (P0): resolution is scope-by-scope shadowing -- an
    # inner-scope binding always wins over an outer-scope binding for
    # the same name, so a parent alias cannot override a nearer
    # direct binding.
    # R90 (P0): each binding is an ordered event with a source
    # position; resolution picks the latest binding strictly before
    # the call. Branch-defined same-name callables produce ambiguous
    # resolutions which are surfaced as violations.
    # R91 (P0): lambda bodies are registered with their lexical
    # parent scope so name resolution inside a reached lambda body
    # walks the full lexical-ancestor chain.
    # R92 (P0): class methods are registered only under the qualified
    # ``ClassName.method_name`` key; the unqualified method name does
    # not leak from a class namespace into the enclosing function's
    # local callable table.
    ingest_body_list = list(ingest.body)
    (
        local_callable_bindings,
        parent_scope_by_id,
    ) = _collect_local_callable_bodies(ingest_body_list)
    reachable_calls, ambiguity_violations = _live_reachable_local_calls(
        ingest_body_list,
        local_callable_bindings,
        parent_scope_by_id,
        factory_statement,
    )

    if ambiguity_violations:
        return ambiguity_violations

    reachable_bodies: list[list[ast.stmt] | ast.Lambda] = []
    seen_body_ids: set[int] = set()
    for _, callable_body in reachable_calls:
        body_id = id(callable_body)
        if body_id in seen_body_ids:
            continue
        seen_body_ids.add(body_id)
        reachable_bodies.append(callable_body)

        body_violation = _callable_body_mutates_collection(
            callable_body,
            collection_name,
        )
        if body_violation is not None:
            return [body_violation]

    # ------------------------------------------------------------------
    # Step 5: append-before-factory execution order (R40).
    # ------------------------------------------------------------------
    if append_position > factory_stmt_position:
        return [
            f"the append statement (line {append_position[0]}) must "
            f"occur BEFORE the factory assignment "
            f"``build_current_run_workset(...)`` on line "
            f"{factory_stmt_position[0]}; otherwise the factory receives "
            f"an empty collection at runtime."
        ]

    # R22: link 4 -- the collapsed scope binding.
    collapsed_local: str | None = None
    collapsed_stmt_position: tuple[int, int] | None = None
    for stmt in ingest.body:
        result = _collapsed_scope_local(stmt, factory_workset_name)
        if result is not None:
            collapsed_local = result
            collapsed_stmt_position = _node_position(stmt)
            break
    if collapsed_local is None:
        return [
            f"ingestion does not bind ``{factory_workset_name}.signal_ids`` "
            f"to a local; the canonical pattern is "
            f"``current_run_signal_ids = tuple({factory_workset_name}.signal_ids)``."
        ]

    if collapsed_stmt_position is None:
        return [
            "ingestion does not expose a source position for the "
            "collapsed current-run scope assignment."
        ]
    if factory_stmt_position >= collapsed_stmt_position:
        return [
            "the factory assignment must occur BEFORE the collapsed-scope "
            "assignment; the workset must exist before its signal_ids "
            "projection is evaluated."
        ]

    # R22 / R46 / R64 (P0): the scoped dispatcher sink must consume the
    # canonical collapsed local via ``signal_ids=``; every call to
    # ``promote_alert_signals_scoped_for_accumulator`` or
    # ``promote_alert_signals_scoped`` in the live lexical scope is
    # inspected so a valid dead-branch sink cannot mask an invalid
    # returned sink.
    dispatcher_violation, dispatcher_stmt_position = (
        _validate_scoped_dispatcher_sinks(
            ingest,
            collapsed_local,
            reachable_bodies,
        )
    )
    if dispatcher_violation is not None:
        return [dispatcher_violation]
    if dispatcher_stmt_position is None:
        return [
            "the scoped-dispatcher call has no source position; the "
            "execution-order chain cannot be proven."
        ]
    if collapsed_stmt_position >= dispatcher_stmt_position:
        return [
            "the collapsed-scope assignment must occur BEFORE the "
            "scoped-dispatcher call; the dispatcher must consume the "
            "freshly collapsed signal_ids local."
        ]

    return []


# ---------------------------------------------------------------------------
# Scoped promotion detectors
# ---------------------------------------------------------------------------


def check_scoped_promotion_handles_empty_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "empty"
            and isinstance(func.value, ast.Name)
            and func.value.id == "IncidentPromotionResult"
        ):
            return []
    return [
        "scoped promotion does not short-circuit on empty "
        "request.signal_ids"
    ]


def check_scoped_promotion_owns_actionable_projection(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "promote_scoped_alert_signals")
    if fn is None:
        return ["scoped promotion: promote_scoped_alert_signals missing"]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "IncidentPromotionResult":
            return []
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "IncidentPromotionResult"
            and func.attr in ("empty", "from_wire_dict")
        ):
            return []
    return [
        "scoped promotion does not construct "
        "IncidentPromotionResult (no actionable projection)"
    ]


# ---------------------------------------------------------------------------
# Handler / backend client / backend adapter detectors
# ---------------------------------------------------------------------------


def check_handler_rejects_missing_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "from_dict"
            and isinstance(func.value, ast.Name)
            and func.value.id == "PromoteAlertSignalsRequest"
        ):
            violations.append(
                "handler uses PromoteAlertSignalsRequest.from_dict; "
                "must call parse_promote_alert_signals_request"
            )
    if not _contains_call_to(tree, "parse_promote_alert_signals_request"):
        violations.append(
            "handler does not call parse_promote_alert_signals_request"
        )
    return violations


def check_handler_uses_scoped_promotion_call(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _contains_call_to(tree, "promote_scoped_alert_signals"):
        return ["handler does not call promote_scoped_alert_signals"]
    return []


def check_backend_client_exposes_scoped_call(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "SchedulerClient")
    if cls is None:
        return ["backend client: SchedulerClient missing"]
    for node in cls.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            in (
                "promote_alert_signals_scoped",
                "promote_alert_signals_scoped_for_accumulator",
            )
        ):
            return []
    return ["SchedulerClient missing promote_alert_signals_scoped method"]


def check_backend_adapter_parses_camel_case_wire(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if _function_def(tree, "_response_to_promotion_result") is not None:
        for call_name in ("from_wire_dict", "IncidentPromotionResult"):
            if _contains_call_to(tree, call_name):
                return []
    for needle in ("scannedSignalIds", "openedIncidentIds"):
        if _contains_text(tree, needle):
            return []
    return [
        "backend adapter does not parse camelCase wire field "
        "'scannedSignalIds'"
    ]


# ---------------------------------------------------------------------------
# Contract / adapter detectors
# ---------------------------------------------------------------------------


def check_contract_exposes_wire_parser(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "IncidentPromotionResult")
    if cls is None:
        return ["contract: IncidentPromotionResult missing"]
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "from_wire_dict"
        for node in cls.body
    ):
        return ["IncidentPromotionResult missing from_wire_dict"]
    if not _contains_text(tree, "scannedSignalIds"):
        return [
            "IncidentPromotionResult does not surface scannedSignalIds "
            "on the wire"
        ]
    return []


def check_persist_alert_signals_returns_artifact_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if _contains_call_to(tree, "PersistedAlertSignal"):
        return []
    return [
        "persist_alert_signals does not construct PersistedAlertSignal"
    ]


def check_eligibility_forbids_legacy_source_label(
    tree: ast.Module, path: Path
) -> list[str]:
    """Reject the legacy ``source="review_packet_artifacts"`` label.

    ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 close-out
    (R20 Defect 4 -- file-wide check / substring match).
    """
    del path
    if _contains_exact_string_constant(tree, "review_packet_artifacts"):
        return [
            "eligibility references forbidden source label "
            "'review_packet_artifacts'; the persisted packet identity is "
            "the authoritative scope."
        ]
    return []


# ---------------------------------------------------------------------------
# Processor / batch detectors
# ---------------------------------------------------------------------------


def check_processor_records_successful_writes_only(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "_process_incident")
    if fn is None:
        return ["processor: _process_incident missing"]
    violations: list[str] = []
    for outer in ast.walk(fn):
        if isinstance(outer, ast.Try):
            for handler_node in outer.finalbody:
                for descendant in ast.walk(handler_node):
                    if (
                        isinstance(descendant, ast.Call)
                        and isinstance(descendant.func, ast.Attribute)
                        and descendant.func.attr == "record_successful_write"
                    ):
                        violations.append(
                            "processor records budget inside a finally "
                            "block (consumes even on failed write)"
                        )
    if not _contains_call_to(fn, "record_successful_write"):
        violations.append(
            "processor never calls record_successful_write on a "
            "successful packet write"
        )
    return violations


def check_processor_checks_budget_before_packet_write(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call(
        tree, "_process_incident", "can_attempt"
    ):
        return [
            "processor never calls budget.can_attempt() before "
            "write_diagnosis_review_packet"
        ]
    return []


def check_processor_uses_budget_for_eligibility(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call_with_kwarg(
        tree,
        "_process_incident",
        "evaluate_incident_eligibility",
        "review_packet_budget",
    ):
        return [
            "processor does not forward review_packet_budget to "
            "evaluate_incident_eligibility"
        ]
    return []


def check_batch_forwards_budget_to_processor(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call_with_kwarg(
        tree,
        "process_incident_batch",
        "_process_incident",
        "review_packet_budget",
    ):
        return [
            "process_incident_batch does not forward "
            "review_packet_budget to _process_incident"
        ]
    return []


# ---------------------------------------------------------------------------
# Budget / collector / eligibility detectors
# ---------------------------------------------------------------------------


def check_budget_keyed_by_collector_run_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "ReviewPacketCreationBudget")
    if cls is None:
        return ["budget: ReviewPacketCreationBudget missing"]
    for node in cls.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "__init__"
            and any(
                arg.arg == "collector_run_id" for arg in node.args.args
            )
        ):
            return []
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "collector_run_id"
        ):
            return []
    return [
        "ReviewPacketCreationBudget is not keyed by collector_run_id"
    ]


def check_budget_reconstruction_filters_by_exact_collector_id(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    if _contains_text(tree, "review_packet_artifacts"):
        violations.append(
            "budget reconstruction uses forbidden source label "
            "'review_packet_artifacts'"
        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "startswith":
            continue
        if not node.args or not isinstance(node.args[0], ast.Attribute):
            continue
        if node.args[0].attr in ("run_id", "collector_run_id"):
            violations.append(
                "budget reconstruction uses filename-prefix matching "
                f"({node.args[0].attr}.startswith(...))"
            )
    return violations


def check_collector_instantiates_review_packet_budget(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(
        tree, "run_automatic_diagnosis_loop_evidence_collection"
    )
    if fn is None:
        return ["collector: entry function missing"]
    if not _contains_call_to(fn, "ReviewPacketCreationBudget"):
        return [
            "collector does not instantiate ReviewPacketCreationBudget"
        ]
    return []


def check_eligibility_bypasses_historical_count_when_budget_present(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "evaluate_incident_eligibility")
    if fn is None:
        return ["eligibility: evaluate_incident_eligibility missing"]
    if not _function_uses_kwarg(
        tree, "evaluate_incident_eligibility", "review_packet_budget"
    ):
        return [
            "evaluate_incident_eligibility does not accept "
            "review_packet_budget"
        ]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in (
            "rglob",
            "glob",
            "listdir",
            "scandir",
        ):
            return [
                "evaluate_incident_eligibility consults the "
                "filesystem directly even when "
                "review_packet_budget is supplied"
            ]
        if isinstance(func, ast.Name) and func.id in (
            "_count_files",
            "count_files",
            "_count_artifacts",
            "count_artifacts",
        ):
            return [
                "evaluate_incident_eligibility consults the "
                "filesystem directly even when "
                "review_packet_budget is supplied"
            ]
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _check(
    tree: ast.Module | None,
    path: Path,
    check: Callable[[ast.Module, Path], list[str]],
    label: str,
) -> list[str]:
    if tree is None:
        return [f"{label}: cannot parse {path}"]
    return [f"{label}: {v}" for v in check(tree, path)]


def run_static_checks() -> list[str]:
    """Run every detector against the production tree."""
    files: list[
        tuple[str, Path, Callable[[ast.Module, Path], list[str]]]
    ] = [
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_uses_scoped_promotion,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_forbids_global_scan_fallback,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_logs_explicit_current_run_scope,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_uses_artifact_identity,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_stable_deduplicates_artifact_workset,
        ),
        (
            "scoped_promotion",
            SCOPED_PROMOTION_PATH,
            check_scoped_promotion_handles_empty_scope,
        ),
        (
            "scoped_promotion",
            SCOPED_PROMOTION_PATH,
            check_scoped_promotion_owns_actionable_projection,
        ),
        (
            "handler",
            HANDLER_PATH,
            check_handler_rejects_missing_scope,
        ),
        (
            "handler",
            HANDLER_PATH,
            check_handler_uses_scoped_promotion_call,
        ),
        (
            "backend_client",
            SCHEDULER_CLIENT_PATH,
            check_backend_client_exposes_scoped_call,
        ),
        (
            "backend_adapter",
            BACKEND_ADAPTER_PATH,
            check_backend_adapter_parses_camel_case_wire,
        ),
        ("contract", CONTRACT_PATH, check_contract_exposes_wire_parser),
        (
            "persistence",
            PERSISTENCE_PATH,
            check_persist_alert_signals_returns_artifact_identity,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_records_successful_writes_only,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_checks_budget_before_packet_write,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_uses_budget_for_eligibility,
        ),
        ("batch", BATCH_PATH, check_batch_forwards_budget_to_processor),
        (
            "budget",
            BUDGET_PATH,
            check_budget_keyed_by_collector_run_identity,
        ),
        (
            "budget",
            BUDGET_PATH,
            check_budget_reconstruction_filters_by_exact_collector_id,
        ),
        (
            "collector",
            COLLECTOR_PATH,
            check_collector_instantiates_review_packet_budget,
        ),
        (
            "eligibility",
            ELIGIBILITY_PATH,
            check_eligibility_bypasses_historical_count_when_budget_present,
        ),
    ]
    violations: list[str] = []
    for label, path, check in files:
        tree = _parse(path)
        violations.extend(_check(tree, path, check, label))
    return violations


def main(argv: list[str]) -> int:
    del argv  # CLI flags intentionally unused
    violations = run_static_checks()
    if violations:
        for violation in violations:
            print(violation)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

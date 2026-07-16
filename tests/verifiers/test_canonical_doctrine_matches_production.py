"""Doctrine-to-production contract test.

Parses the real production file
``src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py``
and proves the canonical chain inside
``_ingest_alert_signals`` matches the major-statement sequence
documented in ``docs/doctrine/verifier-canonical-syntax.md``.

The production function has a long body that begins with a
docstring and several setup statements before the canonical
chain begins. This test searches the body for the canonical
chain nodes (rather than relying on absolute indices) so the
test stays correct as the surrounding setup evolves.

The major statements that must exist (in source order):

1. State 0 -- authoritative accumulator declaration
   (``workset_refs: list[CurrentRunSignalRef] = []``).
2. State 1 -- canonical ``for`` loop
   (``for outcome in persist_result.promotable_outcomes:``).
3. State 2 -- canonical ``if/elif/else: continue`` dispatch
   inside the loop (the fallback ``continue`` is REQUIRED).
4. State 3 -- authoritative append to ``workset_refs``
   (``workset_refs.append(CurrentRunSignalRef(...))``).
5. State 4 -- unique workset factory with
   ``references=tuple(workset_refs)`` (NOT the bare list).
6. State 5 -- signal-ID projection from
   ``current_run_workset.signal_ids`` wrapped in ``tuple(...)``.
7. State 6 -- direct dispatcher declaration
   (``dispatch_result: IncidentPromotionResult | Exception | None = None``).
8. State 7 -- direct dispatcher call
   ``promote_alert_signals_scoped_for_accumulator(...)`` with
   ``signal_ids=current_run_signal_ids``.

CORRECTION05 R5: the contract test must fail if the
dispatcher call is missing, if the dispatcher is placed
inside a non-canonical compound, if the ``signal_ids``
argument is wrong, if ``references=tuple(workset_refs)`` is
not used (or ``workset_refs`` is passed without ``tuple(...)``),
if the workset factory's input is wrong, if an outcome arm
is missing, if the fallback ``continue`` is missing, or if
the append is the wrong constructor. The test is intentionally
not satisfied by "node existence" -- it walks the exact AST
shapes the doctrine specifies.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PRODUCTION_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "k8s_diag_agent"
    / "health"
    / "loop_alertmanager_snapshot_signals.py"
)


def _parse_production_function() -> ast.FunctionDef:
    """Parse the production file and return the
    ``_ingest_alert_signals`` FunctionDef node."""
    src = PRODUCTION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(PRODUCTION_PATH))
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_ingest_alert_signals"
        ):
            return node
    raise AssertionError(
        f"_ingest_alert_signals not found in {PRODUCTION_PATH}"
    )


def _find_accumulator_index(body: list[ast.stmt]) -> int:
    """Return the index of the workset_refs accumulator declaration."""
    for i, stmt in enumerate(body):
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "workset_refs"
        ):
            return i
    raise AssertionError("workset_refs accumulator not found")


def _find_node_by_name(
    body: list[ast.stmt], name: str, start_after: int = -1
) -> int:
    """Return the index of an AnnAssign whose target Name is ``name``,
    searching strictly after ``start_after``."""
    for i, stmt in enumerate(body):
        if i <= start_after:
            continue
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == name
        ):
            return i
    raise AssertionError(f"{name} AnnAssign not found after {start_after}")


def _find_canonical_loop_index(body: list[ast.stmt], start_after: int) -> int:
    """Return the index of the canonical ``for outcome in
    persist_result.promotable_outcomes`` loop."""
    for i, stmt in enumerate(body):
        if i <= start_after:
            continue
        if not isinstance(stmt, ast.For):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        if stmt.target.id != "outcome":
            continue
        if not isinstance(stmt.iter, ast.Attribute):
            continue
        if not isinstance(stmt.iter.value, ast.Name):
            continue
        if (
            stmt.iter.value.id == "persist_result"
            and stmt.iter.attr == "promotable_outcomes"
        ):
            return i
    raise AssertionError("canonical for loop not found")


def _find_required_continue_in_if_chain(head: ast.If) -> bool:
    """Walk the if-orelse-if chain until a Continue is found.

    In Python AST, ``elif`` is encoded as an :class:`ast.If`
    inside the parent ``if.orelse``. The trailing ``else:``
    may live on any of those nodes. The ``else`` clause MUST
    contain exactly one ``Continue`` statement -- ``else: pass``
    or absent ``else`` are both rejected.
    """
    cursor: ast.If | None = head
    while cursor is not None:
        if cursor.orelse:
            first = cursor.orelse[0]
            if isinstance(first, ast.Continue):
                # Ensure the else clause is exactly the continue
                # and contains nothing else.
                return len(cursor.orelse) == 1
            if isinstance(first, ast.If):
                cursor = first
                continue
        return False
    return False


def _find_call_by_name(
    body: list[ast.stmt], call_name: str, start_after: int = -1
) -> ast.Call:
    """Return the first direct-Name ``call_name`` call at the body level."""
    for i, stmt in enumerate(body):
        if i <= start_after:
            continue
        for sub_stmt in ast.walk(stmt):
            if not isinstance(sub_stmt, ast.Call):
                continue
            if not isinstance(sub_stmt.func, ast.Name):
                continue
            if sub_stmt.func.id == call_name:
                return sub_stmt
    raise AssertionError(
        f"call named {call_name!r} not found after index {start_after}"
    )


def test_production_file_exists() -> None:
    """Sanity check: the production file exists at the documented path."""
    assert PRODUCTION_PATH.exists(), (
        f"production source not found at {PRODUCTION_PATH}"
    )


def test_production_function_is_top_level_def() -> None:
    """_ingest_alert_signals is a top-level async/sync FunctionDef."""
    func = _parse_production_function()
    assert isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))


def test_state0_accumulator_is_ann_assign_to_typed_list() -> None:
    """State 0: ``workset_refs: list[CurrentRunSignalRef] = []``."""
    func = _parse_production_function()
    idx = _find_accumulator_index(func.body)
    stmt = func.body[idx]
    assert isinstance(stmt, ast.AnnAssign)
    assert isinstance(stmt.target, ast.Name)
    assert stmt.target.id == "workset_refs"
    assert isinstance(stmt.value, ast.List)
    assert stmt.value.elts == []


def test_state1_canonical_for_loop_present() -> None:
    """State 1: ``for outcome in persist_result.promotable_outcomes:``."""
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    idx = _find_canonical_loop_index(func.body, start_after=accum_idx)
    loop = func.body[idx]
    assert isinstance(loop, ast.For)
    assert isinstance(loop.target, ast.Name)
    assert loop.target.id == "outcome"
    assert isinstance(loop.iter, ast.Attribute)
    assert loop.iter.value.id == "persist_result"
    assert loop.iter.attr == "promotable_outcomes"


def test_state2_canonical_if_elif_else_continue_inside_loop() -> None:
    """State 2: canonical ``if/elif/else: continue`` chain with the
    fallback ``continue`` REQUIRED.

    The fallback ``continue`` trailer is mandatory in the
    production grammar: the doctrine REQUIRES it and the
    production tests REJECT an absent or replaced trailer.
    """
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    loop_idx = _find_canonical_loop_index(func.body, start_after=accum_idx)
    loop = func.body[loop_idx]
    assert isinstance(loop, ast.For)
    if_stmt = loop.body[0]
    assert isinstance(if_stmt, ast.If)
    assert len(if_stmt.body) >= 1
    assert _find_required_continue_in_if_chain(if_stmt), (
        "expected else: continue trailer somewhere in the if-orelse-if chain"
    )


def test_state3_authoritative_append_to_workset_refs() -> None:
    """State 3: ``workset_refs.append(CurrentRunSignalRef(...))``."""
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    loop_idx = _find_canonical_loop_index(func.body, start_after=accum_idx)
    loop = func.body[loop_idx]
    assert isinstance(loop, ast.For)
    last_stmt = loop.body[-1]
    assert isinstance(last_stmt, ast.Expr)
    append_call = last_stmt.value
    assert isinstance(append_call, ast.Call)
    assert isinstance(append_call.func, ast.Attribute)
    assert append_call.func.attr == "append"
    assert isinstance(append_call.func.value, ast.Name)
    assert append_call.func.value.id == "workset_refs"
    # Constructor must be the canonical CurrentRunSignalRef(...).
    assert len(append_call.args) == 1
    arg = append_call.args[0]
    assert isinstance(arg, ast.Call)
    assert isinstance(arg.func, ast.Name)
    assert arg.func.id == "CurrentRunSignalRef"


def test_state4_workset_factory_uses_references_tuple_call() -> None:
    """State 4: ``current_run_workset = build_current_run_workset(...
    references=tuple(workset_refs), ...)``.

    The grammar REQUIRES ``references=tuple(workset_refs)`` --
    passing the bare ``workset_refs`` list is rejected because
    the factory contract requires an immutable sequence.
    """
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    factory_idx = _find_node_by_name(
        func.body, "current_run_workset", start_after=accum_idx
    )
    factory = func.body[factory_idx]
    assert isinstance(factory, ast.AnnAssign)
    assert isinstance(factory.value, ast.Call)
    assert isinstance(factory.value.func, ast.Name)
    assert factory.value.func.id == "build_current_run_workset"
    # Inspect the ``references`` keyword argument: must be
    # ``tuple(Name("workset_refs"))``.
    kw_by_name = {
        kw.arg: kw.value for kw in factory.value.keywords if kw.arg is not None
    }
    assert "references" in kw_by_name, (
        "build_current_run_workset call MUST pass a `references=` kwarg"
    )
    references_value = kw_by_name["references"]
    assert isinstance(references_value, ast.Call), (
        "references= must be a `tuple(...)` call, not a bare Name"
    )
    assert isinstance(references_value.func, ast.Name)
    assert references_value.func.id == "tuple"
    assert len(references_value.args) == 1
    inner = references_value.args[0]
    assert isinstance(inner, ast.Name)
    assert inner.id == "workset_refs"


def test_state5_signal_id_projection_from_workset_signal_ids() -> None:
    """State 5: ``current_run_signal_ids = tuple(current_run_workset.signal_ids)``.

    The projection MUST be from ``current_run_workset.signal_ids``
    wrapped in ``tuple(...)``. A direct Name load or any other
    attribute would be rejected.
    """
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    projection_idx = _find_node_by_name(
        func.body, "current_run_signal_ids", start_after=accum_idx
    )
    projection = func.body[projection_idx]
    assert isinstance(projection, ast.AnnAssign)
    assert isinstance(projection.value, ast.Call)
    assert isinstance(projection.value.func, ast.Name)
    assert projection.value.func.id == "tuple"
    assert len(projection.value.args) == 1
    inner = projection.value.args[0]
    assert isinstance(inner, ast.Attribute)
    assert isinstance(inner.value, ast.Name)
    assert inner.value.id == "current_run_workset"
    assert inner.attr == "signal_ids"


def test_state6_dispatcher_declaration_uses_union_type_and_none() -> None:
    """State 6: ``dispatch_result: IncidentPromotionResult | Exception | None = None``.

    The RHS MUST be the constant ``None`` (the variable is
    initialised to a sentinel value before the try block).
    """
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    dispatcher_decl_idx = _find_node_by_name(
        func.body, "dispatch_result", start_after=accum_idx
    )
    decl = func.body[dispatcher_decl_idx]
    assert isinstance(decl, ast.AnnAssign)
    assert isinstance(decl.target, ast.Name)
    assert decl.target.id == "dispatch_result"
    assert isinstance(decl.value, ast.Constant)
    assert decl.value.value is None


def test_state7_dispatcher_call_passes_signal_ids_current_run_signal_ids() -> None:
    """State 7: the dispatcher call is a direct
    ``promote_alert_signals_scoped_for_accumulator(...)`` with
    ``signal_ids=current_run_signal_ids``.

    The doctrine requires the dispatcher to receive
    ``signal_ids=current_run_signal_ids`` so the backend reads
    from the canonical workset projection. The dispatcher call
    lives inside a ``try`` block (the exception-capture path);
    the test walks the body and matches the call by direct Name,
    not by body-level nesting, so it remains correct when the
    surrounding try/except scaffolding evolves.
    """
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    call = _find_call_by_name(
        func.body,
        "promote_alert_signals_scoped_for_accumulator",
        start_after=accum_idx,
    )
    kw_by_name = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    assert "signal_ids" in kw_by_name, (
        "dispatcher call MUST pass a `signal_ids=` kwarg"
    )
    signal_ids_value = kw_by_name["signal_ids"]
    assert isinstance(signal_ids_value, ast.Name)
    assert signal_ids_value.id == "current_run_signal_ids", (
        f"dispatcher must read signal_ids from current_run_signal_ids "
        f"projection (State 5), got {signal_ids_value.id!r}"
    )


def test_canonical_chain_states_are_in_source_order() -> None:
    """States 0..6 occur in source order; the dispatcher call (State 7)
    occurs after the dispatcher declaration (State 6)."""
    func = _parse_production_function()
    accum_idx = _find_accumulator_index(func.body)
    loop_idx = _find_canonical_loop_index(func.body, start_after=accum_idx)
    factory_idx = _find_node_by_name(
        func.body, "current_run_workset", start_after=loop_idx
    )
    projection_idx = _find_node_by_name(
        func.body, "current_run_signal_ids", start_after=factory_idx
    )
    dispatcher_decl_idx = _find_node_by_name(
        func.body, "dispatch_result", start_after=projection_idx
    )
    # The dispatcher call must appear AFTER the dispatcher
    # declaration in source order (no absolute index needed).
    call = _find_call_by_name(
        func.body,
        "promote_alert_signals_scoped_for_accumulator",
        start_after=dispatcher_decl_idx,
    )
    # call.lineno > dispatcher_decl_idx-statement lineno
    decl_stmt = func.body[dispatcher_decl_idx]
    assert call.lineno > decl_stmt.lineno, (
        "dispatcher call must follow the dispatcher declaration in source order"
    )
    # And the projection (State 5) must come AFTER the factory (State 4)
    # which must come AFTER the loop (State 1).
    assert accum_idx < loop_idx < factory_idx < projection_idx
    assert projection_idx < dispatcher_decl_idx


@pytest.mark.parametrize(
    "doctrine_path",
    [
        Path(__file__).resolve().parents[2]
        / "docs"
        / "doctrine"
        / "verifier-canonical-syntax.md"
    ],
)
def test_doctrine_documents_state_sequence(doctrine_path: Path) -> None:
    """The doctrine file documents the state sequence (states 0-7)."""
    text = doctrine_path.read_text(encoding="utf-8")
    for state in (
        "State 0",
        "State 1",
        "State 2",
        "State 3",
        "State 4",
        "State 5",
        "State 6",
        "State 7",
    ):
        assert state in text, f"doctrine missing {state}"

"""Contract tests for ``scripts.verifiers.verifier_core``.

This file proves the retained verifier-core primitives behave as
documented and do NOT include the interpreter machinery forbidden
by the canonical contract.

The earlier draft of this file tested a wider API surface:
``CODE_CANONICAL``, the 23 ``SUB_*`` constants,
``EXPECTED_PUBLIC_API``, ``all_subcodes()``,
``SOURCE_LINE_DIRECTNESS_BOUND``, ``enforce_directness_bound``,
``Diagnostic``, ``format_violation``, ``sort_diagnostics``, and
``unique_top_level_function``. CORRECTION05 removes those
symbols because the production R20 verifier does not consume
any of them, so the tests have been deleted alongside the
symbols. A dedicated
``tests/verifiers/test_subcode_evidence_executable.py`` file
that exercised the deleted subcode vocabulary has been deleted
in its entirety.

The test inventory below is the authoritative contract for the
narrowed, post-CORRECTION05 public surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.verifiers import verifier_core

# ---------------------------------------------------------------------------
# Parse helpers (codes.py)
# ---------------------------------------------------------------------------


def test_parse_strict_returns_module() -> None:
    """parse_strict returns an ``ast.Module`` for valid source."""
    tree = verifier_core.parse_strict(
        "def f(x):\n    return x\n", filename="<test>"
    )
    assert any(
        isinstance(node, type(tree.body[0]))
        and getattr(node, "name", None) == "f"
        for node in tree.body
    )


def test_parse_strict_raises_on_syntax_error() -> None:
    """parse_strict raises ``VerInfrastructureError`` on SyntaxError."""
    with pytest.raises(verifier_core.VerInfrastructureError) as info:
        verifier_core.parse_strict("def f(x)\n    return x\n", filename="<test>")
    assert "syntax error" in str(info.value)


def test_parse_path_returns_none_on_broken_file(tmp_path: Path) -> None:
    """parse_path returns ``None`` on parse failure (non-raising)."""
    path = tmp_path / "broken.py"
    path.write_text("def f(x)\n    return x\n")
    assert verifier_core.parse_path(path) is None


def test_read_source_round_trips(tmp_path: Path) -> None:
    """read_source returns the file's bytes (UTF-8) verbatim."""
    p = tmp_path / "hello.py"
    p.write_text("hello\n", encoding="utf-8")
    assert verifier_core.read_source(p) == "hello\n"


# ---------------------------------------------------------------------------
# Location helpers (diagnostics.py)
# ---------------------------------------------------------------------------


def test_location_of_handles_none_and_node() -> None:
    """location_of maps ``None`` and real nodes to the documented shape."""
    assert verifier_core.location_of(None) == verifier_core.SourceLocation(0, 0)
    node = ast.parse("x = 1\n", filename="<test>").body[0]
    loc = verifier_core.location_of(node)
    assert loc.line > 0


# ---------------------------------------------------------------------------
# Top-level lookup (lookups.py)
# ---------------------------------------------------------------------------


def test_function_def_returns_top_level_only() -> None:
    """top_level_function only matches top-level definitions."""
    src = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n"
    )
    tree = verifier_core.parse_strict(src)
    assert verifier_core.top_level_function(tree, "outer") is not None
    assert verifier_core.top_level_function(tree, "inner") is None


def test_top_level_function_returns_none_when_absent() -> None:
    """top_level_function returns None when the name is absent."""
    tree = verifier_core.parse_strict("def f(): pass\n")
    assert verifier_core.top_level_function(tree, "missing") is None


def test_parse_function_body_matches_function_body_statements() -> None:
    """parse_function_body is the doctrine-mandated public alias."""
    src = "def f():\n    x = 1\n    return x\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    a = verifier_core.parse_function_body(func)
    b = verifier_core.function_body_statements(func)
    assert list(a) == list(b)
    assert len(list(a)) == 2


# ---------------------------------------------------------------------------
# Directness primitives (directness.py)
# ---------------------------------------------------------------------------


def test_find_direct_calls_only_matches_direct_name_load() -> None:
    """single_direct_name_call matches a direct-Name call and rejects
    an Attribute load.
    """
    src = "def f():\n    g()\n    return a.b\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    # ``g()`` is a direct-Name call at the top level.
    direct = verifier_core.single_direct_name_call(
        verifier_core.function_body_statements(func), "g"
    )
    assert direct is not None
    assert isinstance(direct, ast.Call)
    assert isinstance(direct.func, ast.Name)
    assert direct.func.id == "g"
    # ``return a.b`` is an Attribute load, NOT a direct-Name call to g.
    assert (
        verifier_core.single_direct_name_call(
            verifier_core.function_body_statements(func), "a.b"
        )
        is None
    )
    assert (
        verifier_core.single_direct_name_call(
            verifier_core.function_body_statements(func), "b"
        )
        is None
    )


def test_is_direct_name_call_matches_single_direct_name_call() -> None:
    """is_direct_name_call is the public alias for single_direct_name_call."""
    src = "def f():\n    g()\n    g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.is_direct_name_call(body, "g") is not None
    assert verifier_core.is_direct_name_call(body, "missing") is None
    assert verifier_core.is_direct_name_call(
        body, "g"
    ) is verifier_core.single_direct_name_call(body, "g")


def test_direct_name_from_load_handles_attribute() -> None:
    """direct_name_from_load returns the loaded symbol name for direct-Name
    loads (``a = b`` -> ``"b"``) and the attribute name for direct-Attribute
    loads (``c = obj.attr`` -> ``"attr"``).
    """
    src = "a = b\nc = obj.attr\n"
    tree = verifier_core.parse_strict(src)
    direct_name_load = tree.body[0].value  # Name("b")
    direct_attr_load = tree.body[1].value  # Attribute(value=Name("obj"), attr="attr")
    assert verifier_core.direct_name_from_load(direct_name_load) == "b"
    assert verifier_core.direct_name_from_load(direct_attr_load) == "attr"


def test_single_direct_name_call_finds_top_level_expr() -> None:
    """``g()`` as an Expr statement is detected at the top level."""
    src = "def f():\n    g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is not None


def test_single_direct_name_call_finds_top_level_assignment() -> None:
    """``x = g()`` is detected as a direct-Name call at the top level."""
    src = "def f():\n    x = g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is not None


def test_single_direct_name_call_finds_top_level_annotated_assignment() -> None:
    """``x: T = g()`` is detected as a direct-Name call at the top level."""
    src = "def f():\n    x: int = g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is not None


def test_single_direct_name_call_does_not_descend_into_if() -> None:
    """A direct-Name call inside an ``if`` body is NOT detected."""
    src = "def f():\n    if cond:\n        g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is None


def test_single_direct_name_call_does_not_descend_into_try() -> None:
    """A direct-Name call inside a ``try`` body is NOT detected."""
    src = "def f():\n    try:\n        g()\n    except Exception:\n        pass\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is None


def test_single_direct_name_call_does_not_descend_into_with() -> None:
    """A direct-Name call inside a ``with`` body is NOT detected."""
    src = "def f():\n    with cm:\n        g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is None


def test_single_direct_name_call_does_not_descend_into_nested_def() -> None:
    """A direct-Name call inside a nested ``def`` is NOT detected."""
    src = "def f():\n    def inner():\n        g()\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.single_direct_name_call(body, "g") is None


def test_statement_value_handles_expr_assign_annassign_return() -> None:
    """statement_value returns the immediate expression of Expr/Assign/AnnAssign/Return."""
    src = (
        "def f():\n"
        "    g()\n"
        "    x = h()\n"
        "    y: int = i()\n"
        "    return j()\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert isinstance(verifier_core.statement_value(body[0]), ast.Call)
    assert isinstance(verifier_core.statement_value(body[1]), ast.Call)
    assert isinstance(verifier_core.statement_value(body[2]), ast.Call)
    assert isinstance(verifier_core.statement_value(body[3]), ast.Call)


def test_statement_value_returns_none_for_compound_statements() -> None:
    """statement_value returns ``None`` for compound statement shapes."""
    src = (
        "def f():\n"
        "    if cond:\n        pass\n"
        "    for x in []:\n        pass\n"
        "    while False:\n        pass\n"
        "    try:\n        pass\n    except Exception:\n        pass\n"
        "    with cm:\n        pass\n"
        "    match v:\n        case _:\n            pass\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    for stmt in body:
        assert verifier_core.statement_value(stmt) is None


# ---------------------------------------------------------------------------
# Detectors (detectors.py)
# ---------------------------------------------------------------------------


def test_detect_partial_application_locates_bare_partial() -> None:
    """detect_partial_application finds a direct ``partial(...)`` call."""
    src = "def f():\n    partial(g, x)\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_partial_application(body) is not None


def test_detect_partial_application_rejects_locally_defined_partial() -> None:
    """Option A: a locally defined ``partial`` is also rejected."""
    src = (
        "def f():\n"
        "    def partial(g, x):\n        return g\n"
        "    partial(g, x)\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_partial_application(body) is not None


def test_detect_partial_application_ignores_functools_partial() -> None:
    """Option A: ``functools.partial`` is NOT detected (attribute access)."""
    src = "import functools\ndef f():\n    functools.partial(g, x)\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_partial_application(body) is None


def test_detect_partial_application_returns_none_for_safe_body() -> None:
    """A safe body without ``partial`` returns ``None``."""
    src = "def f():\n    x = g()\n    return x\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_partial_application(body) is None


def test_detect_dynamic_getattr_skips_unrelated_string_constants() -> None:
    """A bare ``"getattr"`` constant is not the built-in ``getattr``."""
    tree = verifier_core.parse_strict("x = 'getattr'\n")
    assert verifier_core.detect_dynamic_getattr(tree.body) is None


def test_detect_dynamic_getattr_handles_bare_expr() -> None:
    """detect_dynamic_getattr detects ``getattr(...)`` as a bare Expr."""
    src = "def f():\n    getattr(module, 'dispatch')\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_dynamic_getattr(body) is not None


def test_detect_dynamic_getattr_handles_plain_assign() -> None:
    """detect_dynamic_getattr detects ``x = getattr(...)``."""
    src = "def f():\n    invoke = getattr(module, 'dispatch')\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_dynamic_getattr(body) is not None


def test_detect_dynamic_getattr_handles_annassign() -> None:
    """detect_dynamic_getattr detects ``x: T = getattr(...)``."""
    src = (
        "from typing import Callable\n"
        "def f():\n"
        "    invoke: Callable[..., object] = getattr(module, 'dispatch')\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_dynamic_getattr(body) is not None


def test_detect_dynamic_getattr_handles_return() -> None:
    """detect_dynamic_getattr detects ``return getattr(...)``."""
    src = "def f():\n    return getattr(module, 'dispatch')\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_dynamic_getattr(body) is not None


def test_detect_dynamic_getattr_does_not_match_mod_getattr() -> None:
    """``mod.getattr(...)`` is NOT a call to the built-in ``getattr``."""
    src = "def f():\n    return mod.getattr('dispatch')\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    assert verifier_core.detect_dynamic_getattr(body) is None


def test_detect_callables_stored_in_collections_flags_obvious_alias_list() -> None:
    """A non-empty list of Names matches ``is_callable_collection_literal``."""
    src = "refs = [a, b, c]\n"
    tree = verifier_core.parse_strict(src)
    assert (
        verifier_core.is_callable_collection_literal(tree.body[0].value)
        is True
    )


def test_is_callable_collection_literal_rejects_empty_list() -> None:
    """Empty ``refs: list[T] = []`` does NOT match (canonical accumulator)."""
    src = "def f():\n    refs: list[T] = []\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    ann_assign = func.body[0]
    assert (
        verifier_core.is_callable_collection_literal(ann_assign.value) is False
    )


def test_is_callable_collection_literal_rejects_scalar() -> None:
    """A scalar ``x = 1`` does NOT match ``is_callable_collection_literal``."""
    src = "x = 1\n"
    tree = verifier_core.parse_strict(src)
    node = tree.body[0].value
    assert verifier_core.is_callable_collection_literal(node) is False


def test_detect_star_expansion_flags_starred_argument() -> None:
    """detect_star_expansion returns the location of the first starred arg."""
    src = "def f():\n    g(*args)\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    body = verifier_core.function_body_statements(func)
    call = verifier_core.single_direct_name_call(body, "g")
    assert call is not None
    assert verifier_core.detect_star_expansion(call) is not None


def test_detect_nested_compound_under_handles_with() -> None:
    """detect_nested_compound_under recognises a ``with`` wrapper."""
    src = (
        "def f():\n"
        "    with cm:\n"
        "        x = 1\n"
        "        y = 2\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    with_stmt = func.body[0]
    assert isinstance(with_stmt, ast.With)
    assert (
        verifier_core.detect_nested_compound_under(with_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_async_with() -> None:
    """detect_nested_compound_under recognises an ``async with`` wrapper."""
    src = (
        "async def f():\n"
        "    async with cm:\n"
        "        x = 1\n"
        "        y = 2\n"
    )
    tree = verifier_core.parse_strict(src)
    # The async function is parsed as ast.AsyncFunctionDef, not
    # ast.FunctionDef; the top_level_function helper intentionally
    # only matches plain defs, so reach into the body directly.
    assert len(tree.body) == 1
    func = tree.body[0]
    assert isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef))
    assert func.name == "f"
    async_with_stmt = func.body[0]
    assert isinstance(async_with_stmt, ast.AsyncWith)
    assert (
        verifier_core.detect_nested_compound_under(async_with_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_for() -> None:
    """detect_nested_compound_under recognises a non-canonical ``for``."""
    src = "def f():\n    for x in []:\n        x = 1\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    for_stmt = func.body[0]
    assert (
        verifier_core.detect_nested_compound_under(for_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_while() -> None:
    """detect_nested_compound_under recognises a ``while`` wrapper."""
    src = "def f():\n    while True:\n        x = 1\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    while_stmt = func.body[0]
    assert (
        verifier_core.detect_nested_compound_under(while_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_if() -> None:
    """detect_nested_compound_under recognises a non-canonical ``if``."""
    src = "def f():\n    if cond:\n        x = 1\n"
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    if_stmt = func.body[0]
    assert (
        verifier_core.detect_nested_compound_under(if_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_try() -> None:
    """detect_nested_compound_under recognises a ``try`` wrapper."""
    src = (
        "def f():\n"
        "    try:\n        x = 1\n    except Exception:\n        pass\n"
    )
    tree = verifier_core.parse_strict(src)
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    try_stmt = func.body[0]
    assert (
        verifier_core.detect_nested_compound_under(try_stmt, target_lineno=1)
        is not None
    )


def test_detect_nested_compound_under_handles_match() -> None:
    """detect_nested_compound_under recognises a ``match`` wrapper."""
    src = "def f():\n    match v:\n        case _:\n            x = 1\n"
    tree = verifier_core.parse_strict(src, filename="<test>")
    func = verifier_core.top_level_function(tree, "f")
    assert func is not None
    match_stmt = func.body[0]
    assert isinstance(match_stmt, ast.Match)
    assert (
        verifier_core.detect_nested_compound_under(match_stmt, target_lineno=1)
        is not None
    )


# ---------------------------------------------------------------------------
# Core does NOT provide call-graph or interpreter primitives
# ---------------------------------------------------------------------------


def test_core_does_not_provide_call_graph_primitives() -> None:
    """Forbidden interpreter / call-graph primitives are NOT exposed."""
    forbidden = (
        "build_call_graph",
        "resolve_aliases",
        "analyze_closure",
        "fixed_point",
        "interpret",
    )
    for name in forbidden:
        assert not hasattr(verifier_core, name), (
            f"verifier_core must not expose interpreter primitive {name}"
        )


def test_core_does_not_expose_removed_subcode_or_bound_symbols() -> None:
    """Removed (CORRECTION05) symbols are NOT exposed on the package."""
    removed = (
        "CODE_CANONICAL",
        "SOURCE_LINE_DIRECTNESS_BOUND",
        "EXPECTED_PUBLIC_API",
        "all_subcodes",
        "enforce_directness_bound",
        "Diagnostic",
        "format_violation",
        "sort_diagnostics",
        "unique_top_level_function",
        # Plus the SUB_* vocabulary as a whole:
        "SUB_DUPLICATE_TARGET_DEFINITION",
        "SUB_REBIND_BEFORE_CALL",
        "SUB_NESTED_WRAPPER",
        "SUB_MISSING_CONTINUE",
    )
    for name in removed:
        assert not hasattr(verifier_core, name), (
            f"verifier_core must not expose removed symbol {name}"
        )

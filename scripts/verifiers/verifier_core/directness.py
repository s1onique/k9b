"""Direct-name and direct-call primitives.

This module owns the bounded helpers a verifier needs to detect
"this expression is a direct ``Name`` load of symbol X":

* :func:`is_direct_name` -- true when ``node`` is a direct-Name
  load of the given symbol. Attribute loads, subscripts, calls
  returning callables, ``getattr`` results are all NOT direct.
* :func:`is_simple_load` -- true for direct-Name OR direct
  attribute load.
* :func:`direct_name_from_load` -- returns the symbol name for
  direct-Name or first attribute ``a.b``.
* :func:`single_direct_name_call` -- first occurrence of a
  direct-Name call in source order at the TOP level of the
  supplied statement sequence. Does NOT descend into
  ``If.body``, ``Try.body``, ``for``/``while`` loops,
  ``with`` blocks, ``Match`` cases, nested function
  definitions, or any other compound statement.
* :func:`is_direct_name_call` -- public alias for
  :func:`single_direct_name_call` mandated by the
  canonical-syntax doctrine.
* :func:`kwargs_dict` -- returns the named subset of a call's
  keyword arguments.
* :func:`is_direct_call_to` -- true when ``call.func`` is a
  direct-Name load of the given symbol.

None of these primitives descend into nested scopes; they
inspect only the AST node they receive.

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence


def is_direct_name(node: ast.expr | None, name: str) -> bool:
    """True when ``node`` is a direct-Name load of ``name``.

    A direct-Name load is the canonical R20 shape; attribute
    loads, subscripts, calls returning callables, ``getattr``
    results, and similar are NOT direct-Name loads.
    """
    return (
        isinstance(node, ast.Name)
        and node.id == name
        and isinstance(node.ctx, ast.Load)
    )


def is_simple_load(node: ast.AST | None) -> bool:
    """True when ``node`` is a direct-Name or direct-Attribute load."""
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load)
    if isinstance(node, ast.Attribute):
        return isinstance(node.ctx, ast.Load)
    return False


def direct_name_from_load(node: ast.AST | None) -> str | None:
    """Return the loaded symbol name for direct-Name or first attr ``a.b``."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and isinstance(node.ctx, ast.Load)
    ):
        return node.attr
    return None


def single_direct_name_call(
    stmts: Sequence[ast.stmt], call_name: str
) -> ast.Call | None:
    """First occurrence of a direct-Name call at the top level of ``stmts``.

    The walk inspects ONLY the supplied statement sequence.
    It does NOT descend into ``If.body``, ``Try.body``,
    ``for`` / ``while`` / ``with`` body, ``Match`` case bodies,
    nested function definitions, lambdas, or any other
    compound statement. The consumer is expected to pass the
    exact statement sequence it wants inspected -- typically
    the canonical arm's direct body.

    Recognised top-level shapes (per-statement, in source order):

    * ``ast.Expr`` whose ``.value`` is an :class:`ast.Call`.
    * ``ast.Assign`` whose ``.value`` is an :class:`ast.Call`.
    * ``ast.AnnAssign`` whose ``.value`` is an :class:`ast.Call`.

    Returns the first matching :class:`ast.Call`, or ``None``.
    """
    for stmt in stmts:
        call = _direct_call_in_stmt(stmt, call_name)
        if call is not None:
            return call
    return None


def _direct_call_in_stmt(stmt: ast.stmt, call_name: str) -> ast.Call | None:
    """Return the direct-Name call in ``stmt`` if ``stmt`` is one of
    the recognised top-level shapes, otherwise ``None``.

    This helper intentionally does NOT descend into compound
    statements. If a consumer wants to inspect an explicitly
    selected canonical arm, it must pass that arm's direct
    body to :func:`single_direct_name_call`.
    """
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        if is_direct_name(stmt.value.func, call_name):
            return stmt.value
        return None
    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
        if is_direct_name(stmt.value.func, call_name):
            return stmt.value
        return None
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call):
        if is_direct_name(stmt.value.func, call_name):
            return stmt.value
        return None
    return None


def is_direct_name_call(
    stmts: Sequence[ast.stmt], call_name: str
) -> ast.Call | None:
    """Public alias for :func:`single_direct_name_call`.

    The canonical-syntax doctrine uses ``is_direct_name_call``;
    :func:`single_direct_name_call` is the underlying primitive.
    Both return the same :class:`ast.Call` node and obey the
    same bounded-walk contract (no descent into compound
    statements).
    """
    return single_direct_name_call(stmts, call_name)


def kwargs_dict(
    call: ast.Call, *names: str
) -> dict[str, ast.expr]:
    """Return the call's keyword arguments as a dict (only the named ones)."""
    out: dict[str, ast.expr] = {}
    for kw in call.keywords:
        if kw.arg is not None and kw.arg in names:
            out[kw.arg] = kw.value
    return out


def is_direct_call_to(
    call: ast.Call, name: str
) -> bool:
    """True when ``call.func`` is a direct ``Name``-load of ``name``."""
    return is_direct_name(call.func, name)


__all__ = (
    "is_direct_name",
    "is_simple_load",
    "direct_name_from_load",
    "single_direct_name_call",
    "is_direct_name_call",
    "kwargs_dict",
    "is_direct_call_to",
)
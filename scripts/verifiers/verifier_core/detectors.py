"""Forbidden-shape structural detectors (purely structural, no call graph).

This module owns every "look for this bad shape inside a function
body" detector. Each detector is purely structural -- it does not
build a call graph, track alias flow, or resolve closures.

Public API:

* :func:`statement_value` -- bounded extractor for the immediate
  expression owned by a statement.
* :func:`detect_partial_application` -- syntactic protected-name
  rejection: every direct call named ``partial`` is rejected,
  regardless of how it was bound.
* :func:`detect_dynamic_getattr` -- bounded check for direct
  ``getattr(...)`` statements (4 forms).
* :func:`detect_star_expansion` -- bounded check for ``*args`` or
  ``**kwargs`` inside a single call.
* :func:`detect_nested_defs` -- bounded ``FunctionDef`` /
  ``AsyncFunctionDef`` check.
* :func:`detect_lambdas` -- bounded ``Lambda`` check.
* :func:`detect_nested_compound_under` -- bounded check for
  compound statements wrapping an authoritative append site.
* :func:`is_callable_collection_literal` -- bounded check for
  ``[a, b, c]``-style collection of Names.

The earlier draft of this module declared
:func:`enforce_directness_bound` and the
``SOURCE_LINE_DIRECTNESS_BOUND`` constant. Both have been
removed because the canonical R20 chain lives entirely
inside one function body, so the bound is intentionally not
enforced (the canonical grammar is bounded by grammar, not by
line count). Future detectors that need a line-distance
budget can re-introduce the helper with a real consumer.

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from .diagnostics import SourceLocation, location_of
from .directness import is_direct_name

# ---------------------------------------------------------------------------
# Statement-value extraction (R2)
# ---------------------------------------------------------------------------


def statement_value(stmt: ast.stmt) -> ast.expr | None:
    """Return the immediate expression owned by ``stmt``, or ``None``.

    Supported statement shapes:

    * ``ast.Expr`` -- ``.value``
    * ``ast.Assign`` -- ``.value``
    * ``ast.AnnAssign`` -- ``.value``
    * ``ast.Return`` -- ``.value``

    For all other statement shapes (including ``ast.If``,
    ``ast.For``, ``ast.While``, ``ast.Try``, ``ast.With``,
    ``ast.Match``, ``ast.FunctionDef``, ``ast.AsyncFunctionDef``,
    ``ast.Lambda``, ``ast.ClassDef``, ``ast.Import``,
    ``ast.ImportFrom``, ``ast.Raise``, ``ast.Assert``, ...),
    this returns ``None``. The detector MUST NOT descend into
    compound statements; consumers that want to inspect a
    specific canonical arm pass the arm's direct body
    themselves via :func:`directness.single_direct_name_call`.

    This bounded extractor is the single policy-free helper
    every detector uses to read the immediate RHS of a
    statement. No detector should access ``.value`` directly.
    """
    if isinstance(stmt, (ast.Expr, ast.Assign, ast.Return)):
        return stmt.value
    if isinstance(stmt, ast.AnnAssign):
        return stmt.value
    return None


# ---------------------------------------------------------------------------
# Partial application detector (R4: Option A — purely syntactic)
# ---------------------------------------------------------------------------


def detect_partial_application(
    body: Sequence[ast.stmt],
) -> SourceLocation | None:
    """Return the first ``partial(...)`` call location in ``body``.

    Option A contract (selected per Correction03 R4): the
    detector is purely syntactic and rejects every direct call
    named ``partial``, regardless of how the name was bound
    (module attribute, bare import, locally defined). The
    detector does NOT track imports.

    Walks the body linearly (no ``ast.walk``) and inspects each
    statement's immediate expression via :func:`statement_value`.
    Returns the location of the first detected direct-Name
    ``partial`` call.
    """
    for stmt in body:
        value = statement_value(stmt)
        if value is None or not isinstance(value, ast.Call):
            continue
        if is_direct_name(value.func, "partial"):
            return location_of(value)
    return None


# ---------------------------------------------------------------------------
# Dynamic-getattr detector (R2)
# ---------------------------------------------------------------------------


def detect_dynamic_getattr(body: Sequence[ast.stmt]) -> SourceLocation | None:
    """Return the first direct ``getattr(...)`` call location in ``body``.

    Option A contract (matching R4): the detector recognises
    four statement shapes for the bare built-in
    :func:`getattr`:

    1. Bare expression: ``getattr(module, "dispatch")`` (an
       :class:`ast.Expr` statement).
    2. Plain assignment: ``invoke = getattr(module, "dispatch")``
       (an :class:`ast.Assign` statement whose value is the
       call).
    3. Annotated assignment:
       ``invoke: Callable[..., object] = getattr(module, "dispatch")``
       (an :class:`ast.AnnAssign` statement whose value is
       the call).
    4. Return statement: ``return getattr(module, "dispatch")``.

    Each is detected via :func:`statement_value`. The detector
    is NOT confused by attribute access whose attribute is
    named ``getattr`` (e.g. ``mod.getattr(...)``); such a
    call is NOT a call to the built-in ``getattr`` and is
    outside this detector's policy surface. If a future
    doctrine chooses to reject every method named ``getattr``,
    that is a SEPARATE detector and is intentionally not
    conflated with this one.
    """
    for stmt in body:
        value = statement_value(stmt)
        if value is None or not isinstance(value, ast.Call):
            continue
        if is_direct_name(value.func, "getattr"):
            return location_of(value)
    return None


# ---------------------------------------------------------------------------
# Star-expansion detector (R2)
# ---------------------------------------------------------------------------


def detect_star_expansion(call: ast.Call) -> SourceLocation | None:
    """Return the first ``*args``/``**kwargs`` location inside ``call``."""
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            return location_of(arg)
    for kw in call.keywords:
        if kw.arg is None:
            return location_of(kw.value)
    return None


# ---------------------------------------------------------------------------
# Nested-def / lambda detectors
# ---------------------------------------------------------------------------


def detect_nested_defs(body: Sequence[ast.stmt]) -> list[SourceLocation]:
    """Locations of every ``FunctionDef`` / ``AsyncFunctionDef`` in
    ``body`` (top-level only -- does NOT descend into ``if`` etc.).
    """
    out: list[SourceLocation] = []
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(location_of(stmt))
    return out


def detect_lambdas(body: Sequence[ast.stmt]) -> list[SourceLocation]:
    """Locations of every ``Lambda`` at the top level of ``body``.

    Bounded: does NOT descend into ``if`` arms.
    """
    out: list[SourceLocation] = []
    for stmt in body:
        value = statement_value(stmt)
        if isinstance(value, ast.Lambda):
            out.append(location_of(value))
    return out


# ---------------------------------------------------------------------------
# Compound-under detector (R1)
# ---------------------------------------------------------------------------


def _child_linenos(child_seq: Sequence[ast.stmt] | None) -> list[int]:
    """Return a list of linenos for each child in ``child_seq``."""
    if not child_seq:
        return []
    return [getattr(c, "lineno", 0) for c in child_seq]


def detect_nested_compound_under(
    parent: ast.stmt, target_lineno: int
) -> SourceLocation | None:
    """Return the first non-canonical compound nested under ``parent``
    whose body contains a statement at or after ``target_lineno``.

    A "non-canonical compound" is any statement that wraps another
    statement. The canonical R20 chain forbids placing an
    authoritative append inside any of the recognised wrappers.

    Recognised parent types and the fields they inspect:

    * ``ast.Try`` / ``ast.TryStar`` -- ``body``, every handler
      body's statements, ``orelse``, ``finalbody``.
    * ``ast.For`` / ``ast.AsyncFor`` / ``ast.While`` -- ``body``,
      ``orelse``.
    * ``ast.With`` / ``ast.AsyncWith`` -- ``body`` only. These
      nodes have no ``orelse`` field; accessing it would raise
      :class:`AttributeError`.
    * ``ast.If`` -- ``body``, ``orelse``.
    * ``ast.Match`` -- every case's ``body`` (a single
      :class:`ast.MatchCase` per pattern).

    Returns ``None`` when no recognised child sits at or after
    ``target_lineno``. Returns ``location_of(parent)`` at the
    first hit.
    """
    fields: list[Sequence[ast.stmt]] = []
    if isinstance(parent, (ast.Try, ast.TryStar)):
        fields.append(parent.body)
        for handler in parent.handlers:
            fields.append(handler.body)
        fields.append(parent.orelse)
        fields.append(parent.finalbody)
    elif isinstance(parent, (ast.For, ast.AsyncFor, ast.While)):
        fields.append(parent.body)
        fields.append(parent.orelse)
    elif isinstance(parent, (ast.With, ast.AsyncWith)):
        # With / AsyncWith have NO orelse field; body only.
        fields.append(parent.body)
    elif isinstance(parent, ast.If):
        fields.append(parent.body)
        fields.append(parent.orelse)
    elif isinstance(parent, ast.Match):
        for case in parent.cases:
            fields.append(case.body)
    else:
        return None

    for child_seq in fields:
        for lineno in _child_linenos(child_seq):
            if lineno >= target_lineno:
                return location_of(parent)
    return None


# ---------------------------------------------------------------------------
# Callable collection literal detector
# ---------------------------------------------------------------------------


def is_callable_collection_literal(
    node: ast.expr,
) -> bool:
    """True when ``node`` is a non-empty literal list/tuple/dict of Names.

    Empty ``refs: list[T] = []`` is the canonical accumulator
    initializer and must NOT be reported.
    """
    if isinstance(node, (ast.List, ast.Tuple)):
        if not node.elts:
            return False
        return all(_looks_like_callable_ref(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        if node.keys is None or node.values is None:
            return False
        if not node.keys:
            return False
        if not all(_looks_like_callable_ref(k) for k in node.keys):
            return False
        return all(_looks_like_callable_ref(v) for v in node.values)
    return False


def _looks_like_callable_ref(node: ast.AST | None) -> bool:
    """Conservative ``looks like a named function`` check."""
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return True
    return False


__all__ = (
    "statement_value",
    "detect_partial_application",
    "detect_dynamic_getattr",
    "detect_star_expansion",
    "detect_nested_defs",
    "detect_lambdas",
    "detect_nested_compound_under",
    "is_callable_collection_literal",
)

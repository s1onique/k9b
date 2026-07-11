"""Module-scope walrus (``ast.NamedExpr``) rebinding walker.

R17 invariant: an ``ast.NamedExpr`` target at module scope
introduces a name binding. ``(NewType := fake.NewType)``,
``if (str := int):``, module-level comprehensions like
``[x for x in (y := iter)]``, ``with (ctx := mgr):``, and
``if (NewType := fake.NewType):`` (the walrus expression itself)
all rebind names at the enclosing module scope. None of the
construct targets covered by :mod:`_llm_safe_alias_rebindings`
captures walrus operators because Python stores the target
identifier as a synthetic ``NamedExpr`` node that does not match
the ``ast.Assign``/``AnnAssign``/``For.target``/``withitem.optional_vars``
forms the existing helpers inspect.

R17 closes that gap by walking the module body and recursively
descending into control-flow bodies, while stopping at function
and class scopes because walrus targets inside them bind to the
enclosing function/class scope, not module scope.

R18 closure extends coverage to all module-scope expression
contexts that R17 missed:

* ``AugAssign.value``
* ``Assert.test``
* ``Raise.exc`` and ``Raise.cause``
* ``Match.subject``
* ``except`` handler type expressions
* ``FunctionDef`` defaults and decorators
* ``AsyncFunctionDef`` defaults and decorators
* ``ClassDef`` bases, keywords, and decorators
* lambda defaults (lambda bodies remain a scope boundary)

R19 closure inspects the remaining annotation contexts:

* ``AnnAssign.annotation``
* ``FunctionDef``/``AsyncFunctionDef`` parameter annotations
  (positional-only, positional, ``*args``, keyword-only,
  ``**kwargs``, and the ``return`` annotation)
* lambda default expressions explicitly (positional and
  keyword-only), distinct from the implicit pass-through in R18

Annotations execute at module scope by default (no
``__future__`` ``annotations`` import is present in the canonical
module), so a walrus in any of these positions binds a name at
module scope. ``__future__`` annotations would defer evaluation,
but the canonical module does not enable that import.

Public surface:

* :func:`scan_module_scope_named_expr_rebindings` - emit diagnostics
  for every module-scope walrus target in
  :data:`CANONICAL_ALIAS_SENSITIVE_NAMES` or
  :data:`PROVENANCE_SENSITIVE_NAMES`.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_ALIAS_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    PROVENANCE_SENSITIVE_NAMES,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    _iter_target_names,
)


def _is_function_or_class_scope(node: ast.AST) -> bool:
    """Return ``True`` for ``FunctionDef``/``AsyncFunctionDef``/``ClassDef``."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def _iter_arg_annotations(args: ast.arguments) -> Iterator[ast.expr]:
    """Yield every annotation expression attached to ``args``.

    Covers positional-only, positional, keyword-only, vararg
    (``*args``), and kwarg (``**kwargs``) annotations. Annotations
    evaluate at module scope by default when the ``def``/``async def``
    statement executes; a walrus in any of them rebinds the
    enclosing module-level name.
    """
    for arg in args.posonlyargs:
        if arg.annotation is not None:
            yield arg.annotation
    for arg in args.args:
        if arg.annotation is not None:
            yield arg.annotation
    if args.vararg is not None and args.vararg.annotation is not None:
        yield args.vararg.annotation
    for arg in args.kwonlyargs:
        if arg.annotation is not None:
            yield arg.annotation
    if args.kwarg is not None and args.kwarg.annotation is not None:
        yield args.kwarg.annotation


def _iter_def_default_exprs(args: ast.arguments) -> Iterator[ast.expr]:
    """Yield default-expression slots of a function's ``arguments``.

    Walrus in any of these executes in the module namespace when
    the ``def``/``async def`` evaluates.
    """
    yield from args.defaults
    for default in args.kw_defaults:
        if default is not None:
            yield default


def _iter_function_header_exprs(
    defn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    """Yield module-scope expressions inside a ``def``/``async def`` header.

    Walrus in any of the following rebinds at module scope:

    * decorator expressions
    * parameter defaults
    * parameter annotations (positional-only, positional,
      ``*args``, keyword-only, ``**kwargs``)
    * the ``return`` annotation
    """
    yield from defn.decorator_list
    yield from _iter_def_default_exprs(defn.args)
    yield from _iter_arg_annotations(defn.args)
    if defn.returns is not None:
        yield defn.returns


def _iter_class_header_exprs(defn: ast.ClassDef) -> Iterator[ast.AST]:
    """Yield module-scope expressions inside a ``class`` header."""
    yield from defn.decorator_list
    yield from defn.bases
    yield from defn.keywords


def _iter_named_exprs_in_expr(expr: ast.AST) -> Iterator[ast.NamedExpr]:
    """Iterate every ``ast.NamedExpr`` inside ``expr`` that binds at module scope.

    Unlike ``ast.walk``, this walker does NOT descend into:

    * ``FunctionDef``/``AsyncFunctionDef``/``ClassDef`` bodies, because
      walrus targets inside them bind to the enclosing function/class
      scope.
    * ``Lambda`` bodies, because per PEP 572 walrus targets inside a
      lambda body bind to the lambda's own scope.

    It DOES descend into lambda default expressions (``args.defaults``
    and ``args.kw_defaults``) because those evaluate at the
    enclosing module scope when the lambda default is computed.

    ``expr`` itself is always included in the walk; only its
    *children* are checked for scope boundaries.
    """
    yield from _iter_named_exprs(expr, in_lambda_body=False)


def _iter_named_exprs(
    node: ast.AST,
    *,
    in_lambda_body: bool,
) -> Iterator[ast.NamedExpr]:
    """Recursive scope-respecting helper for :func:`_iter_named_exprs_in_expr`."""
    if isinstance(node, ast.NamedExpr):
        yield node
        yield from _iter_named_exprs(node.value, in_lambda_body=in_lambda_body)
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Function/class scope boundary. Do not descend into the body.
        return
    if in_lambda_body and isinstance(node, ast.Lambda):
        # Nested lambda inside the body of an outer lambda is itself a
        # new scope; do not descend.
        return
    if isinstance(node, ast.Lambda):
        # ``node`` is a lambda. The body is a scope boundary; the
        # parameter DEFAULT expressions are NOT (per PEP 572 they
        # evaluate in the enclosing scope), so we walk those.
        for default in _iter_def_default_exprs(node.args):
            yield from _iter_named_exprs(default, in_lambda_body=False)
        return
    for child in ast.iter_child_nodes(node):
        if isinstance(node, ast.Lambda) and child is node.body:
            continue
        yield from _iter_named_exprs(child, in_lambda_body=False)


def _iter_module_scope_exprs(stmt: ast.stmt) -> Iterator[ast.AST]:
    """Yield expression nodes of ``stmt`` that execute at module scope.

    The walrus walker iterates the result and emits diagnostics for
    any ``NamedExpr`` target it finds.
    """
    if isinstance(stmt, ast.Expr):
        yield stmt.value
    elif isinstance(stmt, ast.Assign):
        yield stmt.value
    elif isinstance(stmt, ast.AnnAssign):
        # R19: annotation expressions evaluate at module scope when
        # the statement executes (no ``__future__`` ``annotations``
        # import in the canonical module).
        if stmt.annotation is not None:
            yield stmt.annotation
        if stmt.value is not None:
            yield stmt.value
    elif isinstance(stmt, ast.AugAssign):
        yield stmt.value
    elif isinstance(stmt, ast.Assert):
        yield stmt.test
        if stmt.msg is not None:
            yield stmt.msg
    elif isinstance(stmt, ast.Raise):
        if stmt.exc is not None:
            yield stmt.exc
        if stmt.cause is not None:
            yield stmt.cause
    elif isinstance(stmt, ast.If):
        yield stmt.test
    elif isinstance(stmt, ast.While):
        yield stmt.test
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        yield stmt.iter
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            yield item.context_expr
    elif isinstance(stmt, ast.Match):
        yield stmt.subject
        for case in stmt.cases:
            if case.guard is not None:
                yield case.guard
            yield case.pattern
    elif isinstance(stmt, (ast.Try, ast.TryStar)):
        for handler in stmt.handlers:
            if handler.type is not None:
                yield handler.type
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _iter_function_header_exprs(stmt)
    elif isinstance(stmt, ast.ClassDef):
        yield from _iter_class_header_exprs(stmt)


def _walk_stmt_module(stmts: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield statements at module scope, recursing into control flow.

    Function/class *headers* are yielded because their defaults,
    decorators, and annotations execute at module scope; their
    bodies are NOT recursed into.
    """
    for stmt in stmts:
        if _is_function_or_class_scope(stmt):
            yield stmt
            continue
        yield stmt
        if isinstance(stmt, ast.If):
            yield from _walk_stmt_module(stmt.body)
            yield from _walk_stmt_module(stmt.orelse)
        elif isinstance(stmt, ast.While):
            yield from _walk_stmt_module(stmt.body)
            yield from _walk_stmt_module(stmt.orelse)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            yield from _walk_stmt_module(stmt.body)
            yield from _walk_stmt_module(stmt.orelse)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            yield from _walk_stmt_module(stmt.body)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                yield from _walk_stmt_module(case.body)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            yield from _walk_stmt_module(stmt.body)
            for handler in stmt.handlers:
                yield from _walk_stmt_module(handler.body)
            yield from _walk_stmt_module(stmt.orelse)
            yield from _walk_stmt_module(stmt.finalbody)


def scan_module_scope_named_expr_rebindings(
    tree: ast.AST,
    filepath: str,
    errors: list[str],
) -> None:
    """Emit diagnostic for every module-scope walrus target on a sensitive name.

    R17/R18/R19 closure: any walrus assignment-expression that
    targets a canonical-sensitive OR provenance-sensitive name at
    module scope is forbidden. R19 adds coverage for annotation
    expressions (including lambda defaults) while preserving the
    R18 positive proof that walrus inside a lambda body is NOT a
    module-scope rebind (PEP 572).
    """
    for stmt in _walk_stmt_module(tree.body):
        for expr in _iter_module_scope_exprs(stmt):
            for named in _iter_named_exprs_in_expr(expr):
                for name in _iter_target_names(named.target):
                    if name in CANONICAL_ALIAS_SENSITIVE_NAMES:
                        errors.append(
                            f"{filepath}: module-scope walrus "
                            f"assignment-expression rebinds canonical-"
                            f"sensitive name '{name}' (R19 fail-closed). "
                            f"A walrus expression like ``({name} := ...)"
                            f"`` at module scope shadows a canonical "
                            f"alias or the builtin ``str``; remove the "
                            f"walrus or move it into a function/class "
                            f"body."
                        )
                    if name in PROVENANCE_SENSITIVE_NAMES:
                        errors.append(
                            f"{filepath}: module-scope walrus "
                            f"assignment-expression rebinds provenance-"
                            f"sensitive name '{name}' (R19 fail-closed). "
                            f"A walrus like ``({name} := ...)"
                            f"`` at module scope overwrites the trusted "
                            f"``typing`` or ``NewType`` import; remove "
                            f"the walrus."
                        )


__all__ = ["scan_module_scope_named_expr_rebindings"]

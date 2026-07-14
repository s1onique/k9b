"""Exception-source analyzer for SEAM01 promotion-diagnosis handoff verifier.

This module implements the recursive exception-source analyzer that emits
one snapshot per reachable potentially raising operation.  The canonical
exception-edge types (``Environment``, ``ExceptionPath``,
``SourceLocation``, ``ExceptionKind``) live in
:mod:`promotion_diagnosis_handoff_model` so there is a single canonical
definition referenced everywhere.

Import direction:
    promotion_diagnosis_handoff_model
        <- promotion_diagnosis_handoff_flow_exception_paths
            <- promotion_diagnosis_handoff_flow_try_canonical
                <- promotion_diagnosis_handoff_flow
                <- promotion_diagnosis_handoff_flow_tracking
                <- promotion_diagnosis_handoff_flow_try
                <- promotion_diagnosis_handoff_flow_loops

The boolean predicates ``_may_raise_expr`` / ``_stmt_may_raise`` are
non-authoritative filters used only to short-circuit clearly safe
operations.  Handler-entry environments come from
:func:`capture_exception_envs`, never from the boolean predicate.

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from promotion_diagnosis_handoff_model import Environment, Provenance

_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_model import (
    Environment,
    Provenance,
    ProvenanceKind,
    SourceLocation,
)

# Structural callable annotation.  The exception analyzer only relies
# on positional arguments; the structural signature is enforced by
# mypy for type clarity.
_TrackToTargetLine = Callable[
    [
        ast.AST | list[ast.stmt],
        "dict[str, Provenance]",
        int,
        int,
        str | None,
        bool,
    ],
    bool,
]

# ---------------------------------------------------------------------------
# Boolean predicates (non-authoritative filters only).
# ---------------------------------------------------------------------------


# Maximum iterations for loop exception-env fixed-point.
# Provenance is finite (UNSAFE/INCIDENT_PROMOTION_RESULT/CONST/etc.); a
# small cap is sufficient to converge at the ACT's level of detail.
MAX_LOOP_FIXED_POINT_ITERATIONS = 3


_RAISING_EXPR_TYPES = (
    ast.Call,
    ast.Attribute,
    ast.Subscript,
    ast.Yield,
    ast.YieldFrom,
    ast.Starred,
)


def _may_raise_expr(expr: ast.expr | None) -> bool:
    """Return True if evaluating ``expr`` may raise an exception.

    Conservative model used only as a filter.  The exact class of the
    exception is not inferred.  Unknown expressions are conservatively
    assumed to raise.
    """
    if expr is None:
        return False
    if isinstance(expr, _RAISING_EXPR_TYPES):
        return True
    if isinstance(expr, ast.BinOp):
        return _may_raise_expr(expr.left) or _may_raise_expr(expr.right)
    if isinstance(expr, ast.UnaryOp):
        return _may_raise_expr(expr.operand)
    if isinstance(expr, ast.Compare):
        return _may_raise_expr(expr.left) or any(
            _may_raise_expr(c) for c in expr.comparators
        )
    if isinstance(expr, ast.BoolOp):
        return any(_may_raise_expr(value) for value in expr.values)
    if isinstance(expr, ast.IfExp):
        return (
            _may_raise_expr(expr.test)
            or _may_raise_expr(expr.body)
            or _may_raise_expr(expr.orelse)
        )
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return any(_may_raise_expr(elt) for elt in expr.elts)
    if isinstance(expr, ast.Dict):
        return any(_may_raise_expr(k) for k in expr.keys if k is not None) or any(
            _may_raise_expr(v) for v in expr.values
        )
    if isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return _may_raise_expr(expr.elt) or any(
            _may_raise_expr(g.iter) for g in expr.generators
        )
    if isinstance(expr, ast.DictComp):
        return _may_raise_expr(expr.key) or _may_raise_expr(expr.value) or any(
            _may_raise_expr(g.iter) for g in expr.generators
        )
    if isinstance(expr, ast.Await):
        return _may_raise_expr(expr.value)
    if isinstance(
        expr, (ast.Name, ast.Constant, ast.FormattedValue, ast.JoinedStr)
    ):
        return False
    return True


def _stmt_may_raise(stmt: ast.stmt) -> bool:
    """Boolean classification used only as a non-authoritative filter.

    The precise exception analyzer emits a fresh snapshot per reachable
    operation via :func:`capture_exception_envs`.  Callers must NOT use
    this predicate to choose handler-entry environments.
    """
    if isinstance(stmt, ast.Expr):
        return _may_raise_expr(stmt.value)
    if isinstance(stmt, ast.Assign):
        return _may_raise_expr(stmt.value)
    if isinstance(stmt, ast.AnnAssign):
        return stmt.value is not None and _may_raise_expr(stmt.value)
    if isinstance(stmt, ast.AugAssign):
        return _may_raise_expr(stmt.value)
    if isinstance(stmt, ast.Raise):
        return True
    if isinstance(stmt, ast.Delete):
        return any(_may_raise_expr(t) for t in stmt.targets)
    if isinstance(stmt, ast.If):
        return (
            _may_raise_expr(stmt.test)
            or any(_stmt_may_raise(s) for s in stmt.body)
            or any(_stmt_may_raise(s) for s in stmt.orelse)
        )
    if isinstance(stmt, ast.While):
        return _may_raise_expr(stmt.test) or any(
            _stmt_may_raise(s) for s in stmt.body
        )
    if isinstance(stmt, ast.For):
        return _may_raise_expr(stmt.iter) or any(
            _stmt_may_raise(s) for s in stmt.body
        )
    if isinstance(stmt, ast.With):
        return any(_may_raise_expr(item.context_expr) for item in stmt.items) or any(
            _stmt_may_raise(s) for s in stmt.body
        )
    if isinstance(stmt, ast.Try):
        return any(_stmt_may_raise(s) for s in stmt.body) or any(
            any(_stmt_may_raise(s) for s in h.body) for h in stmt.handlers
        ) or any(_stmt_may_raise(s) for s in stmt.orelse)
    if isinstance(stmt, ast.Assert):
        return _may_raise_expr(stmt.test) or _may_raise_expr(stmt.msg)
    return False


def _source_location(node: ast.AST) -> SourceLocation:
    line = getattr(node, "lineno", 0) or 0
    column = getattr(node, "col_offset", 0) or 0
    return SourceLocation(line=line, column=column)


# ---------------------------------------------------------------------------
# Capture exception environments at every reachable operation.
# ---------------------------------------------------------------------------


def _capture_branch_exception_envs(
    stmts: list[ast.stmt],
    env: Environment,
    target_line: int,
    target_col: int,
    enclosing_return_type: str | None,
    is_classmethod: bool,
    _track_to_target_line: _TrackToTargetLine,
) -> list[Environment]:
    """Recursively capture exception envs for a list of statements.

    ``env`` is mutated to reflect the post-success state of each statement
    so callers can continue walking subsequent statements with the
    correct state.  This is shared logic for ``if`` branches and ``try``
    bodies.
    """
    envs: list[Environment] = []
    branch_env = dict(env)
    for sub in stmts:
        envs.extend(
            capture_exception_envs(
                sub,
                branch_env,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )
    return envs




def _iter_bound_names(target: Any) -> Iterator[str]:
    """Yield Name ids bound by a for-target or with-as-target.

    Handles bare Name, Tuple/List/Set (unpacking), Starred, Attribute,
    and Subscript targets.
    """
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List, ast.Set)):
        for elt in target.elts:
            yield from _iter_bound_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_bound_names(target.value)


def capture_exception_envs(
    stmt: ast.stmt,
    env: Environment,
    target_line: int,
    target_col: int,
    enclosing_return_type: str | None,
    is_classmethod: bool,
    _track_to_target_line: _TrackToTargetLine,
) -> list[Environment]:
    """Capture exception envs at every reachable operation inside ``stmt``.

    The function walks ``stmt`` recursively and returns a list of
    snapshots, one per reachable potentially raising operation.  ``env``
    is mutated to reflect the post-success state of ``stmt`` so the
    caller can continue walking subsequent statements.

    Compound statements (if/with/for/while/try) are descended into so
    the snapshots include branch-local assignments made earlier in that
    compound.  This is the canonical source of exception environments
    used by the canonical try analyzer; handlers must start from these
    snapshots, not from any pre-try or post-try state.
    """
    # Terminating statements do not produce user-code exception edges.
    if isinstance(stmt, (ast.Return, ast.Break, ast.Continue)):
        return []

    # Explicit raise: capture and stop.
    if isinstance(stmt, ast.Raise):
        return [dict(env)]

    # Simple statements whose only potentially raising surface is the
    # expression value.
    if isinstance(stmt, ast.Expr):
        return [dict(env)] if _may_raise_expr(stmt.value) else []

    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        value = getattr(stmt, "value", None)
        envs = [dict(env)] if _may_raise_expr(value) else []
        # Update env to the post-success state of this statement.
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return envs

    if isinstance(stmt, ast.Delete):
        return [dict(env)] if any(_may_raise_expr(t) for t in stmt.targets) else []

    if isinstance(stmt, ast.Assert):
        return (
            [dict(env)]
            if _may_raise_expr(stmt.test) or _may_raise_expr(stmt.msg)
            else []
        )

    # Compound statements: descend into both branches / body so branch-
    # local assignments are visible in the captured exception envs.
    if isinstance(stmt, ast.If):
        if_envs: list[Environment] = []  # noqa: F823
        if_envs.extend(
            _capture_branch_exception_envs(
                stmt.body,
                env,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )
        if stmt.orelse:
            if_envs.extend(
                _capture_branch_exception_envs(
                    stmt.orelse,
                    env,
                    target_line,
                    target_col,
                    enclosing_return_type,
                    is_classmethod,
                    _track_to_target_line,
                )
            )
        if _may_raise_expr(stmt.test):
            if_envs.append(dict(env))
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return if_envs

    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        # Process context items SEQUENTIALLY: each item's __enter__
        # can see the prior item's binding.  Apply the with-as target
        # after each successful entry before the next item is evaluated.
        envs = []
        body_env = dict(env)
        for item in stmt.items:
            if _may_raise_expr(item.context_expr):
                envs.append(dict(body_env))
            if item.optional_vars is not None:
                for bound_name in _iter_bound_names(item.optional_vars):
                    body_env[bound_name] = Provenance(provenance_kind=ProvenanceKind.UNKNOWN)
        envs.extend(
            _capture_branch_exception_envs(
                stmt.body,
                body_env,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return envs

    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        if isinstance(stmt, ast.AsyncFor):
            envs = [dict(env)] if _may_raise_expr(stmt.iter) else []
        else:
            envs = [dict(env)] if _may_raise_expr(stmt.iter) else []
        # Apply for-target binding before body walk: each iteration
        # rebinds stmt.target to the iterator value (UNSAFE).
        body_env = dict(env)
        for bound_name in _iter_bound_names(stmt.target):
            body_env[bound_name] = Provenance(provenance_kind=ProvenanceKind.UNKNOWN)
        envs.extend(
            _capture_branch_exception_envs(
                stmt.body,
                body_env,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return envs

    if isinstance(stmt, ast.While):
        envs = [dict(env)] if _may_raise_expr(stmt.test) else []
        envs.extend(
            _capture_branch_exception_envs(
                stmt.body,
                env,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return envs

    if isinstance(stmt, ast.Try):
        # Nested try: descend into the body with the same analyzer.  The
        # canonical try analyzer processes handlers / else / finally for
        # the nested try separately; the outer analyzer only needs the
        # raw exception envs that escape into the outer scope (the
        # nested try's handlers will catch most of these in practice).
        envs = _capture_branch_exception_envs(
            stmt.body,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
            _track_to_target_line,
        )
        _track_to_target_line(
            stmt,
            env,
            target_line,
            target_col,
            enclosing_return_type,
            is_classmethod,
        )
        return envs

    # Other statements (Pass, Import*, FunctionDef, ClassDef, ...) do not
    # contain potentially raising user expressions.
    return []
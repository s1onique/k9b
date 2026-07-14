"""Canonical try analyzer for SEAM01 promotion-diagnosis handoff verifier.

Architecture note (ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01):
- Handler-entry environments come from ``capture_exception_envs`` /
  ``capture_exception_envs_no_target``.  No Boolean heuristic.
- Loop wrappers source exception-env snapshots from these analyzers.
- FAST CONTAINMENT (delta-2): if a try body contains a loop whose
  body both (a) may raise and (b) mutates a relevant var, the analyzer
  demotes those vars to UNKNOWN in every exception env.  Demotion runs
  BEFORE each handler executes, so a sanitising assignment in one
  handler does NOT launder other handlers that don't sanitise the same
  var (delta-3 fix).  Conditional sanitisation also leaves UNKNOWN
  on the non-sanitising branch.

The mutation collector descends through nested compound statements
including try / finally / handlers / else, so mutations nested inside
a try in the loop body are still discovered (delta-4 fix).
"""
from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_exception_paths import (
    _may_raise_expr,
    capture_exception_envs,
)
from promotion_diagnosis_handoff_model import Provenance, ProvenanceKind, merge_paths


def _collect_assigned_names(targets: list[Any]) -> Iterator[str]:
    """Yield Name ids assigned by the given assignment targets list."""
    for t in targets:
        if isinstance(t, ast.Name):
            yield t.id


def _iter_bound_names(target: Any) -> Iterator[str]:
    """Recursively yield Name ids bound by a for-target or with-as-target.

    Handles bare Name, Tuple/List/Set (unpacking), Starred, Attribute,
    and Subscript targets.  Mirrors Python iterable unpacking.
    """
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List, ast.Set)):
        for elt in target.elts:
            yield from _iter_bound_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_bound_names(target.value)


def _walk_assigned_names(stmts: list[Any]) -> Iterator[str]:
    """Yield Name ids assigned in any of the given statements,
    descending through compound bodies INCLUDING nested try."""
    for stmt in stmts:
        if isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            if isinstance(target, ast.Name):
                yield target.id
        elif isinstance(stmt, ast.Assign):
            yield from _collect_assigned_names(stmt.targets)
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                yield stmt.target.id
        elif isinstance(stmt, ast.For):
            # For target binding happens before each iteration; include
            # it in the mutation set for containment.
            yield from _iter_bound_names(stmt.target)
            yield from _walk_assigned_names(stmt.body)
        elif isinstance(stmt, ast.AsyncFor):
            yield from _iter_bound_names(stmt.target)
            yield from _walk_assigned_names(stmt.body)
        elif isinstance(stmt, ast.While):
            yield from _walk_assigned_names(stmt.body)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            # With-as targets bind before the body executes.
            for item in stmt.items:
                if item.optional_vars is not None:
                    yield from _iter_bound_names(item.optional_vars)
            yield from _walk_assigned_names(stmt.body)
        elif isinstance(stmt, ast.If):
            yield from _walk_assigned_names(stmt.body)
            yield from _walk_assigned_names(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            # Nested try: the mutation can be in body, handlers, orelse,
            # or finalbody -- all carry state across iterations.
            yield from _walk_assigned_names(stmt.body)
            yield from _walk_assigned_names(stmt.finalbody)
            for handler in stmt.handlers:
                yield from _walk_assigned_names(handler.body)
            if stmt.orelse:
                yield from _walk_assigned_names(stmt.orelse)


def _find_loop_mutated_vars(body: list[Any]) -> set[str]:
    """Return Name ids assigned inside any for/while loop in body,
    descending through nested compound statements including try."""
    mutated: set[str] = set()

    def _walk(stmts: list[Any]) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.For, ast.AsyncFor)):
                # Recurse into loop body AND its own nested compounds,
                # and the loop target binding (for overwrites target).
                mutated.update(_iter_bound_names(stmt.target))
                mutated.update(_walk_assigned_names(stmt.body))
                _walk(stmt.body)
            elif isinstance(stmt, ast.While):
                mutated.update(_walk_assigned_names(stmt.body))
                _walk(stmt.body)
            elif isinstance(stmt, ast.Try):
                _walk(stmt.body)
                _walk(stmt.finalbody)
                for h in stmt.handlers:
                    _walk(h.body)
                if stmt.orelse:
                    _walk(stmt.orelse)
            elif isinstance(stmt, ast.If):
                _walk(stmt.body)
                _walk(stmt.orelse)
            elif isinstance(stmt, ast.With):
                _walk(stmt.body)

    _walk(body)
    return mutated


def _body_has_raise(body: list[Any]) -> bool:
    """True if any statement in body may raise."""
    for stmt in body:
        if _may_raise_expr(stmt):
            return True
        if isinstance(stmt, ast.If):
            if _body_has_raise(stmt.body):
                return True
            if _body_has_raise(stmt.orelse):
                return True
        elif isinstance(stmt, (ast.For, ast.While)):
            if _body_has_raise(stmt.body):
                return True
        elif isinstance(stmt, ast.With):
            if _body_has_raise(stmt.body):
                return True
        elif isinstance(stmt, ast.Try):
            if _body_has_raise(stmt.body):
                return True
    return False


def analyze_try_to_target(
    node: Any,
    prov: dict[str, Any],
    target_line: int,
    target_col: int,
    enclosing_return_type: Any,
    is_classmethod: bool,
    _track_to_target_line: Any,
) -> None:
    """Canonical try analyzer used by the flow-target tracker."""
    exception_envs: list[Any] = []
    for body_stmt in node.body:
        body_line = getattr(body_stmt, "lineno", None)
        if body_line is not None and body_line > target_line:
            break
        exception_envs.extend(
            capture_exception_envs(
                body_stmt,
                prov,
                target_line,
                target_col,
                enclosing_return_type,
                is_classmethod,
                _track_to_target_line,
            )
        )

    if node.orelse:
        for else_stmt in node.orelse:
            else_line = getattr(else_stmt, "lineno", None)
            if else_line is not None and else_line > target_line:
                break
            _track_to_target_line(
                else_stmt, prov, target_line, target_col,
                enclosing_return_type, is_classmethod,
            )

    # FAST CONTAINMENT: demote loop-mutated vars BEFORE handler analysis.
    # Each handler runs independently from a demoted (UNKNOWN) env, so
    # a sanitising-assignment in one handler does NOT exempt the others
    # that don't sanitise the same variable.  Conditional sanitisation
    # in a handler also leaves UNKNOWN along the non-sanitising branch.
    if _body_has_raise(node.body):
        containment_vars = _find_loop_mutated_vars(node.body)
        if containment_vars:
            for exc_env in exception_envs:
                for var_name in containment_vars:
                    exc_env[var_name] = Provenance(
                        provenance_kind=ProvenanceKind.UNKNOWN,
                    )

    handler_results: list[Any] = []
    for handler in node.handlers:
        if not exception_envs:
            continue
        for exc_env in exception_envs:
            handler_env = cast(dict[str, Any], dict(exc_env))
            for handler_stmt in handler.body:
                hs_line = getattr(handler_stmt, "lineno", None)
                if hs_line is not None and hs_line > target_line:
                    break
                _track_to_target_line(
                    handler_stmt,
                    handler_env,
                    target_line,
                    target_col,
                    enclosing_return_type,
                    is_classmethod,
                )
            handler_results.append(handler_env)

    all_paths: list[Any] = [prov] + handler_results
    merged = merge_paths(all_paths)
    prov.clear()
    prov.update(merged)

    for final_stmt in node.finalbody:
        fs_line = getattr(final_stmt, "lineno", None)
        if fs_line is not None and fs_line > target_line:
            break
        _track_to_target_line(
            final_stmt, prov, target_line, target_col,
            enclosing_return_type, is_classmethod,
        )


def analyze_try_in_sequence(
    node: Any,
    prov: dict[str, Any],
    enclosing_return_type: Any,
    is_classmethod: bool,
    _track_statement: Any,
) -> None:
    """Canonical try analyzer used by the recursive ``_track_statement``."""
    exception_envs: list[Any] = []
    for body_stmt in node.body:
        sub_envs, _sub_term = capture_exception_envs_no_target(
            body_stmt, prov,
            enclosing_return_type, is_classmethod, _track_statement,
        )
        exception_envs.extend(sub_envs)

    if node.orelse:
        for else_stmt in node.orelse:
            _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)

    if _body_has_raise(node.body):
        containment_vars = _find_loop_mutated_vars(node.body)
        if containment_vars:
            for exc_env in exception_envs:
                for var_name in containment_vars:
                    exc_env[var_name] = Provenance(
                        provenance_kind=ProvenanceKind.UNKNOWN,
                    )

    handler_results: list[Any] = []
    for handler in node.handlers:
        if not exception_envs:
            continue
        for exc_env in exception_envs:
            handler_env = cast(dict[str, Any], dict(exc_env))
            for handler_stmt in handler.body:
                _track_statement(handler_stmt, handler_env, enclosing_return_type, is_classmethod)
            handler_results.append(handler_env)

    all_paths: list[Any] = [prov] + handler_results
    merged = merge_paths(all_paths)
    prov.clear()
    prov.update(merged)

    for final_stmt in node.finalbody:
        _track_statement(final_stmt, prov, enclosing_return_type, is_classmethod)


def capture_exception_envs_no_target(
    stmt: Any,
    env: Any,
    enclosing_return_type: Any,
    is_classmethod: bool,
    _track_statement: Any,
) -> tuple[list[Any], str | None]:
    """Target-less variant returning (envs, terminator)."""
    envs: list[Any] = []
    if isinstance(stmt, ast.Expr):
        if _may_raise_expr(stmt.value):
            envs.append(cast(dict[str, Any], dict(env)))
        return envs, None
    if isinstance(stmt, ast.Raise):
        envs.append(cast(dict[str, Any], dict(env)))
        return envs, "raise"
    if isinstance(stmt, (ast.Return, ast.Break, ast.Continue)):
        return envs, stmt.__class__.__name__.lower()
    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        value = getattr(stmt, "value", None)
        if _may_raise_expr(value):
            envs.append(cast(dict[str, Any], dict(env)))
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        return envs, None
    if isinstance(stmt, ast.If):
        body_env = cast(dict[str, Any], dict(env))
        for body_stmt in stmt.body:
            sub_envs, _ = capture_exception_envs_no_target(
                body_stmt, body_env,
                enclosing_return_type, is_classmethod, _track_statement,
            )
            envs.extend(sub_envs)
        if stmt.orelse:
            else_env = cast(dict[str, Any], dict(env))
            for else_stmt in stmt.orelse:
                sub_envs, _ = capture_exception_envs_no_target(
                    else_stmt, else_env,
                    enclosing_return_type, is_classmethod, _track_statement,
                )
                envs.extend(sub_envs)
        if _may_raise_expr(stmt.test):
            envs.append(cast(dict[str, Any], dict(env)))
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        return envs, None
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        # Process context items SEQUENTIALLY: each item's __enter__ can
        # see the prior item's binding.  Apply the with-as target for
        # the current item before the next item is evaluated.
        body_env = cast(dict[str, Any], dict(env))
        for item in stmt.items:
            if _may_raise_expr(item.context_expr):
                envs.append(cast(dict[str, Any], dict(body_env)))
            if item.optional_vars is not None:
                for bound_name in _iter_bound_names(item.optional_vars):
                    body_env[bound_name] = Provenance(provenance_kind=ProvenanceKind.UNKNOWN)
        for body_stmt in stmt.body:
            sub_envs, _ = capture_exception_envs_no_target(
                body_stmt, body_env,
                enclosing_return_type, is_classmethod, _track_statement,
            )
            envs.extend(sub_envs)
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        return envs, None
    if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
        if isinstance(stmt, ast.AsyncFor):
            if _may_raise_expr(stmt.iter):
                envs.append(cast(dict[str, Any], dict(env)))
        elif isinstance(stmt, ast.For) and _may_raise_expr(stmt.iter):
            envs.append(cast(dict[str, Any], dict(env)))
        if isinstance(stmt, ast.While) and _may_raise_expr(stmt.test):
            envs.append(cast(dict[str, Any], dict(env)))
        body_env = cast(dict[str, Any], dict(env))
        # Apply for-target binding: For/AsyncFor rebind stmt.target to
        # each iterator value before the body executes (Python semantics:
        # the target is assigned before the suite runs each iteration).
        # While has no target attribute.  Model the binding as UNKNOWN so
        # any body exception is captured against the for-target value
        # at that iteration, which is what makes the loop-backedge
        # snapshot a full env rather than a partial one.
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            for bound_name in _iter_bound_names(stmt.target):
                body_env[bound_name] = Provenance(provenance_kind=ProvenanceKind.UNKNOWN)
        for body_stmt in stmt.body:
            sub_envs, _ = capture_exception_envs_no_target(
                body_stmt, body_env,
                enclosing_return_type, is_classmethod, _track_statement,
            )
            envs.extend(sub_envs)
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        return envs, None
    if isinstance(stmt, ast.Try):
        body_env = cast(dict[str, Any], dict(env))
        for body_stmt in stmt.body:
            sub_envs, _ = capture_exception_envs_no_target(
                body_stmt, body_env,
                enclosing_return_type, is_classmethod, _track_statement,
            )
            envs.extend(sub_envs)
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        return envs, None
    return envs, None


__all__ = [
    "analyze_try_to_target",
    "analyze_try_in_sequence",
    "capture_exception_envs_no_target",
]

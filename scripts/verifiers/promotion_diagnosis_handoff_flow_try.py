"""Try orchestration and compatibility wrappers for SEAM01 promotion-diagnosis handoff verifier.

This module is the small orchestration entry point for try processing.
It hosts two compatibility wrappers used by loop body analysis
(``process_try_body`` and ``process_try_for_continue``) plus
re-exports for the break helpers that now live in
:mod:`promotion_diagnosis_handoff_flow_try_break`.

The canonical analyzer (precise exception environments, handler
alternatives, clean-only ``else``, exactly-once ``finally``) lives in
:mod:`promotion_diagnosis_handoff_flow_try_canonical`.  This module
remains the single seam the loop analyzer imports from.

Import direction:
    promotion_diagnosis_handoff_model
        <- promotion_diagnosis_handoff_flow_tracking
            <- promotion_diagnosis_handoff_flow_try_break (break helpers)
            <- promotion_diagnosis_handoff_flow_try_continue (continue helpers)
                <- promotion_diagnosis_handoff_flow_try (this module)
                    <- promotion_diagnosis_handoff_flow_loops

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_exception_paths import _stmt_may_raise  # noqa: F401  (retained only for non-authoritative diagnostics)
from promotion_diagnosis_handoff_flow_tracking import _track_statement

# Break helpers live in their own module.  Re-export here so callers
# that previously imported ``_process_stmt_for_break`` etc. from this
# module continue to work.
from promotion_diagnosis_handoff_flow_try_break import (  # noqa: F401
    _contains_break_in_stmt,
    _process_stmt_for_break,
    _process_stmt_for_break_nested,
    process_try_for_break,
)
from promotion_diagnosis_handoff_flow_try_canonical import capture_exception_envs_no_target
from promotion_diagnosis_handoff_flow_try_continue import (
    FlowResult,
    _contains_continue_in_stmt,
    _process_stmt_for_continue,
)
from promotion_diagnosis_handoff_model import Provenance


def _apply_finally(
    env: dict[str, Provenance],
    finalbody: list[ast.stmt],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> dict[str, Provenance]:
    """Apply ``finally`` suite to a single environment, returning a copy."""
    finalized = dict(env)
    if finalbody:
        for stmt in finalbody:
            _track_statement(stmt, finalized, enclosing_return_type, is_classmethod)
    return finalized


def process_try_body(
    try_stmt: ast.Try,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> list[dict[str, Provenance]]:
    """Process try body without break / continue handling.

    Used by loop body analysis.  Captures exception envs at every
    reachable operation inside the try body via
    :func:`promotion_diagnosis_handoff_flow_exception_paths._stmt_may_raise`
    (used here only as a filter; handler-entry environments are the
    captured snapshots).  Handlers are alternatives that start from
    each captured exception env.

    Returns the union of clean-normal completion paths and every
    handler-completion path, each transformed by ``finally`` exactly
    once at a common boundary.
    """
    normal_env = dict(env)
    exception_envs: list[dict[str, Provenance]] = []

    for stmt in try_stmt.body:
        # CANONICAL exception-env capture: emit one snapshot per reachable
        # operation (descending into compound statements so branch-local
        # state is reflected).  Walk a COPY of normal_env so this snapshot
        # pass does not disturb the post-success state used by the
        # _track_statement call below.  Handler-entry environments come
        # from these snapshots, never from `_stmt_may_raise`.
        env_copy = dict(normal_env)
        sub_envs, _sub_term = capture_exception_envs_no_target(
            stmt, env_copy, enclosing_return_type, is_classmethod,
            _track_statement,
        )
        exception_envs.extend(sub_envs)

        term = _track_statement(stmt, normal_env, enclosing_return_type, is_classmethod)
        if term in ("break", "continue", "return", "raise"):
            break

    handler_paths: list[dict[str, Provenance]] = []
    for handler in try_stmt.handlers:
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            for stmt in handler.body:
                term = _track_statement(
                    stmt, handler_env, enclosing_return_type, is_classmethod
                )
                if term in ("break", "continue", "return", "raise"):
                    break
            handler_paths.append(handler_env)

    normal_paths = [normal_env] if normal_env else []
    for stmt in try_stmt.orelse:
        for np in normal_paths:
            _track_statement(stmt, np, enclosing_return_type, is_classmethod)

    if try_stmt.finalbody:
        all_paths = normal_paths + handler_paths
        return [
            _apply_finally(
                path, try_stmt.finalbody, enclosing_return_type, is_classmethod
            )
            for path in all_paths
        ]
    return normal_paths + handler_paths


def process_try_for_continue(
    try_stmt: ast.Try,
    continue_env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process try body for continue path.

    Returns a FlowResult.  Continues are routed through the inner
    ``finally`` exactly once.  Handlers are alternatives starting from
    each captured exception env.
    """
    result = FlowResult()
    exception_envs: list[dict[str, Provenance]] = []
    normal_envs: list[dict[str, Provenance]] = [dict(continue_env)]

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Continue):
            for env in normal_envs:
                result.continues.append(
                    _apply_finally(
                        env, try_stmt.finalbody, enclosing_return_type, is_classmethod
                    )
                )
            return result

        # CANONICAL exception-env capture for every reachable operation
        # across every active normal-env path.  Walk copies so downstream
        # continue-descent or _track_statement sees the original env state.
        for env in normal_envs:
            env_copy = dict(env)
            sub_envs, _sub_term = capture_exception_envs_no_target(
                stmt, env_copy, enclosing_return_type, is_classmethod,
                _track_statement,
            )
            exception_envs.extend(sub_envs)

        if _contains_continue_in_stmt(stmt):
            new_normal_envs: list[dict[str, Provenance]] = []
            for env in normal_envs:
                sub_result = _process_stmt_for_continue(
                    stmt, env, enclosing_return_type, is_classmethod
                )
                for cont_env in sub_result.continues:
                    result.continues.append(
                        _apply_finally(
                            cont_env,
                            try_stmt.finalbody,
                            enclosing_return_type,
                            is_classmethod,
                        )
                    )
                new_normal_envs.extend(sub_result.normal)
            normal_envs = new_normal_envs
        else:
            surviving_envs: list[dict[str, Provenance]] = []
            for env in normal_envs:
                term = _track_statement(
                    stmt, env, enclosing_return_type, is_classmethod
                )
                if term not in ("break", "return", "raise"):
                    surviving_envs.append(env)
            normal_envs = surviving_envs

    if try_stmt.orelse:
        for else_stmt in try_stmt.orelse:
            if _contains_continue_in_stmt(else_stmt):
                else_normals: list[dict[str, Provenance]] = []
                for env in normal_envs:
                    else_result = _process_stmt_for_continue(
                        else_stmt, env, enclosing_return_type, is_classmethod
                    )
                    for cont_env in else_result.continues:
                        result.continues.append(
                            _apply_finally(
                                cont_env,
                                try_stmt.finalbody,
                                enclosing_return_type,
                                is_classmethod,
                            )
                        )
                    else_normals.extend(else_result.normal)
                normal_envs = else_normals
            else:
                else_surviving: list[dict[str, Provenance]] = []
                for env in normal_envs:
                    term = _track_statement(
                        else_stmt, env, enclosing_return_type, is_classmethod
                    )
                    if term not in ("break", "continue", "return", "raise"):
                        else_surviving.append(env)
                normal_envs = else_surviving

    try_body_normal_paths = list(normal_envs)
    handler_normal_paths: list[dict[str, Provenance]] = []

    if try_stmt.handlers and exception_envs:
        for handler in try_stmt.handlers:
            handler_envs: list[dict[str, Provenance]] = [
                dict(e) for e in exception_envs
            ]

            for stmt in handler.body:
                if isinstance(stmt, ast.Continue):
                    for env in handler_envs:
                        result.continues.append(
                            _apply_finally(
                                env,
                                try_stmt.finalbody,
                                enclosing_return_type,
                                is_classmethod,
                            )
                        )
                    handler_envs = []
                    break

                if _contains_continue_in_stmt(stmt):
                    new_handler_envs: list[dict[str, Provenance]] = []
                    for env in handler_envs:
                        sub_result = _process_stmt_for_continue(
                            stmt, env, enclosing_return_type, is_classmethod
                        )
                        for cont_env in sub_result.continues:
                            result.continues.append(
                                _apply_finally(
                                    cont_env,
                                    try_stmt.finalbody,
                                    enclosing_return_type,
                                    is_classmethod,
                                )
                            )
                        new_handler_envs.extend(sub_result.normal)
                    handler_envs = new_handler_envs
                else:
                    surviving: list[dict[str, Provenance]] = []
                    for env in handler_envs:
                        term = _track_statement(
                            stmt, env, enclosing_return_type, is_classmethod
                        )
                        if term not in ("break", "return", "raise"):
                            surviving.append(env)
                    handler_envs = surviving

            handler_normal_paths.extend(handler_envs)

    all_normal_paths = try_body_normal_paths + handler_normal_paths
    if all_normal_paths and try_stmt.finalbody:
        for path in all_normal_paths:
            result.normal.append(
                _apply_finally(
                    path, try_stmt.finalbody, enclosing_return_type, is_classmethod
                )
            )
    else:
        result.normal.extend(all_normal_paths)

    return result


__all__ = [
    "process_try_body",
    "process_try_for_continue",
    # Re-exports from the break module for backwards compatibility.
    "process_try_for_break",
    "_process_stmt_for_break",
    "_process_stmt_for_break_nested",
    "_contains_break_in_stmt",
]
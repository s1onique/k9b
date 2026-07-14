"""Break-path analysis for try statements in SEAM01 promotion-diagnosis handoff verifier.

This module hosts the break-related try-processing helpers used by loop
body analysis.  They are kept separate from
:mod:`promotion_diagnosis_handoff_flow_try` so the orchestration module
stays under the LLM-friendly threshold while keeping the specialised
loop-aware logic available to callers.

Import direction:
    promotion_diagnosis_handoff_model
        <- promotion_diagnosis_handoff_flow_tracking
            <- promotion_diagnosis_handoff_flow_try_break
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
from promotion_diagnosis_handoff_flow_try_canonical import capture_exception_envs_no_target
from promotion_diagnosis_handoff_model import FlowResult, Provenance


def _contains_break_in_stmt(stmt: ast.stmt) -> bool:
    """Check if a statement contains a break (including nested).

    Searcher respects loop-pruning: an inner loop's break does NOT count
    as a break for the outer loop.
    """
    if isinstance(stmt, ast.Break):
        return True
    if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return False
    if isinstance(stmt, (ast.For, ast.While)):
        return False
    if isinstance(stmt, ast.If):
        return any(_contains_break_in_stmt(s) for s in stmt.body) or any(
            _contains_break_in_stmt(s) for s in stmt.orelse
        )
    if isinstance(stmt, ast.With):
        return any(_contains_break_in_stmt(s) for s in stmt.body)
    if isinstance(stmt, ast.Try):
        return any(_contains_break_in_stmt(s) for s in stmt.body) or any(
            _contains_break_in_stmt(s) for h in stmt.handlers for s in h.body
        ) or any(_contains_break_in_stmt(s) for s in stmt.orelse) or any(
            _contains_break_in_stmt(s) for s in stmt.finalbody
        )
    return False


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


def _process_stmt_for_break(
    stmt: ast.stmt,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process a statement to find break paths.

    Returns a FlowResult with break paths captured.  Only ``normal`` and
    ``breaks`` are populated; other categories are routed through the
    broader canonical try analyzer in the loop-aware caller.
    """
    result = FlowResult()

    if isinstance(stmt, ast.Break):
        result.breaks.append(dict(env))
        return result

    if isinstance(stmt, ast.Continue):
        result.normal.append(dict(env))
        return result

    if isinstance(stmt, (ast.Return, ast.Raise)):
        result.returns.append(dict(env))
        result.raises.append(dict(env))
        return result

    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        result.normal.append(dict(env))
        return result

    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        _track_statement(stmt, env, enclosing_return_type, is_classmethod)
        result.normal.append(dict(env))
        return result

    if isinstance(stmt, ast.If):
        body_env = dict(env)
        body_result = FlowResult()
        for body_stmt in stmt.body:
            sub_result = _process_stmt_for_break(
                body_stmt, body_env, enclosing_return_type, is_classmethod
            )
            body_result.breaks.extend(sub_result.breaks)
            body_result.normal.extend(sub_result.normal)
            if sub_result.normal:
                body_env = dict(sub_result.normal[-1])

        else_env = dict(env)
        else_result = FlowResult()
        if stmt.orelse:
            for else_stmt in stmt.orelse:
                sub_result = _process_stmt_for_break(
                    else_stmt, else_env, enclosing_return_type, is_classmethod
                )
                else_result.breaks.extend(sub_result.breaks)
                else_result.normal.extend(sub_result.normal)
                if sub_result.normal:
                    else_env = dict(sub_result.normal[-1])
        else:
            else_result.normal.append(dict(env))

        result.breaks.extend(body_result.breaks)
        result.breaks.extend(else_result.breaks)
        result.normal.extend(body_result.normal)
        result.normal.extend(else_result.normal)
        return result

    if isinstance(stmt, ast.With):
        for body_stmt in stmt.body:
            sub_result = _process_stmt_for_break(
                body_stmt, env, enclosing_return_type, is_classmethod
            )
            result.breaks.extend(sub_result.breaks)
            result.normal.extend(sub_result.normal)
            if sub_result.normal:
                env = dict(sub_result.normal[-1])
        return result

    if isinstance(stmt, ast.Try):
        nested_result = _process_stmt_for_break_nested(
            stmt, env, enclosing_return_type, is_classmethod
        )
        result.breaks.extend(nested_result.breaks)
        result.normal.extend(nested_result.normal)
        return result

    _track_statement(stmt, env, enclosing_return_type, is_classmethod)
    result.normal.append(dict(env))
    return result


def _process_stmt_for_break_nested(
    try_stmt: ast.Try,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process nested try for break paths.

    Break in a nested try propagates out: the outer loop captures the
    break from the point after the nested try.  The inner finally runs
    before the break exits.
    """
    result = FlowResult()
    exception_envs: list[dict[str, Provenance]] = []
    body_normal_envs: list[dict[str, Provenance]] = [dict(env)]

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Break):
            for norm_env in body_normal_envs:
                result.breaks.append(
                    _apply_finally(
                        norm_env,
                        try_stmt.finalbody,
                        enclosing_return_type,
                        is_classmethod,
                    )
                )
            return result
        if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
            return result

        # CANONICAL exception-env capture via the canonical recursive
        # transfer (snapshot pass on copies; downstream break-descent
        # tracks the original envs).
        for norm_env in body_normal_envs:
            env_copy = dict(norm_env)
            sub_envs, _sub_term = capture_exception_envs_no_target(
                stmt, env_copy, enclosing_return_type, is_classmethod,
                _track_statement,
            )
            exception_envs.extend(sub_envs)

        sub_result = _process_stmt_for_break(
            stmt, env, enclosing_return_type, is_classmethod
        )
        for break_path in sub_result.breaks:
            result.breaks.append(
                _apply_finally(
                    break_path,
                    try_stmt.finalbody,
                    enclosing_return_type,
                    is_classmethod,
                )
            )
        if sub_result.normal:
            new_normal_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                new_normal_envs.extend(sub_result.normal)
            body_normal_envs = new_normal_envs if new_normal_envs else body_normal_envs
            env = dict(sub_result.normal[-1])

    # Handlers are alternatives selected by exception class.  Each handler
    # starts from each captured exception env with an independent copy.
    for handler in try_stmt.handlers:
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            handler_break_found = False
            for handler_stmt in handler.body:
                if isinstance(handler_stmt, ast.Break):
                    result.breaks.append(
                        _apply_finally(
                            handler_env,
                            try_stmt.finalbody,
                            enclosing_return_type,
                            is_classmethod,
                        )
                    )
                    handler_break_found = True
                    break
                if isinstance(handler_stmt, ast.If) and _contains_break_in_stmt(
                    handler_stmt
                ):
                    if_result = _process_stmt_for_break(
                        handler_stmt,
                        handler_env,
                        enclosing_return_type,
                        is_classmethod,
                    )
                    for break_path in if_result.breaks:
                        result.breaks.append(
                            _apply_finally(
                                break_path,
                                try_stmt.finalbody,
                                enclosing_return_type,
                                is_classmethod,
                            )
                        )
                    if if_result.normal:
                        handler_env = dict(if_result.normal[-1])
                    continue
                term = _track_statement(
                    handler_stmt,
                    handler_env,
                    enclosing_return_type,
                    is_classmethod,
                )
                if term in ("continue", "return", "raise"):
                    break
            if not handler_break_found and not any(
                _contains_break_in_stmt(s) for s in handler.body
            ):
                result.normal.append(
                    _apply_finally(
                        handler_env,
                        try_stmt.finalbody,
                        enclosing_return_type,
                        is_classmethod,
                    )
                )

    if try_stmt.finalbody:
        result.normal.append(
            _apply_finally(
                env,
                try_stmt.finalbody,
                enclosing_return_type,
                is_classmethod,
            )
        )
    else:
        result.normal.append(env)

    return result


def process_try_for_break(
    try_stmt: ast.Try,
    break_env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> list[dict[str, Provenance]]:
    """Process try body for break path.

    Handles conditional breaks in if statements and applies ``finally``
    exactly once.  Exception handlers are alternatives -- each handler
    starts from the exception environment, NOT from ``break_env``.  Only
    one handler executes at runtime.
    """
    handler_paths: list[dict[str, Provenance]] = []
    body_break_paths: list[dict[str, Provenance]] = []

    exception_envs: list[dict[str, Provenance]] = []
    body_normal_envs: list[dict[str, Provenance]] = [dict(break_env)]

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Break):
            for norm_env in body_normal_envs:
                body_break_paths.append(
                    _apply_finally(
                        norm_env,
                        try_stmt.finalbody,
                        enclosing_return_type,
                        is_classmethod,
                    )
                )
            break
        if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
            return handler_paths

        # CANONICAL exception-env capture via the canonical recursive
        # transfer (snapshot pass on copies; downstream break-descent
        # tracks the original envs).
        for env in body_normal_envs:
            env_copy = dict(env)
            sub_envs, _sub_term = capture_exception_envs_no_target(
                stmt, env_copy, enclosing_return_type, is_classmethod,
                _track_statement,
            )
            exception_envs.extend(sub_envs)

        if isinstance(stmt, ast.If) and _contains_break_in_stmt(stmt):
            new_normal_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                if_result = _process_stmt_for_break(
                    stmt, norm_env, enclosing_return_type, is_classmethod
                )
                for break_path in if_result.breaks:
                    body_break_paths.append(
                        _apply_finally(
                            break_path,
                            try_stmt.finalbody,
                            enclosing_return_type,
                            is_classmethod,
                        )
                    )
                if if_result.normal:
                    new_normal_envs.extend(if_result.normal)
            body_normal_envs = new_normal_envs if new_normal_envs else body_normal_envs
        else:
            surviving_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                term = _track_statement(
                    stmt, norm_env, enclosing_return_type, is_classmethod
                )
                if term not in ("break", "continue", "return", "raise"):
                    surviving_envs.append(norm_env)
            body_normal_envs = surviving_envs if surviving_envs else body_normal_envs

    for handler in try_stmt.handlers:
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            for stmt in handler.body:
                if isinstance(stmt, ast.Break):
                    handler_paths.append(
                        _apply_finally(
                            handler_env,
                            try_stmt.finalbody,
                            enclosing_return_type,
                            is_classmethod,
                        )
                    )
                    break
                if isinstance(stmt, ast.If) and _contains_break_in_stmt(stmt):
                    if_result = _process_stmt_for_break(
                        stmt,
                        handler_env,
                        enclosing_return_type,
                        is_classmethod,
                    )
                    for break_path in if_result.breaks:
                        handler_paths.append(
                            _apply_finally(
                                break_path,
                                try_stmt.finalbody,
                                enclosing_return_type,
                                is_classmethod,
                            )
                        )
                    if if_result.normal:
                        handler_env = dict(if_result.normal[-1])
                    continue
                term = _track_statement(
                    stmt, handler_env, enclosing_return_type, is_classmethod
                )
                if term in ("continue", "return", "raise"):
                    break
            if not any(_contains_break_in_stmt(s) for s in handler.body):
                handler_paths.append(dict(handler_env))

    return body_break_paths + handler_paths


__all__ = [
    "_contains_break_in_stmt",
    "_process_stmt_for_break",
    "_process_stmt_for_break_nested",
    "process_try_for_break",
]
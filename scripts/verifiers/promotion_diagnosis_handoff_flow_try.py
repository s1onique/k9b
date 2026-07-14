"""Try statement processing for SEAM01 promotion-diagnosis handoff verifier."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_tracking import _track_statement
from promotion_diagnosis_handoff_flow_try_continue import (
    FlowResult,
    _contains_continue_in_stmt,
    _process_stmt_for_continue,
)
from promotion_diagnosis_handoff_flow_try_exceptions import _stmt_may_raise
from promotion_diagnosis_handoff_model import Provenance


def _contains_break_in_stmt(stmt: ast.stmt) -> bool:
    """Check if a statement contains a break (including nested). P0 FIX."""
    if isinstance(stmt, ast.Break):
        return True
    if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return False
    if isinstance(stmt, (ast.For, ast.While)):
        return False

    if isinstance(stmt, ast.If):
        return any(_contains_break_in_stmt(s) for s in stmt.body) or \
               any(_contains_break_in_stmt(s) for s in stmt.orelse)

    if isinstance(stmt, ast.With):
        return any(_contains_break_in_stmt(s) for s in stmt.body)

    if isinstance(stmt, ast.Try):
        return any(_contains_break_in_stmt(s) for s in stmt.body) or \
               any(_contains_break_in_stmt(s) for h in stmt.handlers for s in h.body) or \
               any(_contains_break_in_stmt(s) for s in stmt.orelse) or \
               any(_contains_break_in_stmt(s) for s in stmt.finalbody)

    return False


def process_try_body(
    try_stmt: ast.Try,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> list[dict[str, Provenance]]:
    """Process try body without break/continue handling.

    P0 FIX: Tracks BOTH successful and exception paths.
    After a may-raise call, the successful path continues processing.
    Handlers start from the exception point environment.
    """
    # P0 FIX: Track normal paths through the try body, including after may-raise calls
    normal_env = dict(env)
    exception_envs: list[dict[str, Provenance]] = []

    for stmt in try_stmt.body:
        may_raise = _stmt_may_raise(stmt)

        # P0 FIX: Track the exception path BEFORE processing the statement
        # The exception occurs at this point, before the statement executes
        if may_raise:
            exception_envs.append(dict(normal_env))

        # Process the statement for the successful path
        term = _track_statement(stmt, normal_env, enclosing_return_type, is_classmethod)
        if term in ("break", "continue", "return", "raise"):
            break
        # P0 FIX: Continue processing after successful execution of may-raise statements

    # P0 FIX: Build handler paths from EXCEPTION environments
    handler_paths: list[dict[str, Provenance]] = []

    for handler in try_stmt.handlers:
        # P0 FIX: Each handler starts from the state at the point of exception
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            for stmt in handler.body:
                term = _track_statement(stmt, handler_env, enclosing_return_type, is_classmethod)
                if term in ("break", "continue", "return", "raise"):
                    break
            handler_paths.append(handler_env)

    # P0 FIX: Normal path continues through else on successful completion
    normal_paths = [normal_env] if normal_env else []

    # Process else (runs only on normal completion, no exception)
    for stmt in try_stmt.orelse:
        for np in normal_paths:
            _track_statement(stmt, np, enclosing_return_type, is_classmethod)

    # P0 FIX: Apply finally ONCE to all paths at a common boundary
    if try_stmt.finalbody:
        all_paths = normal_paths + handler_paths
        finalized_paths: list[dict[str, Provenance]] = []
        for path in all_paths:
            final_env = dict(path)
            for stmt in try_stmt.finalbody:
                _track_statement(stmt, final_env, enclosing_return_type, is_classmethod)
            finalized_paths.append(final_env)
        return finalized_paths

    # Return BOTH normal completion and handler paths
    return normal_paths + handler_paths


def _process_stmt_for_break(
    stmt: ast.stmt,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process a statement to find break paths.

    P0 FIX: Break is NOT a normal path - it exits the loop.
    Returns FlowResult with break paths captured properly.
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
            sub_result = _process_stmt_for_break(body_stmt, body_env, enclosing_return_type, is_classmethod)
            body_result.breaks.extend(sub_result.breaks)
            body_result.normal.extend(sub_result.normal)
            if sub_result.normal:
                body_env = dict(sub_result.normal[-1])

        else_env = dict(env)
        else_result = FlowResult()

        if stmt.orelse:
            for else_stmt in stmt.orelse:
                sub_result = _process_stmt_for_break(else_stmt, else_env, enclosing_return_type, is_classmethod)
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
            sub_result = _process_stmt_for_break(body_stmt, env, enclosing_return_type, is_classmethod)
            result.breaks.extend(sub_result.breaks)
            result.normal.extend(sub_result.normal)
            if sub_result.normal:
                env = dict(sub_result.normal[-1])
        return result

    # P0 FIX: Nested Try - handle break propagation through nested try
    if isinstance(stmt, ast.Try):
        # Process the nested try for break paths
        nested_result = _process_stmt_for_break_nested(stmt, env, enclosing_return_type, is_classmethod)
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
    """Process nested try statement for break path.

    P0 FIX: Break in nested try propagates out - the outer loop captures the break
    from the point after the nested try. The inner finally runs before break exits.
    P0 FIX: Apply inner finally to break paths exactly once, not only to normal paths.
    P0 FIX: Process handlers (alternatives selected when exception interrupts try suite).
    """
    result = FlowResult()

    # P0 FIX: Track exception environments for handler processing
    exception_envs: list[dict[str, Provenance]] = []
    body_normal_envs: list[dict[str, Provenance]] = [dict(env)]

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Break):
            # P0 FIX: Break exits this try - apply inner finally BEFORE recording break path
            for norm_env in body_normal_envs:
                break_env = dict(norm_env)
                if try_stmt.finalbody:
                    for final_stmt in try_stmt.finalbody:
                        _track_statement(final_stmt, break_env, enclosing_return_type, is_classmethod)
                result.breaks.append(break_env)
            return result
        if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
            return result

        # P0 FIX: Track may-raise for handler processing
        if _stmt_may_raise(stmt):
            for norm_env in body_normal_envs:
                exception_envs.append(dict(norm_env))

        sub_result = _process_stmt_for_break(stmt, env, enclosing_return_type, is_classmethod)
        # P0 FIX: Apply inner finally to each break path from recursive processing
        for break_env in sub_result.breaks:
            finalized = dict(break_env)
            if try_stmt.finalbody:
                for final_stmt in try_stmt.finalbody:
                    _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
            result.breaks.append(finalized)
        if sub_result.normal:
            # Update body_normal_envs for next statement
            new_normal_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                for sub_normal in sub_result.normal:
                    new_normal_envs.append(dict(sub_normal))
            body_normal_envs = new_normal_envs if new_normal_envs else body_normal_envs
            env = dict(sub_result.normal[-1])

    # P0 FIX: Process handlers - they are alternatives, each starts from exception environment
    for handler in try_stmt.handlers:
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            handler_break_found = False
            for stmt in handler.body:
                if isinstance(stmt, ast.Break):
                    # P0 FIX: Apply inner finally at break BEFORE collecting path
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, handler_env, enclosing_return_type, is_classmethod)
                    result.breaks.append(dict(handler_env))
                    handler_break_found = True
                    break
                if isinstance(stmt, ast.If) and _contains_break_in_stmt(stmt):
                    if_result = _process_stmt_for_break(stmt, handler_env, enclosing_return_type, is_classmethod)
                    for break_path in if_result.breaks:
                        finalized = dict(break_path)
                        if try_stmt.finalbody:
                            for final_stmt in try_stmt.finalbody:
                                _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                        result.breaks.append(finalized)
                    if if_result.normal:
                        handler_env = dict(if_result.normal[-1])
                term = _track_statement(stmt, handler_env, enclosing_return_type, is_classmethod)
                if term in ("continue", "return", "raise"):
                    break
            # P0 FIX: Handler that doesn't break - its final state may continue to outer context
            if not handler_break_found and not any(_contains_break_in_stmt(s) for s in handler.body):
                # Handler completes normally - include its final state
                # P0 FIX: Apply inner finally to handler normal path
                handler_final = dict(handler_env)
                if try_stmt.finalbody:
                    for final_stmt in try_stmt.finalbody:
                        _track_statement(final_stmt, handler_final, enclosing_return_type, is_classmethod)
                result.normal.append(handler_final)

    # Apply finally to normal paths
    if try_stmt.finalbody:
        final_env = dict(env)
        for final_stmt in try_stmt.finalbody:
            _track_statement(final_stmt, final_env, enclosing_return_type, is_classmethod)
        result.normal.append(final_env)
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

    P0 FIX: Handle conditional breaks in if statements, and apply finally ONCE.
    Exception handlers are alternatives - each handler starts from the exception
    environment, NOT from break_env. Only one handler executes at runtime.
    """
    handler_paths: list[dict[str, Provenance]] = []
    body_break_paths: list[dict[str, Provenance]] = []

    # P0 FIX: Track exception environments like process_try_for_continue does
    exception_envs: list[dict[str, Provenance]] = []
    body_normal_envs: list[dict[str, Provenance]] = [dict(break_env)]

    # Process try body - track conditional breaks in if statements
    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Break):
            # Direct break - apply finally and collect
            for norm_env in body_normal_envs:
                break_path = dict(norm_env)
                if try_stmt.finalbody:
                    for final_stmt in try_stmt.finalbody:
                        _track_statement(final_stmt, break_path, enclosing_return_type, is_classmethod)
                body_break_paths.append(break_path)
            break
        if isinstance(stmt, (ast.Continue, ast.Return, ast.Raise)):
            return handler_paths

        # P0 FIX: Check for may-raise AFTER checking for break, to allow conditional-break detection
        if _stmt_may_raise(stmt):
            for env in body_normal_envs:
                exception_envs.append(dict(env))

        if isinstance(stmt, ast.If) and _contains_break_in_stmt(stmt):
            # P0 FIX: Conditional break - process the if to find break paths
            new_normal_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                if_result = _process_stmt_for_break(stmt, norm_env, enclosing_return_type, is_classmethod)
                for break_path in if_result.breaks:
                    finalized = dict(break_path)
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                    body_break_paths.append(finalized)
                if if_result.normal:
                    new_normal_envs.extend(if_result.normal)
            body_normal_envs = new_normal_envs if new_normal_envs else body_normal_envs
        else:
            # P0 FIX: Update body_normal_envs after each statement
            surviving_envs: list[dict[str, Provenance]] = []
            for norm_env in body_normal_envs:
                term = _track_statement(stmt, norm_env, enclosing_return_type, is_classmethod)
                if term not in ("break", "continue", "return", "raise"):
                    surviving_envs.append(norm_env)
            body_normal_envs = surviving_envs if surviving_envs else body_normal_envs

    # P0 FIX: Inspect ALL handlers - each handler starts from EACH exception environment
    # Handlers are alternatives - they execute when exception occurs, so they start
    # from the exception environment, not from break_env
    for handler in try_stmt.handlers:
        for exc_env in exception_envs:
            handler_env = dict(exc_env)
            for stmt in handler.body:
                if isinstance(stmt, ast.Break):
                    # P0 FIX: Apply finally at break BEFORE collecting path
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, handler_env, enclosing_return_type, is_classmethod)
                    handler_paths.append(dict(handler_env))
                    break
                if isinstance(stmt, ast.If) and _contains_break_in_stmt(stmt):
                    if_result = _process_stmt_for_break(stmt, handler_env, enclosing_return_type, is_classmethod)
                    for break_path in if_result.breaks:
                        finalized = dict(break_path)
                        if try_stmt.finalbody:
                            for final_stmt in try_stmt.finalbody:
                                _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                        handler_paths.append(finalized)
                    if if_result.normal:
                        handler_env = dict(if_result.normal[-1])
                term = _track_statement(stmt, handler_env, enclosing_return_type, is_classmethod)
                if term in ("continue", "return", "raise"):
                    break
            # P0 FIX: Also add handler path if it didn't break
            if not any(_contains_break_in_stmt(s) for s in handler.body):
                handler_paths.append(dict(handler_env))

    # Collect all paths
    all_paths: list[dict[str, Provenance]] = []
    all_paths.extend(body_break_paths)
    all_paths.extend(handler_paths)

    return all_paths


def process_try_for_continue(
    try_stmt: ast.Try,
    continue_env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process try body for continue path.

    P0 FIX: Returns FlowResult instead of mutating caller-owned list.
    Each statement's finally is applied at the point of exit.

    Returns:
        FlowResult with:
        - normal: list of normal path environments
        - continues: list of continue path environments (FINALIZED by this try's finally)
    """
    result = FlowResult()
    exception_envs: list[dict[str, Provenance]] = []
    normal_envs: list[dict[str, Provenance]] = [dict(continue_env)]

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Continue):
            # P0 FIX: Apply finally BEFORE collecting continue path
            for env in normal_envs:
                finalized_env = dict(env)
                if try_stmt.finalbody:
                    for final_stmt in try_stmt.finalbody:
                        _track_statement(final_stmt, finalized_env, enclosing_return_type, is_classmethod)
                result.continues.append(finalized_env)
            return result

        if _stmt_may_raise(stmt):
            for env in normal_envs:
                exception_envs.append(dict(env))

        if _contains_continue_in_stmt(stmt):
            new_normal_envs: list[dict[str, Provenance]] = []
            for env in normal_envs:
                sub_result = _process_stmt_for_continue(stmt, env, enclosing_return_type, is_classmethod)
                # P0 FIX: Apply finally to each continue path from nested analysis
                for cont_env in sub_result.continues:
                    finalized_env = dict(cont_env)
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, finalized_env, enclosing_return_type, is_classmethod)
                    result.continues.append(finalized_env)
                new_normal_envs.extend(sub_result.normal)
            normal_envs = new_normal_envs
        else:
            surviving_envs: list[dict[str, Provenance]] = []
            for env in normal_envs:
                term = _track_statement(stmt, env, enclosing_return_type, is_classmethod)
                if term not in ("break", "return", "raise"):
                    surviving_envs.append(env)
            normal_envs = surviving_envs

    if try_stmt.orelse:
        for else_stmt in try_stmt.orelse:
            if _contains_continue_in_stmt(else_stmt):
                else_normals: list[dict[str, Provenance]] = []
                for env in normal_envs:
                    else_result = _process_stmt_for_continue(else_stmt, env, enclosing_return_type, is_classmethod)
                    for cont_env in else_result.continues:
                        finalized_env = dict(cont_env)
                        if try_stmt.finalbody:
                            for final_stmt in try_stmt.finalbody:
                                _track_statement(final_stmt, finalized_env, enclosing_return_type, is_classmethod)
                        result.continues.append(finalized_env)
                    else_normals.extend(else_result.normal)
                normal_envs = else_normals
            else:
                else_surviving: list[dict[str, Provenance]] = []
                for env in normal_envs:
                    term = _track_statement(else_stmt, env, enclosing_return_type, is_classmethod)
                    if term not in ("break", "continue", "return", "raise"):
                        else_surviving.append(env)
                normal_envs = else_surviving

    try_body_normal_paths = list(normal_envs)
    handler_normal_paths: list[dict[str, Provenance]] = []

    if try_stmt.handlers and exception_envs:
        for handler in try_stmt.handlers:
            handler_envs: list[dict[str, Provenance]] = [dict(e) for e in exception_envs]

            for stmt in handler.body:
                if isinstance(stmt, ast.Continue):
                    # P0 FIX: Apply finally BEFORE collecting continue path
                    for env in handler_envs:
                        finalized_env = dict(env)
                        if try_stmt.finalbody:
                            for final_stmt in try_stmt.finalbody:
                                _track_statement(final_stmt, finalized_env, enclosing_return_type, is_classmethod)
                        result.continues.append(finalized_env)
                    handler_envs = []
                    break

                if _contains_continue_in_stmt(stmt):
                    new_handler_envs: list[dict[str, Provenance]] = []
                    for env in handler_envs:
                        sub_result = _process_stmt_for_continue(stmt, env, enclosing_return_type, is_classmethod)
                        for cont_env in sub_result.continues:
                            finalized_env = dict(cont_env)
                            if try_stmt.finalbody:
                                for final_stmt in try_stmt.finalbody:
                                    _track_statement(final_stmt, finalized_env, enclosing_return_type, is_classmethod)
                            result.continues.append(finalized_env)
                        new_handler_envs.extend(sub_result.normal)
                    handler_envs = new_handler_envs
                else:
                    surviving: list[dict[str, Provenance]] = []
                    for env in handler_envs:
                        term = _track_statement(stmt, env, enclosing_return_type, is_classmethod)
                        if term not in ("break", "return", "raise"):
                            surviving.append(env)
                    handler_envs = surviving

            handler_normal_paths.extend(handler_envs)

    all_normal_paths = try_body_normal_paths + handler_normal_paths

    # P0 FIX: Apply finally ONCE at the common boundary to normal paths
    if all_normal_paths and try_stmt.finalbody:
        finalized_normals: list[dict[str, Provenance]] = []
        for path in all_normal_paths:
            final_env = dict(path)
            for final_stmt in try_stmt.finalbody:
                _track_statement(final_stmt, final_env, enclosing_return_type, is_classmethod)
            finalized_normals.append(final_env)
        result.normal.extend(finalized_normals)
    else:
        result.normal.extend(all_normal_paths)

    return result

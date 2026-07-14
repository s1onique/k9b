"""Continue path analysis for try statement processing."""

from __future__ import annotations

import ast

from promotion_diagnosis_handoff_flow_tracking import _track_statement
from promotion_diagnosis_handoff_flow_try_canonical import capture_exception_envs_no_target
from promotion_diagnosis_handoff_flow_try_exceptions import _stmt_may_raise  # noqa: F401  (retained only for non-authoritative diagnostics)
from promotion_diagnosis_handoff_model import FlowResult, Provenance


def _contains_continue_in_stmt(stmt: ast.stmt) -> bool:
    """Check if a statement contains a continue (including nested). P0 FIX."""
    if isinstance(stmt, ast.Continue):
        return True
    if isinstance(stmt, (ast.Break, ast.Return, ast.Raise)):
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return False
    if isinstance(stmt, (ast.For, ast.While)):
        return False

    if isinstance(stmt, ast.If):
        return any(_contains_continue_in_stmt(s) for s in stmt.body) or \
               any(_contains_continue_in_stmt(s) for s in stmt.orelse)

    if isinstance(stmt, ast.With):
        return any(_contains_continue_in_stmt(s) for s in stmt.body)

    if isinstance(stmt, ast.Try):
        return any(_contains_continue_in_stmt(s) for s in stmt.body) or \
               any(_contains_continue_in_stmt(s) for h in stmt.handlers for s in h.body) or \
               any(_contains_continue_in_stmt(s) for s in stmt.orelse) or \
               any(_contains_continue_in_stmt(s) for s in stmt.finalbody)

    return False


def _process_stmt_for_continue(
    stmt: ast.stmt,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process a statement to find continue paths.

    P0 FIX: Does NOT apply finally - caller applies finally exactly once.
    This prevents double-finalization of nested continue paths.

    Returns FlowResult with:
    - normal: list of normal path environments after processing
    - continues: list of continue path environments (raw, not finalized)
    """
    result = FlowResult()

    if isinstance(stmt, ast.Continue):
        # P0 FIX: Return raw environment - caller applies finally
        result.continues.append(dict(env))
        return result

    if isinstance(stmt, ast.Break):
        # P0 FIX: Break is NOT a normal path - it exits the loop
        # Return it as a break path so the caller can handle it
        result.breaks.append(dict(env))
        return result

    if isinstance(stmt, (ast.Return, ast.Raise)):
        # Return/raise are terminators - they exit the function
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
            sub_result = _process_stmt_for_continue(body_stmt, body_env, enclosing_return_type, is_classmethod)
            body_result.continues.extend(sub_result.continues)
            body_result.normal.extend(sub_result.normal)
            if sub_result.normal:
                body_env = dict(sub_result.normal[-1])

        else_env = dict(env)
        else_result = FlowResult()

        if stmt.orelse:
            for else_stmt in stmt.orelse:
                sub_result = _process_stmt_for_continue(else_stmt, else_env, enclosing_return_type, is_classmethod)
                else_result.continues.extend(sub_result.continues)
                else_result.normal.extend(sub_result.normal)
                if sub_result.normal:
                    else_env = dict(sub_result.normal[-1])
        else:
            else_result.normal.append(dict(env))

        result.continues.extend(body_result.continues)
        result.continues.extend(else_result.continues)
        result.normal.extend(body_result.normal)
        result.normal.extend(else_result.normal)
        return result

    if isinstance(stmt, ast.With):
        for body_stmt in stmt.body:
            sub_result = _process_stmt_for_continue(body_stmt, env, enclosing_return_type, is_classmethod)
            result.continues.extend(sub_result.continues)
            result.normal.extend(sub_result.normal)
            if sub_result.normal:
                env = dict(sub_result.normal[-1])
        return result

    if isinstance(stmt, ast.Try):
        # P0 FIX: Nested try - use specialized handler for inner finally+continue
        nested_result = _process_inner_try_for_continue(stmt, env, enclosing_return_type, is_classmethod)
        result.continues.extend(nested_result.continues)
        result.normal.extend(nested_result.normal)
        return result

    _track_statement(stmt, env, enclosing_return_type, is_classmethod)
    result.normal.append(dict(env))
    return result


def _apply_finally(
    envs: list[dict[str, Provenance]],
    finalbody: list[ast.stmt],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> list[dict[str, Provenance]]:
    """Apply finally block to each environment, returning modified copies."""
    result = []
    for env in envs:
        new_env = dict(env)
        for final_stmt in finalbody:
            _track_statement(final_stmt, new_env, enclosing_return_type, is_classmethod)
        result.append(new_env)
    return result


def _process_inner_try_for_continue(
    try_stmt: ast.Try,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Process inner try statement for continue path with proper finally handling.

    P0 FIX: This handles nested try statements where the inner finally must
    execute before the continue exits. Unlike outer try processing, this needs
    to handle the continue+finally interaction within the inner try.

    P0 FIX: Handlers start from exception environments, not normal completion.

    Returns FlowResult with continue paths properly finalized by inner finally.
    """
    result = FlowResult()
    normal_envs: list[dict[str, Provenance]] = [dict(env)]

    # P0 FIX: Track exception environments within this nested try body
    inner_exception_envs: list[dict[str, Provenance]] = []

    for stmt in try_stmt.body:
        if isinstance(stmt, ast.Continue):
            # Found continue - apply inner finally BEFORE collecting continue path
            for inner_env in normal_envs:
                finalized = dict(inner_env)
                if try_stmt.finalbody:
                    for final_stmt in try_stmt.finalbody:
                        _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                result.continues.append(finalized)
            return result

        # CANONICAL exception-env capture via the canonical recursive
        # transfer.  Walk copies so the downstream continue-descent
        # sees the original env state.
        for inner_env in normal_envs:
            env_copy = dict(inner_env)
            sub_envs, _sub_term = capture_exception_envs_no_target(
                stmt, env_copy, enclosing_return_type, is_classmethod,
                _track_statement,
            )
            inner_exception_envs.extend(sub_envs)

        if _contains_continue_in_stmt(stmt):
            new_normal_envs: list[dict[str, Provenance]] = []
            for inner_env in normal_envs:
                sub_result = _process_stmt_for_continue(stmt, inner_env, enclosing_return_type, is_classmethod)
                # Apply inner finally to each continue path
                for cont_env in sub_result.continues:
                    finalized = dict(cont_env)
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                    result.continues.append(finalized)
                new_normal_envs.extend(sub_result.normal)
            normal_envs = new_normal_envs
        else:
            surviving: list[dict[str, Provenance]] = []
            for inner_env in normal_envs:
                term = _track_statement(stmt, inner_env, enclosing_return_type, is_classmethod)
                if term not in ("break", "return", "raise"):
                    surviving.append(inner_env)
            normal_envs = surviving

    # Process else clause
    for else_stmt in try_stmt.orelse:
        if _contains_continue_in_stmt(else_stmt):
            else_normal_envs: list[dict[str, Provenance]] = []
            for inner_env in normal_envs:
                sub_result = _process_stmt_for_continue(else_stmt, inner_env, enclosing_return_type, is_classmethod)
                for cont_env in sub_result.continues:
                    finalized = dict(cont_env)
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                    result.continues.append(finalized)
                else_normal_envs.extend(sub_result.normal)
            normal_envs = else_normal_envs
        else:
            else_surviving: list[dict[str, Provenance]] = []
            for inner_env in normal_envs:
                term = _track_statement(else_stmt, inner_env, enclosing_return_type, is_classmethod)
                if term not in ("break", "continue", "return", "raise"):
                    else_surviving.append(inner_env)
            normal_envs = else_surviving

    # P0 FIX: Process handlers - each handler starts independently from exception envs
    # Handlers are alternatives, not sequential transformations
    handler_normal_paths: list[dict[str, Provenance]] = []
    for handler in try_stmt.handlers:
        # Each handler starts from the exception environment, not from shared state
        handler_continues: list[dict[str, Provenance]] = []
        for exc_env in inner_exception_envs:
            handler_env = dict(exc_env)
            handler_continue_found = False
            for handler_stmt in handler.body:
                if isinstance(handler_stmt, ast.Continue):
                    # Continue found - apply inner finally before collecting
                    finalized = dict(handler_env)
                    if try_stmt.finalbody:
                        for final_stmt in try_stmt.finalbody:
                            _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                    handler_continues.append(finalized)
                    handler_continue_found = True
                    break
                if _contains_continue_in_stmt(handler_stmt):
                    sub_result = _process_stmt_for_continue(handler_stmt, handler_env, enclosing_return_type, is_classmethod)
                    for cont_env in sub_result.continues:
                        finalized = dict(cont_env)
                        if try_stmt.finalbody:
                            for final_stmt in try_stmt.finalbody:
                                _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
                        handler_continues.append(finalized)
                    # Update handler_env from normal paths
                    if sub_result.normal:
                        handler_env = dict(sub_result.normal[-1])
                else:
                    term = _track_statement(handler_stmt, handler_env, enclosing_return_type, is_classmethod)
                    if term in ("break", "continue", "return", "raise"):
                        handler_continue_found = True  # Treat as terminating
                        break
            # P0 FIX: Handler that doesn't execute continue - add its final state to normal paths
            # The handler completes normally and control transfers to the next statement
            if not handler_continue_found:
                handler_normal_paths.append(dict(handler_env))
        result.continues.extend(handler_continues)

    # P0 FIX: Apply finally to ALL normal paths before adding to result.normal
    # This includes both try-body normal paths and handler normal paths
    all_normal_paths = normal_envs + handler_normal_paths

    if try_stmt.finalbody:
        for path in all_normal_paths:
            finalized = dict(path)
            for final_stmt in try_stmt.finalbody:
                _track_statement(final_stmt, finalized, enclosing_return_type, is_classmethod)
            result.normal.append(finalized)
    else:
        result.normal.extend(all_normal_paths)

    return result

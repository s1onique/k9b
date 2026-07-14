"""Loop analysis functions for SEAM01 promotion-diagnosis handoff verifier.

This module contains:
- _track_for_to_target: Comprehensive path analysis for for loops
- _track_while_to_target: Comprehensive path analysis for while loops

Path tracking model:
- Each statement produces a FlowResult with normal/continues/breaks/returns paths
- Normal paths feed into subsequent statements
- Continue paths are accumulated separately (start next iteration)
- Break paths exit the loop
- Return/raise paths terminate the function

Python loop semantics:
- for-else runs ONLY when iterator exhausts without break
- break exits loop immediately, finally runs before exit
- continue starts next iteration (may reach else on normal exhaustion)
- finally runs before break exits the loop
- if no else, all paths (break, exhaustion, zero-iteration) are possible
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_tracking import (
    _collect_assigned_names,
    _contains_direct_continue,
    _loop_body_has_direct_break,
    _statement_has_break_for_enclosing_loop,
    _track_statement,
)
from promotion_diagnosis_handoff_flow_try import (
    process_try_body,
    process_try_for_break,
    process_try_for_continue,
)
from promotion_diagnosis_handoff_model import FlowResult, Provenance, merge_paths

# NOTE: FlowResult is now imported from promotion_diagnosis_handoff_model.
# The local NamedTuple definition has been removed to avoid duplication.
# The model defines FlowResult as a dataclass with lists of paths.


def _track_if_for_continue(
    if_stmt: ast.If,
    env: dict[str, Provenance],
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> FlowResult:
    """Track if statement for continue path analysis.

    Returns FlowResult with:
    - normal: state for the fallthrough path (else or after if body when no else)
    - continues: list of states where continue was executed

    P0 FIX: When if has explicit else, the non-terminating if.body path
    is also a normal fallthrough path. Python executes only one branch,
    so both are valid normal paths.
    """
    # Process body (if condition is true)
    if_body_env = dict(env)
    if_continues: list[dict[str, Provenance]] = []
    if_body_terminates = False

    for stmt in if_stmt.body:
        term = _track_statement(stmt, if_body_env, enclosing_return_type, is_classmethod)
        if term == "continue":
            # Continue in body - this is a continue path
            if_continues.append(dict(if_body_env))
            if_body_terminates = True
            break
        elif term in ("break", "return", "raise"):
            if_body_terminates = True
            break

    # Process else (if condition is false)
    else_body_env = dict(env)
    else_continues: list[dict[str, Provenance]] = []

    for stmt in if_stmt.orelse:
        term = _track_statement(stmt, else_body_env, enclosing_return_type, is_classmethod)
        if term == "continue":
            else_continues.append(dict(else_body_env))
        elif term in ("break", "return", "raise"):
            break

    # P0 FIX: Normal paths are:
    # 1. The else body (if condition is false) - always a normal path if it doesn't terminate
    # 2. The if body (if condition is true) when:
    #    - There's no else clause (fallthrough is normal)
    #    - The if body doesn't terminate (can fall through)
    #
    # When "if item: continue else: ..." the else path is NOT a continue path,
    # it's a normal path. The if body IS a continue path.
    all_normals: list[dict[str, Provenance]] = []

    # Else body contributes to normal if it doesn't have continue (it's a fallthrough)
    if else_body_env:
        # Check if else body has a continue - if so, the else path is NOT normal
        has_else_continue = bool(else_continues)
        if not has_else_continue:
            all_normals.append(else_body_env)

    # P0 FIX: If body IS a normal path when it doesn't terminate.
    # Python executes only the selected branch:
    # - if condition TRUE: executes if.body (normal path if it doesn't terminate)
    # - if condition FALSE: executes else.body (normal path if no continue)
    #
    # For "if item: value = untrusted else: continue":
    # - TRUE path: value = untrusted (NORMAL - if body executes)
    # - FALSE path: continue (CONTINUE path)
    #
    # Both paths are valid and must be tracked separately.
    if not if_body_terminates:
        # If body doesn't terminate - it IS a normal path
        # Add it regardless of whether else exists
        all_normals.append(if_body_env)

    # Else body contributes to normal if it doesn't have continue
    # (already handled above in the "has_else_continue" check)

    all_continues = if_continues + else_continues

    if all_normals:
        merged_normal = merge_paths(all_normals)
        return FlowResult(normal=[merged_normal], continues=all_continues, breaks=[], returns=[], raises=[])
    else:
        return FlowResult(normal=[], continues=all_continues, breaks=[], returns=[], raises=[])


def _track_for_to_target(
    node: ast.For,
    prov: dict[str, Provenance],
    target_line: int,
    target_col: int,
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> None:
    """Track for loop with comprehensive path analysis.

    Path categories:
    1. Zero-iteration: pre_loop state (safe for pre-loop vars, unknown for body-only vars)
    2. Normal exhaustion: state after all iterations complete without break
    3. Break paths: state captured at each break point (after finally if present)
    4. For-else: runs on normal exhaustion (not on break)
    """
    loop_assigned = _collect_assigned_names(node)
    pre_loop = dict(prov)

    # Register loop target
    if isinstance(node.target, ast.Name):
        prov[node.target.id] = Provenance()

    # Track all paths through the loop
    all_continue_paths: list[dict[str, Provenance]] = []
    all_break_paths: list[dict[str, Provenance]] = []

    # The state that feeds into each iteration (after pre-loop assignments)
    iteration_input = dict(pre_loop)
    if isinstance(node.target, ast.Name):
        iteration_input[node.target.id] = Provenance()

    # Process first iteration to get continuation paths
    first_iter_normal = dict(iteration_input)
    first_iter_continues: list[dict[str, Provenance]] = []

    for body_stmt in node.body:
        has_break = _statement_has_break_for_enclosing_loop(body_stmt)
        has_continue = _contains_direct_continue(body_stmt)

        if has_break:
            # Break path - capture state and stop processing
            break_env = dict(first_iter_normal)
            if isinstance(body_stmt, ast.Try):
                # For try, process handlers and finalbody for break path
                # P0 FIX: Use the return value which contains finalized paths
                break_paths = process_try_for_break(body_stmt, break_env, enclosing_return_type, is_classmethod)
                all_break_paths.extend(break_paths)

                # For conditional break in try, also process the non-break continuation path
                # The try's normal execution continues after the try statement
                # We need to process this for subsequent statements
                process_try_body(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
            elif isinstance(body_stmt, ast.If):
                # Conditional break - track BOTH break path AND continuation path
                # Break path: state at the point of break
                if_break_env = dict(first_iter_normal)
                for if_body_stmt in body_stmt.body:
                    _track_statement(if_body_stmt, if_break_env, enclosing_return_type, is_classmethod)
                all_break_paths.append(if_break_env)

                # Continuation path: process the if statement for non-break path
                _track_statement(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
            else:
                # Unconditional break - stop processing loop body
                _track_statement(body_stmt, break_env, enclosing_return_type, is_classmethod)
                all_break_paths.append(break_env)
                break

        if has_continue:
            # Continue path - capture state before processing remaining statements
            continue_env = dict(first_iter_normal)

            if isinstance(body_stmt, ast.Try):
                # For try: process body until continue, then finalbody
                # P0 FIX: process_try_for_continue now returns FlowResult (no caller-owned list)
                try_result = process_try_for_continue(body_stmt, continue_env, enclosing_return_type, is_classmethod)
                # The try statement's normal path continues with the try's effects
                if try_result.normal:
                    # Merge the normal paths from the try into first_iter_normal
                    first_iter_normal = merge_paths(try_result.normal)
                # Continue paths are already finalized by the try's finally
                first_iter_continues.extend(try_result.continues)
            elif isinstance(body_stmt, ast.If):
                # For if: process the if statement
                # The if's continue path goes to continues, fallthrough goes to normal
                if_result = _track_if_for_continue(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
                if if_result.normal:
                    # Canonical FlowResult.normal is a list; merge them
                    merged_normal = merge_paths(if_result.normal)
                    first_iter_normal = merged_normal
                first_iter_continues.extend(if_result.continues)
            else:
                # Direct continue statement
                _track_statement(body_stmt, continue_env, enclosing_return_type, is_classmethod)
                first_iter_continues.append(continue_env)
        else:
            # No break or continue in this statement - process normally
            if isinstance(body_stmt, ast.Try):
                # process_try_body returns handler paths; update first_iter_normal
                try_result = process_try_body(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
                if try_result:
                    first_iter_normal = merge_paths(try_result)
            else:
                _track_statement(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)

    # After first iteration, accumulate continue paths
    all_continue_paths.extend(first_iter_continues)

    has_break = _loop_body_has_direct_break(node)

    if node.orelse:
        # for-else runs ONLY on normal exhaustion (no break)
        zero_iter_else = dict(pre_loop)
        for v in loop_assigned:
            if v not in pre_loop:
                zero_iter_else[v] = Provenance()

        else_zero_iter = dict(zero_iter_else)
        for else_stmt in node.orelse:
            _track_statement(else_stmt, else_zero_iter, enclosing_return_type, is_classmethod)

        else_normal_exhaustion = dict(first_iter_normal) if first_iter_normal else dict(pre_loop)
        for else_stmt in node.orelse:
            _track_statement(else_stmt, else_normal_exhaustion, enclosing_return_type, is_classmethod)

        # P0 FIX: Continue paths must be fed through the loop head/exhaustion model
        # regardless of whether there are break paths.
        #
        # Break paths exit the loop immediately (don't reach else).
        # Continue paths start the next iteration - they can exhaust and reach else.
        #
        # Both break and continue paths must be tracked independently:
        # - all_break_paths: exit via break (no else)
        # - continue_else_paths: continue to next iteration, may exhaust and reach else

        continue_else_paths: list[dict[str, Provenance]] = []
        for cont_path in all_continue_paths:
            cont_else = dict(cont_path)
            for else_stmt in node.orelse:
                _track_statement(else_stmt, cont_else, enclosing_return_type, is_classmethod)
            continue_else_paths.append(cont_else)

        if has_break:
            # Break paths exit immediately (no else), but continue paths can still exhaust
            all_paths = [else_zero_iter, else_normal_exhaustion] + continue_else_paths + all_break_paths
        else:
            # No breaks - all paths can reach else on exhaustion
            all_paths = [else_zero_iter, else_normal_exhaustion] + continue_else_paths
    else:
        # No else: all paths are possible
        zero_iter_path = dict(pre_loop)
        for v in loop_assigned:
            if v not in pre_loop:
                zero_iter_path[v] = Provenance()

        normal_exhaustion = dict(first_iter_normal) if first_iter_normal else dict(pre_loop)

        all_paths = [normal_exhaustion, zero_iter_path] + all_break_paths + all_continue_paths

    merged = merge_paths(all_paths)
    prov.clear()
    prov.update(merged)


def _track_while_to_target(
    node: ast.While,
    prov: dict[str, Provenance],
    target_line: int,
    target_col: int,
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> None:
    """Track while loop with comprehensive path analysis.

    Similar to for loop but with while-specific semantics.
    """
    while_assigned = _collect_assigned_names(node)
    pre_while_loop = dict(prov)

    all_continue_paths: list[dict[str, Provenance]] = []
    all_break_paths: list[dict[str, Provenance]] = []

    # Process first iteration
    first_iter_normal = dict(pre_while_loop)
    first_iter_continues: list[dict[str, Provenance]] = []

    for body_stmt in node.body:
        has_break = _statement_has_break_for_enclosing_loop(body_stmt)
        has_continue = _contains_direct_continue(body_stmt)

        if has_break:
            break_env = dict(first_iter_normal)
            if isinstance(body_stmt, ast.Try):
                # P0 FIX: Use the return value which contains finalized paths
                break_paths = process_try_for_break(body_stmt, break_env, enclosing_return_type, is_classmethod)
                all_break_paths.extend(break_paths)
                process_try_body(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
            elif isinstance(body_stmt, ast.If):
                if_break_env = dict(first_iter_normal)
                for if_body_stmt in body_stmt.body:
                    _track_statement(if_body_stmt, if_break_env, enclosing_return_type, is_classmethod)
                all_break_paths.append(if_break_env)
                _track_statement(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
            else:
                _track_statement(body_stmt, break_env, enclosing_return_type, is_classmethod)
                all_break_paths.append(break_env)
                break

        if has_continue:
            continue_env = dict(first_iter_normal)

            if isinstance(body_stmt, ast.Try):
                # P0 FIX: process_try_for_continue now returns FlowResult (no caller-owned list)
                try_result = process_try_for_continue(body_stmt, continue_env, enclosing_return_type, is_classmethod)
                if try_result.normal:
                    first_iter_normal = merge_paths(try_result.normal)
                first_iter_continues.extend(try_result.continues)
            elif isinstance(body_stmt, ast.If):
                if_result = _track_if_for_continue(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
                if if_result.normal:
                    # Canonical FlowResult.normal is a list; merge them
                    merged_normal = merge_paths(if_result.normal)
                    first_iter_normal = merged_normal
                first_iter_continues.extend(if_result.continues)
            else:
                _track_statement(body_stmt, continue_env, enclosing_return_type, is_classmethod)
                first_iter_continues.append(continue_env)
        else:
            if isinstance(body_stmt, ast.Try):
                # P0 FIX: Use the return value - merge handler paths
                try_result = process_try_body(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)
                if try_result:
                    first_iter_normal = merge_paths(try_result)
            else:
                _track_statement(body_stmt, first_iter_normal, enclosing_return_type, is_classmethod)

    all_continue_paths.extend(first_iter_continues)

    has_break = _loop_body_has_direct_break(node)

    if node.orelse:
        zero_iter_else = dict(pre_while_loop)
        for v in while_assigned:
            if v not in pre_while_loop:
                zero_iter_else[v] = Provenance()

        else_zero_iter = dict(zero_iter_else)
        for else_stmt in node.orelse:
            _track_statement(else_stmt, else_zero_iter, enclosing_return_type, is_classmethod)

        else_normal_exhaustion = dict(first_iter_normal) if first_iter_normal else dict(pre_while_loop)
        for else_stmt in node.orelse:
            _track_statement(else_stmt, else_normal_exhaustion, enclosing_return_type, is_classmethod)

        # P0 FIX: Same logic as for loops - continue paths can exhaust to else
        continue_else_paths: list[dict[str, Provenance]] = []
        for cont_path in all_continue_paths:
            cont_else = dict(cont_path)
            for else_stmt in node.orelse:
                _track_statement(else_stmt, cont_else, enclosing_return_type, is_classmethod)
            continue_else_paths.append(cont_else)

        if has_break:
            # Break paths exit immediately (no else), but continue paths can still exhaust
            all_paths = [else_zero_iter, else_normal_exhaustion] + continue_else_paths + all_break_paths
        else:
            # No breaks - all paths can reach else on exhaustion
            all_paths = [else_zero_iter, else_normal_exhaustion] + continue_else_paths
    else:
        zero_iter_path = dict(pre_while_loop)
        for v in while_assigned:
            if v not in pre_while_loop:
                zero_iter_path[v] = Provenance()

        normal_exhaustion = dict(first_iter_normal) if first_iter_normal else dict(pre_while_loop)

        all_paths = [normal_exhaustion, zero_iter_path] + all_break_paths + all_continue_paths

    merged = merge_paths(all_paths)
    prov.clear()
    prov.update(merged)

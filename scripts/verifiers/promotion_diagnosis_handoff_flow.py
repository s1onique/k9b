"""Flow analysis for SEAM01 promotion-diagnosis handoff verifier.

This module handles:
- Ordered traversal with node-position awareness (lineno, col_offset, end_lineno, end_col_offset)
- Conservative joins for branches, loops, and try/except
- Proper handling of loop break vs normal exhaustion vs zero-iteration

Loop analysis has been moved to promotion_diagnosis_handoff_flow_loops.py
Tracking logic has been moved to promotion_diagnosis_handoff_flow_tracking.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_loops import _track_for_to_target, _track_while_to_target
from promotion_diagnosis_handoff_flow_tracking import (
    _contains_direct_break,
    _track_statement,
)
from promotion_diagnosis_handoff_model import (
    FunctionInfo,
    ImportInfo,
    Provenance,
    ProvenanceKind,
    merge_paths,
)
from promotion_diagnosis_handoff_symbols import (
    is_incident_promotion_result_type,
    is_promotion_batch_type,
    is_run_promotion_accumulator_type,
)


def _track_to_target_line(
    node: ast.AST | list[ast.stmt],
    prov: dict[str, Provenance],
    target_line: int,
    target_col: int = 0,
    enclosing_return_type: str | None = None,
    is_classmethod: bool = False,
    _in_loop_body: bool = False,
) -> bool:
    """Recursively track provenance up to (but not including) the target position.

    Args:
        _in_loop_body: If True, return True when encountering a Break to signal
                       that the loop should stop processing more statements.
                       Default False for backward compatibility.
    """
    if isinstance(node, list):
        for stmt in node:
            if hasattr(stmt, 'lineno') and stmt.lineno is not None:
                if stmt.lineno > target_line:
                    return False
                if stmt.lineno == target_line:
                    stmt_end_col = getattr(stmt, 'end_col_offset', None)
                    if stmt_end_col is not None and stmt_end_col > target_col:
                        return False
            result = _track_to_target_line(
                stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod, _in_loop_body
            )
            if result:
                return True
        return False

    if not isinstance(node, (ast.stmt, list)):
        return False

    if hasattr(node, 'lineno') and node.lineno is not None:
        if node.lineno > target_line:
            return False
        if node.lineno == target_line:
            node_end_col = getattr(node, 'end_col_offset', None)
            if node_end_col is not None and node_end_col > target_col:
                return False

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False

    if isinstance(node, ast.Break):
        # Only return True if we're inside a loop body that should stop processing
        return _in_loop_body
    if isinstance(node, ast.Continue):
        # P0 FIX: continue skips remaining statements in the loop body.
        # Return True to signal that remaining statements should be skipped.
        return _in_loop_body
    if isinstance(node, (ast.Return, ast.Raise)):
        return False

    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        _track_statement(node, prov, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.For):
        # Process nested for loops - don't return their result as it would break the outer loop
        if hasattr(node, 'lineno') and node.lineno < target_line:
            _track_for_to_target(node, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.While):
        # Process nested while loops - don't return their result as it would break the outer loop
        if hasattr(node, 'lineno') and node.lineno < target_line:
            _track_while_to_target(node, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.With):
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                prov[item.optional_vars.id] = Provenance()
        for body_stmt in node.body:
            _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod, _in_loop_body)
    elif isinstance(node, ast.If):
        # P0 FIX: Check if any statement in if body contains a break
        has_break_in_body = False
        for body_stmt in node.body:
            if _contains_direct_break(body_stmt):
                has_break_in_body = True
                break

        # P0 FIX: Also check if-else for break (R3-3)
        if not has_break_in_body and node.orelse:
            for else_stmt in node.orelse:
                if _contains_direct_break(else_stmt):
                    has_break_in_body = True
                    break

        if has_break_in_body:
            # P0 FIX: Handle if with break in body specially
            # Break path: state at the point where break is taken (before any inner statements)
            # Non-break path: continue processing remaining statements in if body
            break_prov = dict(prov)
            continuation_prov = dict(prov)

            for idx, body_stmt in enumerate(node.body):
                if _contains_direct_break(body_stmt):
                    # P0 FIX: Don't process this statement for either path
                    # Just capture the break path at current state
                    break_prov = dict(continuation_prov)
                    # Continue processing for non-break path only
                    for remaining_stmt in node.body[idx + 1:]:
                        _track_to_target_line(
                            remaining_stmt, continuation_prov, target_line, target_col,
                            enclosing_return_type, is_classmethod, _in_loop_body
                        )
                    break
                # P0 FIX: For non-break statements, process for both paths
                _track_to_target_line(
                    body_stmt, break_prov, target_line, target_col,
                    enclosing_return_type, is_classmethod, _in_loop_body
                )
                _track_to_target_line(
                    body_stmt, continuation_prov, target_line, target_col,
                    enclosing_return_type, is_classmethod, _in_loop_body
                )

            # P0 FIX: Also process if-else for break path (R3-3)
            if node.orelse:
                for else_stmt in node.orelse:
                    if _contains_direct_break(else_stmt):
                        # P0 FIX: Capture break path at this point
                        break_prov = dict(continuation_prov)
                        break
                    _track_to_target_line(
                        else_stmt, break_prov, target_line, target_col,
                        enclosing_return_type, is_classmethod, _in_loop_body
                    )
                    _track_to_target_line(
                        else_stmt, continuation_prov, target_line, target_col,
                        enclosing_return_type, is_classmethod, _in_loop_body
                    )

            # P0 FIX: Merge break path and continuation path
            all_vars = set(break_prov.keys()) | set(continuation_prov.keys())
            merged = {}
            for var_name in all_vars:
                if var_name in break_prov and var_name in continuation_prov:
                    merged[var_name] = break_prov[var_name].merge(continuation_prov[var_name])
                elif var_name in break_prov:
                    merged[var_name] = break_prov[var_name]
                else:
                    merged[var_name] = continuation_prov[var_name]
            prov.clear()
            prov.update(merged)
        else:
            # Track if-body normally
            if_body_prov = dict(prov)
            for body_stmt in node.body:
                _track_to_target_line(body_stmt, if_body_prov, target_line, target_col, enclosing_return_type, is_classmethod, _in_loop_body)

            # Merge if-body and fallthrough (or else-body if present)
            if node.orelse:
                else_body_prov = dict(prov)
                for else_stmt in node.orelse:
                    _track_to_target_line(else_stmt, else_body_prov, target_line, target_col, enclosing_return_type, is_classmethod, _in_loop_body)
                # Merge if-body and else-body paths
                all_vars = set(if_body_prov.keys()) | set(else_body_prov.keys())
                for var_name in all_vars:
                    if var_name in if_body_prov and var_name in else_body_prov:
                        prov[var_name] = if_body_prov[var_name].merge(else_body_prov[var_name])
                    elif var_name in if_body_prov:
                        prov[var_name] = if_body_prov[var_name]
                    else:
                        prov[var_name] = else_body_prov[var_name]
            else:
                # No else clause: merge if-body and fallthrough (pre-if state)
                # P0 FIX: For variables only in if-body (not in pre-if), we must merge
                # with fallthrough which doesn't have the variable at all.
                # This makes the result unknown because the variable may not be assigned.
                pre_if = dict(prov)
                all_vars = set(if_body_prov.keys()) | set(pre_if.keys())
                merged = {}
                for var_name in all_vars:
                    if var_name in pre_if and var_name in if_body_prov:
                        merged[var_name] = pre_if[var_name].merge(if_body_prov[var_name])
                    elif var_name in pre_if:
                        merged[var_name] = pre_if[var_name]
                    else:
                        # Variable only in if-body - merge with missing (unknown)
                        merged[var_name] = Provenance()  # unknown
                prov.clear()
                prov.update(merged)
    elif isinstance(node, ast.Try):
        # P0 FIX: Route all Try nodes through explicit try-path analyzer
        # This processes: try body, handlers, else body, finally body
        _track_try_to_target(node, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    return False


def _track_try_to_target(
    node: ast.Try,
    prov: dict[str, Provenance],
    target_line: int,
    target_col: int,
    enclosing_return_type: str | None,
    is_classmethod: bool,
) -> None:
    """Track try/except/else/finally up to target line."""
    pre_try_state = dict(prov)

    for body_stmt in node.body:
        _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)

    if node.orelse:
        for else_stmt in node.orelse:
            _track_to_target_line(else_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)

    handler_results: list[dict[str, Provenance]] = []
    for handler in node.handlers:
        handler_env = dict(pre_try_state)
        for handler_stmt in handler.body:
            _track_to_target_line(handler_stmt, handler_env, target_line, target_col, enclosing_return_type, is_classmethod)
        handler_results.append(handler_env)

    all_paths = [prov] + handler_results
    merged = merge_paths(all_paths)
    prov.clear()
    prov.update(merged)

    for final_stmt in node.finalbody:
        _track_to_target_line(final_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)


def build_provenance_at_node(
    tree: ast.AST,
    function: FunctionInfo,
    target_line: int,
    target_col: int = 0,
    imports: list[ImportInfo] | None = None,
) -> dict[str, Provenance]:
    """Build provenance map up to (but not including) a specific position."""
    prov: dict[str, Provenance] = {}

    for param_name, annotation in function.params.items():
        if annotation:
            kind = ProvenanceKind.UNKNOWN
            if is_promotion_batch_type(annotation, imports):
                kind = ProvenanceKind.PROMOTION_BATCH
            elif is_incident_promotion_result_type(annotation, imports):
                kind = ProvenanceKind.INCIDENT_PROMOTION_RESULT
            elif is_run_promotion_accumulator_type(annotation, imports):
                kind = ProvenanceKind.RUN_PROMOTION_ACCUMULATOR
            prov[param_name] = Provenance(
                annotated_type=annotation,
                provenance_kind=kind,
            )

    if function.return_annotation:
        prov["__return__"] = Provenance(return_type=function.return_annotation)

    func_node = _find_function_node(tree, function)

    if func_node:
        enclosing_return_type = None
        if function.return_annotation:
            if is_incident_promotion_result_type(function.return_annotation, imports):
                enclosing_return_type = function.return_annotation

        _track_to_target_line(
            func_node.body,
            prov,
            target_line,
            target_col,
            enclosing_return_type=enclosing_return_type,
            is_classmethod=function.is_classmethod,
        )

    return prov


def _find_function_node(
    tree: ast.AST,
    function: FunctionInfo,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find the AST node for a function by matching line_start AND name."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno == function.line_start and node.name == function.name:
                return node
    return None

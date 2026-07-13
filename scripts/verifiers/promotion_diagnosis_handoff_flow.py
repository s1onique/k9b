"""Flow analysis for SEAM01 promotion-diagnosis handoff verifier.

This module handles:
- Ordered traversal with node-position awareness (lineno, col_offset, end_lineno, end_col_offset)
- Conservative joins for branches, loops, and try/except
- Proper handling of loop break vs normal exhaustion vs zero-iteration
- Recursive assigned-name collection for nested statements

Collection functions have been moved to promotion_diagnosis_handoff_flow_collect.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow_collect import (
    annotation_to_str,
)
from promotion_diagnosis_handoff_model import (
    CANONICAL_PROMOTION_RESULT_FIELD,
    FunctionInfo,
    Provenance,
)
from promotion_diagnosis_handoff_symbols import (
    is_incident_promotion_result_type,
)


def node_before_position(
    node: ast.AST,
    target_line: int,
    target_col: int,
) -> bool:
    """Check if a node ends before the target position.

    P0 FIX: Uses full source position (line, col_offset) for accurate ordering.
    This handles same-line statements correctly.
    """
    if not hasattr(node, 'lineno') or node.lineno is None:
        return True
    if not hasattr(node, 'end_lineno') or node.end_lineno is None:
        return True

    if node.end_lineno < target_line:
        return True
    if node.end_lineno == target_line:
        end_col = getattr(node, 'end_col_offset', None)
        if end_col is not None and end_col <= target_col:
            return True
    return False


def _collect_assigned_names(stmt: ast.stmt) -> set[str]:
    """Recursively collect all variable names assigned in a statement.

    P0 FIX: Recursively scans nested statements (if, with, try, loops)
    to find all assigned names, not just direct body statements.
    This prevents bypassing loop joins via nested assignments.
    """
    assigned: set[str] = set()

    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                assigned.add(target.id)
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        assigned.add(stmt.target.id)
    elif isinstance(stmt, ast.For):
        if isinstance(stmt.target, ast.Name):
            assigned.add(stmt.target.id)
        for body_stmt in stmt.body:
            assigned.update(_collect_assigned_names(body_stmt))
        for else_stmt in stmt.orelse:
            assigned.update(_collect_assigned_names(else_stmt))
    elif isinstance(stmt, ast.While):
        for body_stmt in stmt.body:
            assigned.update(_collect_assigned_names(body_stmt))
        for else_stmt in stmt.orelse:
            assigned.update(_collect_assigned_names(else_stmt))
    elif isinstance(stmt, ast.With):
        for item in stmt.items:
            if isinstance(item.optional_vars, ast.Name):
                assigned.add(item.optional_vars.id)
        for body_stmt in stmt.body:
            assigned.update(_collect_assigned_names(body_stmt))
    elif isinstance(stmt, ast.If):
        for body_stmt in stmt.body:
            assigned.update(_collect_assigned_names(body_stmt))
        for else_stmt in stmt.orelse:
            assigned.update(_collect_assigned_names(else_stmt))
    elif isinstance(stmt, ast.Try):
        for body_stmt in stmt.body:
            assigned.update(_collect_assigned_names(body_stmt))
        for handler in stmt.handlers:
            for handler_stmt in handler.body:
                assigned.update(_collect_assigned_names(handler_stmt))
        for else_stmt in stmt.orelse:
            assigned.update(_collect_assigned_names(else_stmt))
        for final_stmt in stmt.finalbody:
            assigned.update(_collect_assigned_names(final_stmt))

    return assigned


def _contains_direct_break(stmt: ast.stmt) -> bool:
    """P0 FIX: Check if a statement contains a break that directly exits THIS loop.
    
    Does NOT descend into:
    - Nested loops (their breaks don't affect the outer loop's else)
    - Nested functions, lambdas, or classes
    
    Python semantics: a break only exits the innermost enclosing loop.
    """
    for node in ast.walk(stmt):
        # Skip nested loops - their breaks don't affect this loop's else
        if isinstance(node, (ast.For, ast.While)):
            continue
        # Skip nested functions, lambdas, and classes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, ast.Break):
            return True
    return False


def _contains_break(stmt: ast.stmt) -> bool:
    """P0 FIX: Legacy wrapper - delegate to scope-aware implementation.
    
    Deprecated: Use _contains_direct_break for loop-else analysis.
    """
    return _contains_direct_break(stmt)


def _get_expr_provenance(
    expr: ast.expr,
    prov: dict[str, Provenance],
) -> Provenance:
    """Determine provenance of an expression at a specific point in execution."""
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name):
            base_name = expr.value.id
            if base_name in prov:
                base_prov = prov[base_name]
                if base_prov.attr_chain is not None:
                    return Provenance(attr_chain=base_prov.attr_chain + (expr.attr,))
                elif base_prov.annotated_type:
                    return Provenance(attr_chain=(expr.attr,))
            if expr.attr == CANONICAL_PROMOTION_RESULT_FIELD:
                return Provenance(attr_chain=(CANONICAL_PROMOTION_RESULT_FIELD,))
        elif isinstance(expr.value, ast.Attribute):
            inner_prov = _get_expr_provenance(expr.value, prov)
            if inner_prov.attr_chain is not None:
                return Provenance(attr_chain=inner_prov.attr_chain + (expr.attr,))
    elif isinstance(expr, ast.Name):
        if expr.id in prov:
            return prov[expr.id]
    elif isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name):
            if expr.func.id == "__return__":
                return prov.get("__return__", Provenance())
    return Provenance()


def _track_statement(
    stmt: ast.stmt,
    prov: dict[str, Provenance],
    enclosing_return_type: str | None = None,
    is_classmethod: bool = False,
) -> None:
    """Track variable assignment for a single statement in execution order."""
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                value_prov = _get_expr_provenance(stmt.value, prov)
                if enclosing_return_type and isinstance(stmt.value, ast.Call):
                    if isinstance(stmt.value.func, ast.Name):
                        func_name = stmt.value.func.id
                        if func_name == "cls" and is_classmethod:
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif func_name == "__class__":
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif is_incident_promotion_result_type(func_name):
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                prov[target.id] = value_prov
    elif isinstance(stmt, ast.AnnAssign):
        if isinstance(stmt.target, ast.Name):
            ann_str = None
            if stmt.annotation:
                ann_str = annotation_to_str(stmt.annotation)
            value_prov = Provenance()
            if stmt.value:
                value_prov = _get_expr_provenance(stmt.value, prov)
                if enclosing_return_type and isinstance(stmt.value, ast.Call):
                    if isinstance(stmt.value.func, ast.Name):
                        if stmt.value.func.id == "cls" and is_classmethod:
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif stmt.value.func.id == "__class__":
                            value_prov = Provenance(annotated_type=enclosing_return_type)
            if ann_str and value_prov.is_safe_promotion_result_access():
                prov[stmt.target.id] = Provenance(
                    attr_chain=value_prov.attr_chain,
                    annotated_type=ann_str,
                )
            elif ann_str and value_prov.attr_chain is not None:
                prov[stmt.target.id] = Provenance(attr_chain=value_prov.attr_chain)
            else:
                prov[stmt.target.id] = value_prov
    elif isinstance(stmt, ast.For):
        # P0 FIX: Proper handling of loop break vs normal exhaustion vs zero-iteration
        # Python executes a loop's else only when the loop finishes without break.
        loop_assigned = _collect_assigned_names(stmt)
        pre_loop = {v: prov[v] for v in loop_assigned if v in prov}
        if isinstance(stmt.target, ast.Name):
            prov[stmt.target.id] = Provenance()
        for body_stmt in stmt.body:
            _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
        # Merge pre-loop and post-loop states
        for v in loop_assigned:
            if v in pre_loop:
                prov[v] = pre_loop[v].merge(prov.get(v, Provenance()))
        # P0 FIX: When break is present, need to merge break-path and exhaustion-path
        # - break path: exits immediately, else does NOT run
        # - exhaustion path: loop completes normally, else runs
        # Both paths must be considered safe for the variable to be safe
        has_break = _contains_direct_break(stmt)
        if stmt.orelse:
            if has_break:
                # Save break-path state (current prov after loop body)
                break_path_prov = dict(prov)
                # Execute else for exhaustion path
                else_prov = dict(prov)
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, else_prov, enclosing_return_type, is_classmethod)
                # Merge both paths - conservative: safe only if both paths are safe
                all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                for var_name in all_vars:
                    if var_name in break_path_prov and var_name in else_prov:
                        prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                    elif var_name in break_path_prov:
                        prov[var_name] = break_path_prov[var_name]
                    else:
                        prov[var_name] = else_prov[var_name]
            else:
                # No break - else always runs
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)
    elif isinstance(stmt, ast.While):
        # P0 FIX: Proper handling of loop break vs normal exhaustion vs zero-iteration
        while_assigned = _collect_assigned_names(stmt)
        pre_while_loop = {v: prov[v] for v in while_assigned if v in prov}
        for body_stmt in stmt.body:
            _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
        for v in while_assigned:
            if v in pre_while_loop:
                prov[v] = pre_while_loop[v].merge(prov.get(v, Provenance()))
        # P0 FIX: When break is present, need to merge break-path and exhaustion-path
        has_break = _contains_direct_break(stmt)
        if stmt.orelse:
            if has_break:
                # Save break-path state (current prov after loop body)
                break_path_prov = dict(prov)
                # Execute else for exhaustion path
                else_prov = dict(prov)
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, else_prov, enclosing_return_type, is_classmethod)
                # Merge both paths - conservative: safe only if both paths are safe
                all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                for var_name in all_vars:
                    if var_name in break_path_prov and var_name in else_prov:
                        prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                    elif var_name in break_path_prov:
                        prov[var_name] = break_path_prov[var_name]
                    else:
                        prov[var_name] = else_prov[var_name]
            else:
                # No break - else always runs
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)
    elif isinstance(stmt, ast.With):
        for item in stmt.items:
            if isinstance(item.optional_vars, ast.Name):
                prov[item.optional_vars.id] = Provenance()
        for body_stmt in stmt.body:
            _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
    elif isinstance(stmt, ast.If):
        # P0: Track if and else branches separately, then merge
        if_body_prov = dict(prov)
        for body_stmt in stmt.body:
            _track_statement(body_stmt, if_body_prov, enclosing_return_type, is_classmethod)
        else_body_prov = dict(prov)
        for else_stmt in stmt.orelse:
            _track_statement(else_stmt, else_body_prov, enclosing_return_type, is_classmethod)
        all_vars = set(if_body_prov.keys()) | set(else_body_prov.keys())
        for var_name in all_vars:
            if var_name in if_body_prov and var_name in else_body_prov:
                prov[var_name] = if_body_prov[var_name].merge(else_body_prov[var_name])
            elif var_name in if_body_prov:
                prov[var_name] = if_body_prov[var_name]
            else:
                prov[var_name] = else_body_prov[var_name]
    elif isinstance(stmt, ast.Try):
        # P0 FIX: Separate execution paths for try/except/else
        # Python semantics:
        # - try body executes, then if no exception, else executes
        # - if exception, handlers execute from pre-try state
        # - finally always executes after selected path
        #
        # Required model:
        #   pre_try_env = complete environment BEFORE try (P0 FIX: ALL variables)
        #   normal_env = copy of pre_try_env
        #   normal_env = execute try body
        #   normal_env = execute else against normal_env (only on normal path)
        #   handler_env_1 = copy of pre_try_env; execute handler 1
        #   handler_env_2 = copy of pre_try_env; execute handler 2
        #   joined_env = merge(normal_env, handler_env_1, handler_env_2)
        #   final_env = execute finally against joined_env

        # P0 FIX: Save COMPLETE pre-try state for ALL variables, not just handler-assigned
        pre_try_state = dict(prov)

        # Execute try body on current environment (normal path)
        for body_stmt in stmt.body:
            _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)

        # P0 FIX: else ONLY executes on normal completion (no exception)
        # Track else in current env, which is the post-try-body state
        if stmt.orelse:
            for else_stmt in stmt.orelse:
                _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)

        # P0 FIX: Execute each handler from COMPLETE pre-try state (exception path)
        handler_results: list[dict[str, Provenance]] = []
        for handler in stmt.handlers:
            handler_env = dict(pre_try_state)
            for handler_stmt in handler.body:
                _track_statement(handler_stmt, handler_env, enclosing_return_type, is_classmethod)
            handler_results.append(handler_env)

        # P0 FIX: Merge ALL paths including normal (prov) with handler paths
        # A variable missing from one path must be merged as UNKNOWN
        all_vars = set(prov.keys())
        for handler_env in handler_results:
            all_vars.update(handler_env.keys())
        all_vars.update(pre_try_state.keys())

        merged: dict[str, Provenance] = {}
        for var_name in all_vars:
            # Start with Provenance() for unknown, then merge all paths
            merged[var_name] = Provenance()

            # Merge normal path if present
            if var_name in prov:
                merged[var_name] = merged[var_name].merge(prov[var_name])

            # Merge handler paths
            for handler_env in handler_results:
                if var_name in handler_env:
                    merged[var_name] = merged[var_name].merge(handler_env[var_name])

        # Update current environment with merged result
        prov.update(merged)

        # Execute finally (always runs after selected path)
        for final_stmt in stmt.finalbody:
            _track_statement(final_stmt, prov, enclosing_return_type, is_classmethod)


def _track_to_target_line(
    node: ast.AST | list[ast.stmt],
    prov: dict[str, Provenance],
    target_line: int,
    target_col: int = 0,
    enclosing_return_type: str | None = None,
    is_classmethod: bool = False,
) -> bool:
    """Recursively track provenance up to (but not including) the target position.

    P0 FIX: Uses (lineno, col_offset) for accurate statement ordering.
    Handles same-line statements correctly.
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
                stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod
            )
            if result:
                return True
        return False

    if not isinstance(node, (ast.stmt, list)):
        return False

    # Check position
    if hasattr(node, 'lineno') and node.lineno is not None:
        if node.lineno > target_line:
            return False
        if node.lineno == target_line:
            node_end_col = getattr(node, 'end_col_offset', None)
            if node_end_col is not None and node_end_col > target_col:
                return False

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False

    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                value_prov = _get_expr_provenance(node.value, prov)
                if enclosing_return_type and isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        func_name = node.value.func.id
                        if func_name == "cls" and is_classmethod:
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif func_name == "__class__":
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif is_incident_promotion_result_type(func_name):
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                prov[target.id] = value_prov
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            ann_str = None
            if node.annotation:
                ann_str = annotation_to_str(node.annotation)
            value_prov = Provenance()
            if node.value:
                value_prov = _get_expr_provenance(node.value, prov)
                if enclosing_return_type and isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        if node.value.func.id == "cls" and is_classmethod:
                            value_prov = Provenance(annotated_type=enclosing_return_type)
                        elif node.value.func.id == "__class__":
                            value_prov = Provenance(annotated_type=enclosing_return_type)
            if ann_str and value_prov.is_safe_promotion_result_access():
                prov[node.target.id] = Provenance(
                    attr_chain=value_prov.attr_chain,
                    annotated_type=ann_str,
                )
            elif ann_str and value_prov.attr_chain is not None:
                prov[node.target.id] = Provenance(attr_chain=value_prov.attr_chain)
            else:
                prov[node.target.id] = value_prov
    elif isinstance(node, ast.For):
        if hasattr(node, 'lineno') and node.lineno < target_line:
            loop_assigned = _collect_assigned_names(node)
            pre_loop = {v: prov[v] for v in loop_assigned if v in prov}
            if isinstance(node.target, ast.Name):
                prov[node.target.id] = Provenance()
            for body_stmt in node.body:
                _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
            for v in loop_assigned:
                if v in pre_loop:
                    prov[v] = pre_loop[v].merge(prov.get(v, Provenance()))
            # P0 FIX: When break is present, need to merge break-path and exhaustion-path
            has_break = _contains_direct_break(node)
            if node.orelse:
                if has_break:
                    # Save break-path state (current prov after loop body)
                    break_path_prov = dict(prov)
                    # Execute else for exhaustion path
                    else_prov = dict(prov)
                    for else_stmt in node.orelse:
                        _track_to_target_line(else_stmt, else_prov, target_line, target_col, enclosing_return_type, is_classmethod)
                    # Merge both paths - conservative: safe only if both paths are safe
                    all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                    for var_name in all_vars:
                        if var_name in break_path_prov and var_name in else_prov:
                            prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                        elif var_name in break_path_prov:
                            prov[var_name] = break_path_prov[var_name]
                        else:
                            prov[var_name] = else_prov[var_name]
                else:
                    # No break - else always runs
                    for else_stmt in node.orelse:
                        _track_to_target_line(else_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.While):
        if hasattr(node, 'lineno') and node.lineno < target_line:
            while_assigned = _collect_assigned_names(node)
            pre_while_loop = {v: prov[v] for v in while_assigned if v in prov}
            for body_stmt in node.body:
                _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
            for v in while_assigned:
                if v in pre_while_loop:
                    prov[v] = pre_while_loop[v].merge(prov.get(v, Provenance()))
            # P0 FIX: When break is present, need to merge break-path and exhaustion-path
            has_break = _contains_direct_break(node)
            if node.orelse:
                if has_break:
                    # Save break-path state (current prov after loop body)
                    break_path_prov = dict(prov)
                    # Execute else for exhaustion path
                    else_prov = dict(prov)
                    for else_stmt in node.orelse:
                        _track_to_target_line(else_stmt, else_prov, target_line, target_col, enclosing_return_type, is_classmethod)
                    # Merge both paths - conservative: safe only if both paths are safe
                    all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                    for var_name in all_vars:
                        if var_name in break_path_prov and var_name in else_prov:
                            prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                        elif var_name in break_path_prov:
                            prov[var_name] = break_path_prov[var_name]
                        else:
                            prov[var_name] = else_prov[var_name]
                else:
                    # No break - else always runs
                    for else_stmt in node.orelse:
                        _track_to_target_line(else_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.With):
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                prov[item.optional_vars.id] = Provenance()
        for body_stmt in node.body:
            _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    elif isinstance(node, ast.If):
        if_body_prov = dict(prov)
        for body_stmt in node.body:
            _track_to_target_line(body_stmt, if_body_prov, target_line, target_col, enclosing_return_type, is_classmethod)
        else_body_prov = dict(prov)
        for else_stmt in node.orelse:
            _track_to_target_line(else_stmt, else_body_prov, target_line, target_col, enclosing_return_type, is_classmethod)
        all_vars = set(if_body_prov.keys()) | set(else_body_prov.keys())
        for var_name in all_vars:
            if var_name in if_body_prov and var_name in else_body_prov:
                prov[var_name] = if_body_prov[var_name].merge(else_body_prov[var_name])
            elif var_name in if_body_prov:
                prov[var_name] = if_body_prov[var_name]
            else:
                prov[var_name] = else_body_prov[var_name]
    elif isinstance(node, ast.Try):
        # P0 FIX: Separate execution paths for try/except/else (same as _track_statement)
        # P0 FIX: Save COMPLETE pre-try state for ALL variables, not just handler-assigned
        pre_try_state = dict(prov)

        # Execute try body on current environment (normal path)
        for body_stmt in node.body:
            _track_to_target_line(body_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)

        # P0 FIX: else ONLY executes on normal completion
        if node.orelse:
            for else_stmt in node.orelse:
                _track_to_target_line(else_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)

        # P0 FIX: Execute each handler from COMPLETE pre-try state (exception path)
        handler_results: list[dict[str, Provenance]] = []
        for handler in node.handlers:
            handler_env = dict(pre_try_state)
            for handler_stmt in handler.body:
                _track_to_target_line(handler_stmt, handler_env, target_line, target_col, enclosing_return_type, is_classmethod)
            handler_results.append(handler_env)

        # P0 FIX: Merge ALL paths including normal (prov) with handler paths
        # A variable missing from one path must be merged as UNKNOWN
        all_vars = set(prov.keys())
        for handler_env in handler_results:
            all_vars.update(handler_env.keys())
        all_vars.update(pre_try_state.keys())

        merged: dict[str, Provenance] = {}
        for var_name in all_vars:
            # Start with Provenance() for unknown, then merge all paths
            merged[var_name] = Provenance()

            # Merge normal path if present
            if var_name in prov:
                merged[var_name] = merged[var_name].merge(prov[var_name])

            # Merge handler paths
            for handler_env in handler_results:
                if var_name in handler_env:
                    merged[var_name] = merged[var_name].merge(handler_env[var_name])

        prov.update(merged)

        # Execute finally (always runs after selected path)
        for final_stmt in node.finalbody:
            _track_to_target_line(final_stmt, prov, target_line, target_col, enclosing_return_type, is_classmethod)
    return False


def build_provenance_at_node(
    tree: ast.AST,
    function: FunctionInfo,
    target_line: int,
    target_col: int = 0,
) -> dict[str, Provenance]:
    """Build provenance map up to (but not including) a specific position.

    P0 FIX: Uses (lineno, col_offset) for accurate statement ordering.
    """
    prov: dict[str, Provenance] = {}

    for param_name, annotation in function.params.items():
        if annotation:
            prov[param_name] = Provenance(annotated_type=annotation)

    if function.return_annotation:
        prov["__return__"] = Provenance(return_type=function.return_annotation)

    func_node = _find_function_node(tree, function)

    if func_node:
        enclosing_return_type = None
        if function.return_annotation:
            if is_incident_promotion_result_type(function.return_annotation):
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

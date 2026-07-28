#!/usr/bin/env python3
"""AST scanner for disposition reason-map verification.

Extracted from automatic_diagnosis_disposition.py to satisfy the 500-line
source guard while preserving full AST analysis semantics.

This module provides:
- Loading and parsing supplied Python files
- Locating the scheduler-completion return projection
- Following supported **spread values
- Validating the projection_from_result helper
- Rejecting nested-function-only evidence
- Proving all three maps are returned (skip/ineligible/error)
"""

from __future__ import annotations

import ast


def _check_file_has_reason_maps(source: str) -> tuple[bool, str]:
    """Check if source includes all three reason map keys in returned dict.

    Uses AST analysis to verify that build_completed_summary returns a dict
    containing skip_reasons, ineligible_reasons, and error_reasons keys.
    Uses two-phase approach:
    1. For direct dict literals: check if required keys are present
    2. For dict spreads: check if spread comes from projection_from_result helper
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, "syntax error in source"

    # Phase 1: Find build_completed_summary and check its return statements
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_completed_summary":
            # Get direct return statements (not from nested functions)
            returns = _get_direct_returns(node)
            if not returns:
                return False, "build_completed_summary has no return statement"

            for ret in returns:
                if isinstance(ret, ast.Tuple):
                    # Unpack the tuple: return summary, reason_projection
                    # We care about 'summary' which is the first element
                    if len(ret.elts) >= 1:
                        summary_expr = ret.elts[0]
                        result = _check_dict_provides_reason_maps(summary_expr, source)
                        if result[0]:
                            return result

            # Check if any return dict has all required keys
            for ret in returns:
                if isinstance(ret, ast.Dict):
                    keys = [k.value if isinstance(k, ast.Constant) else None for k in ret.keys]
                    has_skip = "skip_reasons" in keys
                    has_ineligible = "ineligible_reasons" in keys
                    has_error = "error_reasons" in keys
                    if has_skip and has_ineligible and has_error:
                        return True, "all three reason maps present in returned dict"
                    else:
                        missing = []
                        if not has_skip:
                            missing.append("skip_reasons")
                        if not has_ineligible:
                            missing.append("ineligible_reasons")
                        if not has_error:
                            missing.append("error_reasons")
                        return False, f"missing keys in returned dict: {missing}"

            # If we have returns but none have all keys, check for spread case
            for ret in returns:
                if isinstance(ret, ast.Tuple) and len(ret.elts) >= 1:
                    result = _check_dict_provides_reason_maps(ret.elts[0], source)
                    if result[0]:
                        return result

    return False, "build_completed_summary function not found or no return statement"


def _get_direct_returns(func_node: ast.FunctionDef) -> list[ast.expr]:
    """Get return statements that are direct children of the function, not from nested functions."""
    returns: list[ast.expr] = []
    for node in func_node.body:
        _collect_returns(node, returns)
    return returns


def _collect_returns(node: ast.AST, collector: list[ast.expr]) -> None:
    """Recursively collect return statements, skipping nested function bodies."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return  # Skip nested functions
    if isinstance(node, ast.Return) and node.value is not None:
        collector.append(node.value)
    for child in ast.iter_child_nodes(node):
        _collect_returns(child, collector)


def _check_dict_provides_reason_maps(expr: ast.expr, source: str) -> tuple[bool, str]:
    """Check if a dict expression provides the required reason map keys.

    Handles direct dict literals, Name references (lookup assignment), and dicts with spreads.
    """
    # If expr is a Name, look up its assignment
    if isinstance(expr, ast.Name):
        assigned_expr = _lookup_assignment(expr.id, source)
        if assigned_expr is not None:
            return _check_dict_provides_reason_maps(assigned_expr, source)
        return False, f"variable {expr.id} not found in scope"

    if not isinstance(expr, ast.Dict):
        return False, "return value is not a dict"

    # Check for required keys directly in dict
    direct_keys = []
    has_spread = False
    spread_vars = []

    for i, key in enumerate(expr.keys):
        if key is None:
            # This is a **spread
            has_spread = True
            if i < len(expr.values):
                value = expr.values[i]
                if isinstance(value, ast.Name):
                    spread_vars.append(value.id)
        elif isinstance(key, ast.Constant):
            direct_keys.append(key.value)

    required = {"skip_reasons", "ineligible_reasons", "error_reasons"}
    missing = required - set(direct_keys)

    if not missing:
        return True, "all three reason maps present in returned dict"

    # If we have spreads, check if they come from projection_from_result
    if has_spread:
        for var in spread_vars:
            # Check if var is assigned from projection_from_result
            if _helper_provides_reason_maps(var, source):
                # The helper provides all remaining missing keys
                return True, "all three reason maps present via spread from projection_from_result helper"

    return False, f"missing keys in returned dict: {sorted(missing)}"


def _lookup_assignment(var_name: str, source: str) -> ast.expr | None:
    """Look up the assigned expression for a variable name."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check direct assignments in function body
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id == var_name:
                            return stmt.value
    return None


def _helper_provides_reason_maps(var_name: str, source: str) -> bool:
    """Check if a variable is assigned from projection_from_result helper that returns all three keys."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    # First, find the module-level function that projection_from_result is defined in
    helper_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "projection_from_result":
            helper_func = node
            break

    if helper_func is None:
        return False

    # Verify the helper returns all 3 keys
    helper_returns_all = _helper_returns_all_keys(helper_func)

    if not helper_returns_all:
        return False

    # Now verify that var_name is assigned from a call to projection_from_result
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == var_name:
                            if isinstance(child.value, ast.Call):
                                func = child.value.func
                                if isinstance(func, ast.Name) and func.id == "projection_from_result":
                                    return True
    return False


def _helper_returns_all_keys(func_node: ast.FunctionDef) -> bool:
    """Check if a function returns a dict with all three required reason map keys."""
    required = {"skip_reasons", "ineligible_reasons", "error_reasons"}

    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value:
            if isinstance(node.value, ast.Dict):
                keys = [k.value if isinstance(k, ast.Constant) else None for k in node.value.keys]
                found_keys = {k for k in keys if k is not None}
                if required.issubset(found_keys):
                    return True
    return False


# Re-export the check function for the main module
__all__ = [
    "_check_file_has_reason_maps",
]

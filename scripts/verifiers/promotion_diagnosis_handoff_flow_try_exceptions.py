"""Exception analysis helpers for try statement processing."""

from __future__ import annotations

import ast


def _may_raise(expr: ast.expr) -> bool:
    """Check if an expression may raise an exception. P0 FIX: Conservative model."""
    if expr is None:
        return False

    if isinstance(expr, ast.Call):
        return True

    if isinstance(expr, ast.Attribute):
        return True

    if isinstance(expr, ast.Subscript):
        return True

    if isinstance(expr, ast.BinOp):
        return _may_raise(expr.left) or _may_raise(expr.right)

    if isinstance(expr, ast.UnaryOp):
        return _may_raise(expr.operand)

    if isinstance(expr, ast.Compare):
        return _may_raise(expr.left) or any(_may_raise(c) for c in expr.comparators)

    if isinstance(expr, ast.BoolOp):
        # P0 FIX: Check ALL operands of BoolOp, not just the first.
        return any(_may_raise(value) for value in expr.values)

    if isinstance(expr, (ast.Name, ast.Constant, ast.FormattedValue, ast.JoinedStr)):
        return False

    return True


def _stmt_may_raise(stmt: ast.stmt) -> bool:
    """Check if a statement may raise an exception.

    P0 FIX: Recursively analyze compound statements to detect exception points
    inside if/with/try/etc. bodies. Python begins handler selection at the point
    the exception interrupts the suite, not from a synthetic state after later statements.
    """
    # Base cases - expressions that definitely raise
    if isinstance(stmt, ast.Expr):
        return _may_raise(stmt.value)

    if isinstance(stmt, ast.Assign):
        return _may_raise(stmt.value)

    if isinstance(stmt, ast.AnnAssign):
        if stmt.value is not None:
            return _may_raise(stmt.value)
        return False

    if isinstance(stmt, ast.AugAssign):
        return _may_raise(stmt.value)

    if isinstance(stmt, ast.Raise):
        return True

    # P0 FIX: Recursive analysis for compound statements
    # An If may raise if ANY of its branches may raise
    if isinstance(stmt, ast.If):
        return any(_stmt_may_raise(s) for s in stmt.body) or \
               any(_stmt_may_raise(s) for s in stmt.orelse)

    # A With may raise if any of its body statements may raise
    if isinstance(stmt, ast.With):
        return any(_stmt_may_raise(s) for s in stmt.body)

    # A Try may raise if any of body/handlers/else may raise
    if isinstance(stmt, ast.Try):
        return any(_stmt_may_raise(s) for s in stmt.body) or \
               any(any(_stmt_may_raise(s) for s in h.body) for h in stmt.handlers) or \
               any(_stmt_may_raise(s) for s in stmt.orelse)

    # For and While - check body (not conditions, which are loop guards)
    if isinstance(stmt, (ast.For, ast.While)):
        return any(_stmt_may_raise(s) for s in stmt.body)

    return False

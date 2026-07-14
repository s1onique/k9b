"""Flow tracking logic for SEAM01 promotion-diagnosis handoff verifier.

This module contains the core flow analysis functions:
- Provenance tracking for expressions
- Statement-level assignment tracking
- Break/continue detection for loops

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

import ast
from typing import Literal

from promotion_diagnosis_handoff_flow_collect import (
    annotation_to_str,
)
from promotion_diagnosis_handoff_model import (
    CANONICAL_PROMOTION_RESULT_FIELD,
    Provenance,
)
from promotion_diagnosis_handoff_symbols import (
    is_incident_promotion_result_type,
)


def _collect_assigned_names(stmt: ast.stmt) -> set[str]:
    """Recursively collect all variable names assigned in a statement."""
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
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        pass

    return assigned


class _BreakSearcher(ast.NodeVisitor):
    """Visitor that finds breaks owned by the enclosing loop.

    Key invariant: nested For/While loops are pruned. Python's break exits
    only the nearest enclosing loop, so an inner loop's break does NOT count
    as a break for the outer loop.
    """

    def _visit_body(self, body: list[ast.stmt]) -> bool:
        """Visit statements in order, stopping at first break found."""
        for stmt in body:
            if self._visit_stmt(stmt):
                return True
        return False

    def _visit_stmt(self, stmt: ast.stmt) -> bool:
        """Visit a single statement, return True if break found.

        Stops at nested loops - an inner loop's break does NOT count as
        a break for the outer loop.
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
            return (
                self._visit_body(stmt.body)
                or self._visit_body(stmt.orelse)
            )
        if isinstance(stmt, ast.With):
            return self._visit_body(stmt.body)
        if isinstance(stmt, ast.Try):
            return (
                self._visit_body(stmt.body)
                or any(self._visit_body(h.body) for h in stmt.handlers)
                or self._visit_body(stmt.orelse)
                or self._visit_body(stmt.finalbody)
            )
        return False

    def generic_visit(self, node: ast.AST) -> bool:
        """Don't recurse by default."""
        return False


class _ContinueSearcher(ast.NodeVisitor):
    """Visitor that finds continues owned by the enclosing loop.

    Key invariant: nested For/While loops are pruned. Python's continue starts
    the next iteration of the nearest enclosing loop, so an inner loop's
    continue does NOT count as a continue for the outer loop.
    """

    def _visit_body(self, body: list[ast.stmt]) -> bool:
        """Visit statements in order, stopping at first continue found."""
        for stmt in body:
            if self._visit_stmt(stmt):
                return True
        return False

    def _visit_stmt(self, stmt: ast.stmt) -> bool:
        """Visit a single statement, return True if continue found (not break)."""
        if isinstance(stmt, ast.Continue):
            return True
        if isinstance(stmt, ast.Break):
            return False
        if isinstance(stmt, (ast.Return, ast.Raise)):
            return False
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return False
        if isinstance(stmt, (ast.For, ast.While)):
            return False
        if isinstance(stmt, ast.If):
            return (
                self._visit_body(stmt.body)
                or self._visit_body(stmt.orelse)
            )
        if isinstance(stmt, ast.With):
            return self._visit_body(stmt.body)
        if isinstance(stmt, ast.Try):
            return (
                self._visit_body(stmt.body)
                or any(self._visit_body(h.body) for h in stmt.handlers)
                or self._visit_body(stmt.orelse)
                or self._visit_body(stmt.finalbody)
            )
        return False

    def generic_visit(self, node: ast.AST) -> bool:
        """Don't recurse by default."""
        return False


def _statement_has_break_for_enclosing_loop(stmt: ast.stmt) -> bool:
    """Does this statement contain a break owned by its enclosing loop?"""
    return _BreakSearcher()._visit_stmt(stmt)


def _loop_body_has_direct_break(loop: ast.For | ast.While) -> bool:
    """Does this loop's own body contain a break owned by this loop?"""
    return _BreakSearcher()._visit_body(loop.body)


def _contains_direct_break(stmt: ast.stmt) -> bool:
    """Does this statement contain a break (not continue) owned by its enclosing loop?"""
    return _statement_has_break_for_enclosing_loop(stmt)


def _contains_break(stmt: ast.stmt) -> bool:
    """Legacy wrapper."""
    return _statement_has_break_for_enclosing_loop(stmt)


def _statement_has_continue_for_enclosing_loop(stmt: ast.stmt) -> bool:
    """Does this statement contain a continue owned by its enclosing loop?"""
    return _ContinueSearcher()._visit_stmt(stmt)


def _loop_body_has_direct_continue(loop: ast.For | ast.While) -> bool:
    """Does this loop's own body contain a continue owned by this loop?"""
    return _ContinueSearcher()._visit_body(loop.body)


def _contains_direct_continue(stmt: ast.stmt) -> bool:
    """Does this statement contain a continue (not break) owned by its enclosing loop?"""
    return _statement_has_continue_for_enclosing_loop(stmt)


def _get_expr_provenance(
    expr: ast.expr,
    prov: dict[str, Provenance],
) -> Provenance:
    """Determine provenance of an expression at a specific point in execution."""
    from promotion_diagnosis_handoff_model import ProvenanceKind

    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name):
            base_name = expr.value.id
            if base_name in prov:
                base_prov = prov[base_name]
                if base_prov.attr_chain is not None:
                    return Provenance(
                        attr_chain=base_prov.attr_chain + (expr.attr,),
                        provenance_kind=base_prov.provenance_kind,
                    )
                elif base_prov.annotated_type:
                    if (
                        base_prov.provenance_kind == ProvenanceKind.PROMOTION_BATCH
                        and expr.attr == CANONICAL_PROMOTION_RESULT_FIELD
                    ):
                        return Provenance(
                            attr_chain=(CANONICAL_PROMOTION_RESULT_FIELD,),
                            provenance_kind=ProvenanceKind.INCIDENT_PROMOTION_RESULT,
                        )
                    return Provenance(
                        attr_chain=(expr.attr,),
                        provenance_kind=base_prov.provenance_kind,
                    )
            if expr.attr == CANONICAL_PROMOTION_RESULT_FIELD:
                return Provenance(attr_chain=(CANONICAL_PROMOTION_RESULT_FIELD,))
        elif isinstance(expr.value, ast.Attribute):
            inner_prov = _get_expr_provenance(expr.value, prov)
            if inner_prov.attr_chain is not None:
                new_kind = inner_prov.provenance_kind
                if (
                    isinstance(expr.value, ast.Attribute)
                    and expr.value.attr == CANONICAL_PROMOTION_RESULT_FIELD
                    and inner_prov.provenance_kind == ProvenanceKind.PROMOTION_BATCH
                ):
                    new_kind = ProvenanceKind.INCIDENT_PROMOTION_RESULT
                return Provenance(
                    attr_chain=inner_prov.attr_chain + (expr.attr,),
                    provenance_kind=new_kind,
                )
    elif isinstance(expr, ast.Name):
        if expr.id in prov:
            return prov[expr.id]
    elif isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name):
            if expr.func.id == "__return__":
                return prov.get("__return__", Provenance())
    return Provenance()


# Path termination types
TerminatedBy = Literal["break", "continue", "return", "raise", None]


def _track_statement(
    stmt: ast.stmt,
    prov: dict[str, Provenance],
    enclosing_return_type: str | None = None,
    is_classmethod: bool = False,
) -> TerminatedBy:
    """Track variable assignment for a single statement in execution order."""
    if isinstance(stmt, ast.Break):
        return "break"
    if isinstance(stmt, ast.Continue):
        return "continue"
    if isinstance(stmt, ast.Return):
        return "return"
    if isinstance(stmt, ast.Raise):
        return "raise"

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
        loop_assigned = _collect_assigned_names(stmt)
        pre_loop = {v: prov[v] for v in loop_assigned if v in prov}
        if isinstance(stmt.target, ast.Name):
            prov[stmt.target.id] = Provenance()

        for body_stmt in stmt.body:
            term = _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
            if term == "break":
                break
            elif term in ("return", "raise"):
                break

        for v in loop_assigned:
            if v in pre_loop:
                current_prov = prov.get(v, Provenance())
                if current_prov.provenance_kind != pre_loop[v].provenance_kind:
                    continue
                if current_prov.attr_chain != pre_loop[v].attr_chain:
                    continue
                prov[v] = pre_loop[v].merge(current_prov)

        has_break = _contains_direct_break(stmt)
        if stmt.orelse:
            if has_break:
                break_path_prov = dict(prov)
                for v in loop_assigned:
                    if v in pre_loop:
                        break_path_prov[v] = pre_loop[v]
                else_prov = dict(prov)
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, else_prov, enclosing_return_type, is_classmethod)
                all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                for var_name in all_vars:
                    if var_name in break_path_prov and var_name in else_prov:
                        prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                    elif var_name in break_path_prov:
                        prov[var_name] = break_path_prov[var_name]
                    else:
                        prov[var_name] = else_prov[var_name]
            else:
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)
    elif isinstance(stmt, ast.While):
        loop_assigned = _collect_assigned_names(stmt)
        pre_while_loop = {v: prov[v] for v in loop_assigned if v in prov}

        for body_stmt in stmt.body:
            term = _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
            if term == "break":
                break
            elif term in ("return", "raise"):
                break

        for v in loop_assigned:
            if v in pre_while_loop:
                current_prov = prov.get(v, Provenance())
                if current_prov.provenance_kind != pre_while_loop[v].provenance_kind:
                    continue
                if current_prov.attr_chain != pre_while_loop[v].attr_chain:
                    continue
                prov[v] = pre_while_loop[v].merge(current_prov)

        has_break = _contains_direct_break(stmt)
        if stmt.orelse:
            if has_break:
                break_path_prov = dict(prov)
                else_prov = dict(prov)
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, else_prov, enclosing_return_type, is_classmethod)
                all_vars = set(break_path_prov.keys()) | set(else_prov.keys())
                for var_name in all_vars:
                    if var_name in break_path_prov and var_name in else_prov:
                        prov[var_name] = break_path_prov[var_name].merge(else_prov[var_name])
                    elif var_name in break_path_prov:
                        prov[var_name] = break_path_prov[var_name]
                    else:
                        prov[var_name] = else_prov[var_name]
            else:
                for else_stmt in stmt.orelse:
                    _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)
    elif isinstance(stmt, ast.With):
        for item in stmt.items:
            if isinstance(item.optional_vars, ast.Name):
                prov[item.optional_vars.id] = Provenance()
        for body_stmt in stmt.body:
            term = _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)
            if term in ("break", "return", "raise"):
                break
    elif isinstance(stmt, ast.If):
        if_body_prov = dict(prov)
        for body_stmt in stmt.body:
            term = _track_statement(body_stmt, if_body_prov, enclosing_return_type, is_classmethod)
            if term in ("return", "raise"):
                break

        else_body_prov = dict(prov)
        for else_stmt in stmt.orelse:
            term = _track_statement(else_stmt, else_body_prov, enclosing_return_type, is_classmethod)
            if term in ("return", "raise"):
                break

        all_vars = set(if_body_prov.keys()) | set(else_body_prov.keys())
        for var_name in all_vars:
            if var_name in if_body_prov and var_name in else_body_prov:
                prov[var_name] = if_body_prov[var_name].merge(else_body_prov[var_name])
            elif var_name in if_body_prov:
                prov[var_name] = if_body_prov[var_name]
            else:
                prov[var_name] = else_body_prov[var_name]
    elif isinstance(stmt, ast.Try):
        pre_try_state = dict(prov)

        for body_stmt in stmt.body:
            _track_statement(body_stmt, prov, enclosing_return_type, is_classmethod)

        if stmt.orelse:
            for else_stmt in stmt.orelse:
                _track_statement(else_stmt, prov, enclosing_return_type, is_classmethod)

        handler_results: list[dict[str, Provenance]] = []
        for handler in stmt.handlers:
            handler_env = dict(pre_try_state)
            for handler_stmt in handler.body:
                _track_statement(handler_stmt, handler_env, enclosing_return_type, is_classmethod)
            handler_results.append(handler_env)

        all_vars = set(prov.keys())
        for handler_env in handler_results:
            all_vars.update(handler_env.keys())
        all_vars.update(pre_try_state.keys())

        merged: dict[str, Provenance] = {}
        for var_name in all_vars:
            merged[var_name] = Provenance()
            if var_name in prov:
                merged[var_name] = merged[var_name].merge(prov[var_name])
            for handler_env in handler_results:
                if var_name in handler_env:
                    merged[var_name] = merged[var_name].merge(handler_env[var_name])

        prov.update(merged)

        for final_stmt in stmt.finalbody:
            _track_statement(final_stmt, prov, enclosing_return_type, is_classmethod)

    return None

"""Provenance tracking for SEAM01 promotion-diagnosis handoff verifier.

This module provides the public API for provenance tracking by delegating
to focused submodules:

- promotion_diagnosis_handoff_model: Core types (Provenance, ClassInfo, etc.)
- promotion_diagnosis_handoff_symbols: Symbol identity and import resolution
- promotion_diagnosis_handoff_flow: Ordered traversal and control-flow analysis

Security guarantees:
- Provenance is tracked at each statement in execution order (P0: node-position aware)
- At control-flow joins, provenance is conservative: SAFE only when ALL paths are SAFE (P0)
- Attribute chains must terminate at the canonical promotion_result field (P0)
- Import identity is verified before accepting annotation names (P1)
- Return type annotations do not bless arbitrary local receivers (P0)
- Canonical method calls are restricted to RunPromotionAccumulator (P1)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_flow import (
    _collect_assigned_names,
    _get_expr_provenance,
    _track_statement,
    _track_to_target_line,
    build_provenance_at_node,
)
from promotion_diagnosis_handoff_flow_collect import (
    annotation_to_str,
    collect_classes,
    collect_functions,
    collect_imports,
)
from promotion_diagnosis_handoff_model import (
    CANONICAL_PROMOTION_RESULT_FIELD,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    Provenance,
    ProvenanceSafety,
)
from promotion_diagnosis_handoff_symbols import (
    CANONICAL_ACTIONABLE_OWNERS,
    CANONICAL_ALIAS_MODULES,
    CANONICAL_CANONICAL_OWNER,
    CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES,
    CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES,
    is_canonical_actionable_owner,
    is_canonical_canonical_owner,
    is_from_canonical_module,
    is_incident_promotion_result_type,
    is_run_promotion_accumulator_type,
    module_paths_equal,
    normalize_module_path,
    resolve_annotation_to_import,
)

if TYPE_CHECKING:
    pass

# Re-export for backward compatibility
__all__ = [
    # Model types
    "Provenance",
    "ClassInfo",
    "FunctionInfo",
    "ImportInfo",
    "ProvenanceSafety",
    "CANONICAL_PROMOTION_RESULT_FIELD",
    # Symbol functions
    "is_incident_promotion_result_type",
    "is_run_promotion_accumulator_type",
    "is_canonical_actionable_owner",
    "is_canonical_canonical_owner",
    "CANONICAL_ACTIONABLE_OWNERS",
    "CANONICAL_CANONICAL_OWNER",
    "resolve_annotation_to_import",
    "is_from_canonical_module",
    "CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES",
    "CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES",
    "CANONICAL_ALIAS_MODULES",
    "module_paths_equal",
    "normalize_module_path",
    # Flow functions
    "collect_classes",
    "collect_functions",
    "collect_imports",
    "build_provenance_at_node",
    "annotation_to_str",
    "_collect_assigned_names",
    "_get_expr_provenance",
    "_track_statement",
    "_track_to_target_line",
    # Receiver checking
    "get_receiver_name",
    "is_inside_class",
    "is_inside_class_by_name",
    "is_through_promotion_result_chain",
    "is_provenanced_actionable_access",
    "is_provenanced_canonical_call",
    "is_legitimate_actionable_access",
    "is_legitimate_canonical_call",
    "find_narrowest_enclosing_function",
]


def get_receiver_name(node: ast.AST) -> str:
    """Extract a readable name from an AST node representing a receiver."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        base = get_receiver_name(node.value)
        return f"{base}.{node.attr}"
    elif isinstance(node, ast.Subscript):
        base = get_receiver_name(node.value)
        return f"{base}[...]"
    else:
        return "<expr>"


def is_inside_class(node: ast.AST, class_name: str, classes: dict[str, ClassInfo]) -> bool:
    """Check if a node is inside a specific class definition based on line numbers."""
    if not hasattr(node, 'lineno') or node.lineno is None:
        return False
    node_line: int = node.lineno
    if class_name in classes:
        class_info = classes[class_name]
        return bool(class_info.line_start <= node_line <= class_info.line_end)
    return False


def is_inside_class_by_name(
    node: ast.AST,
    class_name: str,
    classes: dict[str, ClassInfo],
) -> bool:
    """Check if a node is inside a class by name.
    
    P1 FIX: This is a weak check that trusts any local class with a canonical-looking name.
    For self/cls access checks, use is_legitimate_actionable_access which verifies import identity.
    """
    return is_inside_class(node, class_name, classes)


def _is_class_from_canonical_module(
    class_name: str,
    imports: list[ImportInfo] | None,
    canonical_modules: frozenset[str],
) -> bool:
    """P1 FIX: Check if a class name was imported from a canonical module.
    
    Rejects locally defined classes with the same name.
    """
    if imports is None:
        return False
    for imp in imports:
        if imp.name == class_name or imp.alias == class_name:
            # Found import - verify it comes from canonical module
            if imp.module:
                for canonical in canonical_modules:
                    if module_paths_equal(imp.module, canonical):
                        return True
    return False


def is_through_promotion_result_chain(
    node: ast.Attribute,
    prov: dict[str, Provenance],
) -> bool:
    """Check if this is access through .promotion_result chain.
    
    P0 FIX: Now requires the chain to TERMINATE at .promotion_result, not just
    contain it anywhere in the chain. Descendants like .error_messages are NOT safe.
    
    Safe: batch.promotion_result.actionable_incident_ids
    Unsafe: batch.promotion_result.error_messages.actionable_incident_ids
    """
    # Build the full attribute chain from the node
    attr_parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        attr_parts.append(current.attr)
        current = current.value
    
    # Check if the immediate attribute is .promotion_result
    if node.attr == CANONICAL_PROMOTION_RESULT_FIELD:
        return True
    
    # Check if we're accessing from .promotion_result
    if isinstance(node.value, ast.Attribute):
        if node.value.attr == CANONICAL_PROMOTION_RESULT_FIELD:
            return True
        return False
    
    # Check if the value is a Name with safe attr_chain
    if isinstance(node.value, ast.Name):
        var_name = node.value.id
        if var_name in prov:
            var_prov = prov[var_name]
            if var_prov.is_safe_promotion_result_access():
                return True
    
    return False


def is_provenanced_actionable_access(
    receiver: ast.expr,
    prov: dict[str, Provenance],
    classes: dict[str, ClassInfo],
    imports: list[ImportInfo] | None = None,
    enclosing_func: FunctionInfo | None = None,
) -> bool:
    """P0 FIX: Check if accessing actionable_incident_ids is provenanced from promotion_result."""
    receiver_name = get_receiver_name(receiver)
    
    if receiver_name == "self":
        if is_inside_class_by_name(receiver, "IncidentPromotionResult", classes):
            return True
        if is_inside_class_by_name(receiver, "PromotionPropagationResult", classes):
            return True
        if is_inside_class_by_name(receiver, "IncidentPromotionResultDispatch", classes):
            return True
        return False
    
    if receiver_name == "cls":
        if enclosing_func and enclosing_func.is_classmethod:
            if is_inside_class_by_name(receiver, "IncidentPromotionResult", classes):
                return True
            if is_inside_class_by_name(receiver, "PromotionPropagationResult", classes):
                return True
            if is_inside_class_by_name(receiver, "IncidentPromotionResultDispatch", classes):
                return True
        return False
    
    if isinstance(receiver, ast.Name):
        var_prov = prov.get(receiver.id)
        if var_prov:
            if var_prov.is_safe_promotion_result_access():
                return True
            if is_incident_promotion_result_type(var_prov.annotated_type, imports):
                return True
    
    return False


def is_provenanced_canonical_call(
    receiver: ast.expr,
    prov: dict[str, Provenance],
    classes: dict[str, ClassInfo],
    imports: list[ImportInfo] | None = None,
) -> bool:
    """P0/P1 FIX: Check if calling canonical_incident_ids() is provenanced from RunPromotionAccumulator.
    
    P1 FIX: For self access, verify RunPromotionAccumulator was imported from canonical module.
    """
    receiver_name = get_receiver_name(receiver)
    
    if receiver_name == "self":
        # P1 FIX: Verify RunPromotionAccumulator was imported from canonical module
        if is_inside_class_by_name(receiver, CANONICAL_CANONICAL_OWNER, classes):
            if _is_class_from_canonical_module(CANONICAL_CANONICAL_OWNER, imports, CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES):
                return True
        return False
    
    if isinstance(receiver, ast.Name):
        var_prov = prov.get(receiver.id)
        if var_prov:
            if is_run_promotion_accumulator_type(var_prov.annotated_type, imports):
                return True
    
    return False


def is_legitimate_actionable_access(
    node: ast.Attribute,
    classes: dict[str, ClassInfo],
    prov: dict[str, Provenance],
    imports: list[ImportInfo] | None = None,
    enclosing_func: FunctionInfo | None = None,
) -> bool:
    """Check if accessing .actionable_incident_ids is legitimate based on provenance.
    
    P1 FIX: For self/cls access, we must verify that the class was imported from
    a canonical module, not just defined locally with the same name.
    """
    receiver_name = get_receiver_name(node.value)
    
    if receiver_name == "self":
        # P1 FIX: Verify class was imported from canonical module, not locally defined
        for class_name in CANONICAL_ACTIONABLE_OWNERS:
            if is_inside_class_by_name(node, class_name, classes):
                if _is_class_from_canonical_module(class_name, imports, CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES):
                    return True
        return False
    
    if receiver_name == "cls":
        if enclosing_func and enclosing_func.is_classmethod:
            # P1 FIX: Verify class was imported from canonical module
            for class_name in CANONICAL_ACTIONABLE_OWNERS:
                if is_inside_class_by_name(node, class_name, classes):
                    if _is_class_from_canonical_module(class_name, imports, CANONICAL_INCIDENT_PROMOTION_RESULT_MODULES):
                        return True
        return False
    
    if is_provenanced_actionable_access(node.value, prov, classes, imports, enclosing_func):
        return True
    
    if is_through_promotion_result_chain(node, prov):
        return True
    
    return False


def is_legitimate_canonical_call(
    node: ast.Call,
    classes: dict[str, ClassInfo],
    prov: dict[str, Provenance],
    imports: list[ImportInfo] | None = None,
) -> bool:
    """P1 FIX: Check if calling .canonical_incident_ids() is legitimate."""
    if not isinstance(node.func, ast.Attribute):
        return False
    
    receiver = node.func.value
    
    if is_provenanced_canonical_call(receiver, prov, classes, imports):
        return True
    
    return False


def find_narrowest_enclosing_function(
    node: ast.AST,
    functions: list[FunctionInfo],
) -> FunctionInfo | None:
    """Find the innermost (narrowest) function containing the node."""
    if not hasattr(node, 'lineno') or node.lineno is None:
        return None
    node_line = node.lineno
    
    enclosing = []
    for func in functions:
        if func.line_start <= node_line <= func.line_end:
            enclosing.append(func)
    
    if not enclosing:
        return None
    
    return min(enclosing, key=lambda f: f.line_end - f.line_start)

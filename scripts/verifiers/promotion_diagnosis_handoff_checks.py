"""Flow-aware checks for SEAM01 promotion-diagnosis handoff verifier.

Extracts the attribute/method access checking logic from the main verifier.
"""

from __future__ import annotations

import ast
from pathlib import Path

from promotion_diagnosis_handoff_flow import (
    build_provenance_at_node,
)
from promotion_diagnosis_handoff_flow_collect import (
    collect_imports,
)
from promotion_diagnosis_handoff_model import (
    CANONICAL_PROMOTION_RESULT_FIELD,
    ImportInfo,
    Provenance,
    ProvenanceKind,
)
from promotion_diagnosis_handoff_symbols import (
    CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES,
    is_from_canonical_module,
    resolve_annotation_to_import,
)

# Forbidden property and method names
FORBIDDEN_PROPERTY = "actionable_incident_ids"
FORBIDDEN_METHOD = "canonical_incident_ids"


def _find_containing_function(
    tree: ast.AST,
    node: ast.AST,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find the function that contains the given node.

    Uses iterative tree traversal to find parent nodes.
    """
    # Build parent mapping by traversing the FULL tree
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent

    # Walk up from node to find a function
    current = node
    while current in parent_map:
        parent = parent_map[current]
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent
        current = parent

    return None


def check_attribute_access(
    tree: ast.AST,
    node: ast.Attribute,
    path: Path,
    functions: list,  # type: ignore[type-arg]
) -> list[Violation]:
    """Check an .actionable_incident_ids attribute access.

    R12 FIX: Every receiver must be either structurally proven safe OR rejected.
    There is no "unhandled AST receiver means allowed" outcome.
    """
    violations: list[Violation] = []

    # Find which function contains this node
    containing_func = _find_containing_function(tree, node)
    if containing_func is None:
        # Module-level forbidden access is a contract violation (exit 1), not infrastructure failure
        return [
            Violation(
                file_path=str(path),
                line=node.lineno or 0,
                violation_type="forbidden_actionable_access",
                detail=(
                    f"Access to .{FORBIDDEN_PROPERTY} outside a function context. "
                    f"Must access via promotion_result chain."
                ),
            )
        ]

    # Find matching FunctionInfo
    func_info = None
    for f in functions:
        if f.line_start == containing_func.lineno and f.name == containing_func.name:
            func_info = f
            break
    if func_info is None:
        # R18 FIX: Can't verify without function metadata - infrastructure failure
        raise VerifierInfrastructureError(
            f"Cannot match function metadata for {path}:{node.lineno or 0}"
        )

    # Get the target line and column (before the attribute access)
    target_line = node.lineno
    target_col = node.col_offset

    # R21: Collect imports for type identity verification
    imports: list[ImportInfo] = []
    try:
        imports = collect_imports(tree)
    except Exception as exc:
        # Import collection failure is infrastructure error
        raise VerifierInfrastructureError(
            f"Import collection failed in {path}: {exc}"
        ) from exc

    # R17 FIX: Provenance analysis failure is infrastructure error (exit code 2)
    prov: dict[str, Provenance]
    try:
        prov = build_provenance_at_node(tree, func_info, target_line, target_col, imports)
    except Exception as exc:
        raise VerifierInfrastructureError(
            f"Provenance analysis failed for {path}:{target_line}: {exc}"
        ) from exc

    # R12 FIX: Check ALL receiver types, not just ast.Name
    # Every receiver must be either proven safe or rejected
    if isinstance(node.value, ast.Name):
        var_name = node.value.id
        # R5 FIX: self is ONLY safe if we're inside a PromotionBatch method
        # (which would be the ONLY class that has access to promotion_result)
        # and even then, we need to verify we're accessing through .promotion_result
        if var_name == "self":
            # self.actionable_incident_ids is ONLY allowed when the annotated type
            # of self is a PromotionBatch that has a promotion_result field
            # The provenance analysis should have set this up correctly
            if var_name in prov:
                p = prov[var_name]
                # Only allow if safe chain terminates at promotion_result
                if p.is_safe_promotion_result_access():
                    return violations
            # self without safe provenance chain - reject
            violations.append(Violation(
                file_path=str(path),
                line=target_line,
                violation_type="forbidden_actionable_access",
                detail=(
                    f"Access to self.{FORBIDDEN_PROPERTY} requires proven safe "
                    f"promotion_result chain. Must access via promotion_result chain."
                ),
            ))
        elif var_name in prov:
            p = prov[var_name]
            # R21 FIX: The ONLY safe chain is exactly ("promotion_result",)
            # Having PROMOTION_BATCH provenance alone does NOT allow direct access
            # The variable must have attr_chain == ("promotion_result",)
            if not p.is_safe_promotion_result_access():
                violations.append(Violation(
                    file_path=str(path),
                    line=target_line,
                    violation_type="forbidden_actionable_access",
                    detail=(
                        f"Access to {var_name}.{FORBIDDEN_PROPERTY} has untrusted provenance "
                        f"(attr_chain={p.attr_chain}, provenance_kind={p.provenance_kind}). "
                        f"Must access via promotion_result chain."
                    ),
                ))
        else:
            # Variable not in provenance - assume unsafe
            violations.append(Violation(
                file_path=str(path),
                line=target_line,
                violation_type="forbidden_actionable_access",
                detail=(
                    f"Access to {var_name}.{FORBIDDEN_PROPERTY} - variable has unknown provenance. "
                    f"Must access via promotion_result chain."
                ),
            ))
    elif isinstance(node.value, ast.Attribute):
        # Attribute chain like batch.promotion_result.error_messages
        # R12 FIX: Check if it's batch.promotion_result first
        if node.value.attr == "promotion_result":
            # This is something.promotion_result - check the base
            base = node.value.value
            # R5 FIX: Inside a PromotionBatch method, self.promotion_result is safe
            if isinstance(base, ast.Name) and base.id == "self":
                return violations
            if isinstance(base, ast.Name):
                base_name = base.id
                if base_name in prov:
                    base_prov = prov[base_name]
                    # R21 FIX: Split check into provenance kind AND attr chain
                    # 1. Check base has verified PROMOTION_BATCH provenance
                    has_promotion_batch_provenance = (
                        base_prov.provenance_kind == ProvenanceKind.PROMOTION_BATCH
                    )
                    # 2. Check the attribute being accessed is "promotion_result"
                    is_promotion_result_access = (
                        node.value.attr == CANONICAL_PROMOTION_RESULT_FIELD
                    )
                    # Both must be true for legitimate access
                    if has_promotion_batch_provenance and is_promotion_result_access:
                        # Base is batch.promotion_result - this is legitimate
                        return violations
                    else:
                        # Base is not proven safe - violation
                        if not has_promotion_batch_provenance:
                            detail_suffix = (
                                f"base has untrusted provenance "
                                f"(provenance_kind={base_prov.provenance_kind}). "
                                f"Must access via promotion_result chain."
                            )
                        else:
                            detail_suffix = (
                                f"base has untrusted provenance "
                                f"(attr_chain={base_prov.attr_chain}). "
                                f"Must access via promotion_result chain."
                            )
                        violations.append(Violation(
                            file_path=str(path),
                            line=target_line,
                            violation_type="forbidden_actionable_access",
                            detail=(
                                f"Access to {base_name}.promotion_result.{node.attr} - "
                                + detail_suffix
                            ),
                        ))
                else:
                    # Base variable not in provenance
                    violations.append(Violation(
                        file_path=str(path),
                        line=target_line,
                        violation_type="forbidden_actionable_access",
                        detail=(
                            f"Access to {base_name}.promotion_result.{node.attr} - "
                            f"base variable has unknown provenance. "
                            f"Must access via promotion_result chain."
                        ),
                    ))
            else:
                # Non-Name base for .promotion_result - reject unless proven
                violations.append(Violation(
                    file_path=str(path),
                    line=target_line,
                    violation_type="forbidden_actionable_access",
                    detail=(
                        f"Access to .{node.value.attr}.{node.attr} from non-canonical base. "
                        f"Must access via promotion_result chain."
                    ),
                ))
        else:
            # Other attribute chain - reject unless proven safe
            violations.append(Violation(
                file_path=str(path),
                line=target_line,
                violation_type="forbidden_actionable_access",
                detail=(
                    f"Access to .{node.value.attr}.{node.attr} - non-canonical attribute chain. "
                    f"Must access via promotion_result chain."
                ),
            ))
    else:
        # R12 FIX: Any other receiver type (Call, Subscript, etc.) - reject
        violations.append(Violation(
            file_path=str(path),
            line=target_line,
            violation_type="forbidden_actionable_access",
            detail=(
                f"Access to .{FORBIDDEN_PROPERTY} from unhandled receiver type "
                f"({type(node.value).__name__}). Must access via promotion_result chain."
            ),
        ))

    return violations


def check_method_call(
    tree: ast.AST,
    node: ast.Call,
    path: Path,
    functions: list,  # type: ignore[type-arg]
) -> list[Violation]:
    """Check a .canonical_incident_ids() method call."""
    violations: list[Violation] = []

    # Find which function contains this node
    containing_func = _find_containing_function(tree, node)
    if containing_func is None:
        # Module-level forbidden access is a contract violation (exit 1), not infrastructure failure
        return [
            Violation(
                file_path=str(path),
                line=node.lineno or 0,
                violation_type="forbidden_canonical_call",
                detail=(
                    f"Call to .{FORBIDDEN_METHOD}() outside a function context. "
                    f"Must use propagate_promotion_result_to_run() for handoff."
                ),
            )
        ]

    # Find matching FunctionInfo
    func_info = None
    for f in functions:
        if f.line_start == containing_func.lineno and f.name == containing_func.name:
            func_info = f
            break
    if func_info is None:
        # R18 FIX: Can't verify without function metadata - infrastructure failure
        raise VerifierInfrastructureError(
            f"Cannot match function metadata for {path}:{node.lineno or 0}"
        )

    # Get the target line and column (before the call)
    target_line = node.lineno
    target_col = node.col_offset

    # R17 FIX: Provenance analysis failure is infrastructure error (exit code 2)
    prov: dict[str, Provenance]
    try:
        prov = build_provenance_at_node(tree, func_info, target_line, target_col)
    except Exception as exc:
        raise VerifierInfrastructureError(
            f"Provenance analysis failed for {path}:{target_line}: {exc}"
        ) from exc

    # R13 FIX: canonical_incident_ids() must ONLY be allowed on RunPromotionAccumulator
    # with VERIFIED import identity (not just annotation string match)
    # Collect imports for identity verification
    imports: list[ImportInfo] = []
    try:
        imports = collect_imports(tree)
    except Exception as exc:
        # R17 FIX: Import collection failure is infrastructure error (exit code 2)
        raise VerifierInfrastructureError(
            f"Import collection failed in {path}: {exc}"
        ) from exc

    if isinstance(node.func, ast.Attribute):
        receiver = node.func.value
        if isinstance(receiver, ast.Name):
            # Simple variable: accumulator.canonical_incident_ids()
            var_name = receiver.id
            if var_name in prov:
                p = prov[var_name]
                if p.annotated_type and "RunPromotionAccumulator" in p.annotated_type:
                    # R13 FIX: Must verify import identity - resolve annotation to import
                    # and check it comes from canonical module
                    imp = resolve_annotation_to_import("RunPromotionAccumulator", imports)
                    if imp is None:
                        # No import found - could be local shadow, reject
                        violations.append(Violation(
                            file_path=str(path),
                            line=target_line,
                            violation_type="forbidden_canonical_call",
                            detail=(
                                f"Call to {var_name}.{FORBIDDEN_METHOD}() - 'RunPromotionAccumulator' "
                                f"annotation not imported from known canonical module. "
                                f"Must use propagate_promotion_result_to_run()."
                            ),
                        ))
                    elif not is_from_canonical_module(imp, CANONICAL_RUN_PROMOTION_ACCUMULATOR_MODULES):
                        # Wrong module - reject (prevents fake.k8s_diag_agent.collect.accumulator shadow)
                        violations.append(Violation(
                            file_path=str(path),
                            line=target_line,
                            violation_type="forbidden_canonical_call",
                            detail=(
                                f"Call to {var_name}.{FORBIDDEN_METHOD}() - 'RunPromotionAccumulator' "
                                f"imported from '{imp.module}' not canonical module. "
                                f"Must use propagate_promotion_result_to_run()."
                            ),
                        ))
                    else:
                        return violations  # Allowed - verified canonical import
                else:
                    violations.append(Violation(
                        file_path=str(path),
                        line=target_line,
                        violation_type="forbidden_canonical_call",
                        detail=(
                            f"Call to {var_name}.{FORBIDDEN_METHOD}() is only allowed on "
                            f"RunPromotionAccumulator receivers. "
                            f"Must use propagate_promotion_result_to_run()."
                        ),
                    ))
            else:
                violations.append(Violation(
                    file_path=str(path),
                    line=target_line,
                    violation_type="forbidden_canonical_call",
                    detail=(
                        f"Call to {var_name}.{FORBIDDEN_METHOD}() - variable has unknown provenance. "
                        f"Must use propagate_promotion_result_to_run()."
                    ),
                ))
        elif isinstance(receiver, ast.Attribute):
            # Attribute chain: batch.promotion_result.canonical_incident_ids()
            # This is ALWAYS forbidden - promotion_result is not RunPromotionAccumulator
            violations.append(Violation(
                file_path=str(path),
                line=target_line,
                violation_type="forbidden_canonical_call",
                detail=(
                    f"Call to .{receiver.attr}.{FORBIDDEN_METHOD}() is only allowed on "
                    f"RunPromotionAccumulator receivers. "
                    f"Must use propagate_promotion_result_to_run()."
                ),
            ))
        else:
            # Any other receiver type - reject
            violations.append(Violation(
                file_path=str(path),
                line=target_line,
                violation_type="forbidden_canonical_call",
                detail=(
                    f"Call to .{FORBIDDEN_METHOD}() from unhandled receiver type "
                    f"({type(receiver).__name__}). Must use propagate_promotion_result_to_run()."
                ),
            ))

    return violations


class VerifierInfrastructureError(RuntimeError):
    """Raised when verification infrastructure fails (parse errors, collection errors, etc).

    R16 FIX: Infrastructure failures must return exit code 2, not pass silently.
    """
    pass


class Violation:
    """Represents a contract violation found during scanning."""

    def __init__(
        self,
        file_path: str,
        line: int,
        violation_type: str,
        detail: str,
    ) -> None:
        self.file_path = file_path
        self.line = line
        self.violation_type = violation_type
        self.detail = detail

    def __str__(self) -> str:
        return (
            f"{self.file_path}:{self.line} "
            f"[{self.violation_type}] {self.detail}"
        )

#!/usr/bin/env python3
"""AST verifier for SEAM01 promotion-diagnosis handoff contract.

SEAM01 R3 contract enforcement:
- PromotionBatch MUST NOT expose actionable_incident_ids or canonical_incident_ids
- Production code MUST use propagate_promotion_result_to_run() for handoff
- No direct batch.actionable_incident_ids or batch.canonical_incident_ids access
- Semantic enforcement: checks actual receiver provenance, not just names

This verifier scans production code and rejects:
1. PromotionBatch.actionable_incident_ids property definition
2. PromotionBatch.canonical_incident_ids method definition
3. Direct access: batch.actionable_incident_ids (unless receiver provenanced from promotion_result)
4. Direct access: batch.canonical_incident_ids() (unless receiver is RunPromotionAccumulator)
5. getattr/hasattr patterns that bypass these checks

Exit codes:
  0 -- no violations found
  1 -- violations found (list printed)
  2 -- verification infrastructure failure (parse errors are fatal per R3)

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R3
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Ensure the verifiers directory is in the path for imports
_VERIFIERS_DIR = Path(__file__).parent
if str(_VERIFIERS_DIR) not in sys.path:
    sys.path.insert(0, str(_VERIFIERS_DIR))

from promotion_diagnosis_handoff_provenance import (
    build_provenance_at_node,
    collect_classes,
    collect_functions,
    collect_imports,
    find_narrowest_enclosing_function,
    get_receiver_name,
    is_legitimate_actionable_access,
    is_legitimate_canonical_call,
)

# Forbidden patterns
FORBIDDEN_PROPERTY = "actionable_incident_ids"
FORBIDDEN_METHOD = "canonical_incident_ids"


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


def _scan_module(path: Path) -> list[Violation]:
    """Scan a single Python file for SEAM01 contract violations.

    Legitimate patterns (NOT violations):
    - IncidentPromotionResult.self.actionable_incident_ids (class owns the property)
    - PromotionPropagationResult.self.actionable_incident_ids (result wrapper)
    - RunPromotionAccumulator.self.canonical_incident_ids() (class owns the method)
    - x.promotion_result.actionable_incident_ids (through the owned reference)
    - Variable annotated as IncidentPromotionResult accessing .actionable_incident_ids
    - Variable annotated as RunPromotionAccumulator calling .canonical_incident_ids()
    - x = batch.promotion_result; x.actionable_incident_ids (provenanced)
    """
    violations: list[Violation] = []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"FAIL: syntax error in {path}: {e}", file=sys.stderr)
        sys.exit(2)

    classes = collect_classes(tree)
    functions = collect_functions(tree)
    imports = collect_imports(tree)

    # Build final provenance maps for class body analysis (not needed for statement-order check)
    # Note: Statement-order provenance is computed per-node in the loop below

    # Check 1: PromotionBatch class with forbidden members
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromotionBatch":
            for item in node.body:
                # Check for actionable_incident_ids property (AnnAssign)
                if isinstance(item, ast.AnnAssign):
                    if (
                        hasattr(item, "target")
                        and hasattr(item.target, "id")
                        and item.target.id == FORBIDDEN_PROPERTY
                    ):
                        violations.append(Violation(
                            file_path=str(path),
                            line=item.lineno or 0,
                            violation_type="forbidden_property",
                            detail=(
                                f"PromotionBatch MUST NOT define '{FORBIDDEN_PROPERTY}' property. "
                                f"Access via batch.promotion_result.{FORBIDDEN_PROPERTY} instead."
                            ),
                        ))
                # Check for @property decorated actionable_incident_ids (FunctionDef)
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == FORBIDDEN_PROPERTY:
                        violations.append(Violation(
                            file_path=str(path),
                            line=item.lineno or 0,
                            violation_type="forbidden_property",
                            detail=(
                                f"PromotionBatch MUST NOT define '{FORBIDDEN_PROPERTY}' as a property. "
                                f"Access via batch.promotion_result.{FORBIDDEN_PROPERTY} instead."
                            ),
                        ))
                    if item.name == FORBIDDEN_METHOD:
                        violations.append(Violation(
                            file_path=str(path),
                            line=item.lineno or 0,
                            violation_type="forbidden_method",
                            detail=(
                                f"PromotionBatch MUST NOT define '{FORBIDDEN_METHOD}()' method. "
                                f"Use propagate_promotion_result_to_run() for handoff."
                            ),
                        ))

    # Check 2 & 3: Direct access patterns with provenance tracking
    # P0 FIX: Use build_provenance_at_node to get provenance AT THIS STATEMENT,
    # not the final state after the whole function. This prevents later assignments
    # from sanitizing earlier accesses.
    for node in ast.walk(tree):
        # Only check attribute accesses and calls that might be violations
        is_violation_candidate = False
        if isinstance(node, ast.Attribute) and node.attr == FORBIDDEN_PROPERTY:
            is_violation_candidate = True
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == FORBIDDEN_METHOD:
                is_violation_candidate = True

        if not is_violation_candidate:
            continue

        # Get enclosing function for provenance lookup
        enclosing_func = find_narrowest_enclosing_function(node, functions)

        # P0 FIX: Build provenance up to (but not including) this node's position
        # This ensures we get the state AT THIS STATEMENT, not after the whole function
        target_line = getattr(node, 'lineno', None)
        target_col = getattr(node, 'col_offset', 0) or 0
        if enclosing_func and target_line is not None:
            func_prov = build_provenance_at_node(
                tree,
                enclosing_func,
                target_line=target_line,
                target_col=target_col,
            )
        elif enclosing_func:
            func_prov = enclosing_func.local_vars if enclosing_func else {}
        else:
            func_prov = {}

        # Check: .actionable_incident_ids access
        if isinstance(node, ast.Attribute) and node.attr == FORBIDDEN_PROPERTY:
            if not is_legitimate_actionable_access(node, classes, func_prov, imports, enclosing_func):
                receiver = get_receiver_name(node.value)
                violations.append(Violation(
                    file_path=str(path),
                    line=node.lineno or 0,
                    violation_type="forbidden_actionable_access",
                    detail=(
                        f"Must not access {receiver}.{FORBIDDEN_PROPERTY} directly. "
                        f"Use propagate_promotion_result_to_run() for handoff."
                    ),
                ))

        # Check: .canonical_incident_ids() call
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == FORBIDDEN_METHOD:
                if not is_legitimate_canonical_call(node, classes, func_prov, imports):
                    receiver = get_receiver_name(node.func.value)
                    violations.append(Violation(
                        file_path=str(path),
                        line=node.lineno or 0,
                        violation_type="forbidden_canonical_call",
                        detail=(
                            f"Must not call {receiver}.{FORBIDDEN_METHOD}(). "
                            f"Use propagate_promotion_result_to_run() for handoff."
                        ),
                    ))

    # Check 4: getattr(..., "actionable_incident_ids")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) >= 2:
                    second_arg = node.args[1]
                    if isinstance(second_arg, ast.Constant):
                        if second_arg.value == FORBIDDEN_PROPERTY:
                            violations.append(Violation(
                                file_path=str(path),
                                line=node.lineno or 0,
                                violation_type="getattr_bypass",
                                detail=(
                                    f"getattr(..., '{FORBIDDEN_PROPERTY}') is not allowed. "
                                    f"Use propagate_promotion_result_to_run() for handoff."
                                ),
                            ))

    # Check 5: hasattr(..., "canonical_incident_ids")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "hasattr":
                if len(node.args) >= 2:
                    second_arg = node.args[1]
                    if isinstance(second_arg, ast.Constant):
                        if second_arg.value == FORBIDDEN_METHOD:
                            violations.append(Violation(
                                file_path=str(path),
                                line=node.lineno or 0,
                                violation_type="hasattr_bypass",
                                detail=(
                                    f"hasattr(..., '{FORBIDDEN_METHOD}') is not allowed. "
                                    f"Use propagate_promotion_result_to_run() for handoff."
                                ),
                            ))

    return violations


def scan_src(src_root: Path) -> list[Violation]:
    """Scan all Python files under src_root for violations."""
    violations: list[Violation] = []
    for py_file in src_root.rglob("*.py"):
        # Skip test files - they're allowed to test the contract
        if "test_" in py_file.name or "/tests/" in str(py_file):
            continue
        # Skip __pycache__
        if "__pycache__" in str(py_file):
            continue
        violations.extend(_scan_module(py_file))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-root",
        default="src",
        help="Root directory to scan (default: src)",
    )
    args = parser.parse_args(argv)

    src_root = Path(args.src_root)
    if not src_root.is_dir():
        print(f"FAIL: source root {src_root} is not a directory", file=sys.stderr)
        return 2

    violations = scan_src(src_root)

    if violations:
        print(f"FAIL: SEAM01 contract violations found ({len(violations)} total):")
        for v in violations:
            print(f"  {v}")
        return 1

    print("PASS: No SEAM01 promotion-diagnosis handoff contract violations")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

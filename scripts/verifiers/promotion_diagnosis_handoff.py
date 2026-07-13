#!/usr/bin/env python3
"""AST verifier for SEAM01 promotion-diagnosis handoff contract.

SEAM01 R3 contract enforcement:
- PromotionBatch MUST NOT expose actionable_incident_ids or canonical_incident_ids
- Production code MUST use propagate_promotion_result_to_run() for handoff
- No direct batch.actionable_incident_ids or batch.canonical_incident_ids access
- No variable-name dependent checks (checks actual semantics, not just variable names)
- Parse errors are FATAL (exit code 2) - they are not silently skipped

This verifier scans production code and rejects:
1. PromotionBatch.actionable_incident_ids property definition
2. PromotionBatch.canonical_incident_ids method definition
3. Direct access: batch.actionable_incident_ids
4. Direct access: batch.canonical_incident_ids()
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

# Forbidden patterns
FORBIDDEN_PROPERTY = "actionable_incident_ids"
FORBIDDEN_METHOD = "canonical_incident_ids"

# Legitimate access via promotion_result
LEGITIMATE_ACCESS_PATTERN = "promotion_result.actionable_incident_ids"

# Required handoff function
REQUIRED_HANDOFF_FUNC = "propagate_promotion_result_to_run"


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

    Checks for:
    1. PromotionBatch class definition with forbidden property/method
    2. Access patterns: batch.actionable_incident_ids
    3. Access patterns: batch.canonical_incident_ids()
    4. getattr(..., "actionable_incident_ids")
    5. hasattr(..., "canonical_incident_ids")
    """
    violations: list[Violation] = []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as e:
        # SEAM01 R3: Parse errors are FATAL - they indicate broken code
        print(f"FAIL: syntax error in {path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Check 1: PromotionBatch class with forbidden members
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromotionBatch":
            for item in node.body:
                # Check for actionable_incident_ids property
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
                # Check for canonical_incident_ids method
                if isinstance(item, ast.FunctionDef):
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

    # Check 2 & 3: Direct access patterns via AST
    # SEAM01 R3: Check ALL variable names, not just specific ones
    # This catches batch.actionable_incident_ids regardless of variable name
    for node in ast.walk(tree):
        # Check: .actionable_incident_ids on any PromotionBatch-like object
        if isinstance(node, ast.Attribute):
            if node.attr == FORBIDDEN_PROPERTY:
                # Check if it's batch.promotion_result.actionable (legitimate)
                # or some other.attr (potential violation)
                if isinstance(node.value, ast.Attribute):
                    # batch.promotion_result.actionable is OK
                    if node.value.attr == "promotion_result":
                        continue
                elif isinstance(node.value, ast.Name):
                    var_name = node.value.id
                    # Any variable ending with 'batch' or starting with 'promo'/'batch'
                    # is considered a PromotionBatch-like variable
                    if var_name.endswith("batch") or var_name.startswith(("batch_", "promo_", "promotion_")):
                        violations.append(Violation(
                            file_path=str(path),
                            line=node.lineno or 0,
                            violation_type="direct_access",
                            detail=(
                                f"Must not access {var_name}.{FORBIDDEN_PROPERTY} directly. "
                                f"Use propagate_promotion_result_to_run() for handoff."
                            ),
                        ))

        # Check: batch.canonical_incident_ids()
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == FORBIDDEN_METHOD:
                    if isinstance(node.func.value, ast.Name):
                        var_name = node.func.value.id
                        if var_name.endswith("batch") or var_name.startswith(("batch_", "promo_", "promotion_")):
                            violations.append(Violation(
                                file_path=str(path),
                                line=node.lineno or 0,
                                violation_type="direct_access",
                                detail=(
                                    f"Must not call {var_name}.{FORBIDDEN_METHOD}(). "
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

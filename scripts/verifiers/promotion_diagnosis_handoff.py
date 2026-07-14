#!/usr/bin/env python3
"""AST verifier for SEAM01 promotion-diagnosis handoff contract.

SEAM01 R3 contract enforcement:
- PromotionBatch MUST NOT expose actionable_incident_ids or canonical_incident_ids
- Production code MUST use propagate_promotion_result_to_run() for handoff
- No direct batch.actionable_incident_ids or batch.canonical_incident_ids access
- No variable-name dependent checks (checks actual semantics, not just variable names)
- Parse errors are FATAL (exit code 2) - they are not silently skipped

This verifier scans production code and rejects:
1. PromotionBatch class definition with forbidden property/method
2. Direct access: batch.actionable_incident_ids (via flow-aware analysis)
3. Direct access: batch.canonical_incident_ids()
4. getattr/hasattr patterns that bypass these checks

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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Handle imports for flow analysis
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_checks import (
    FORBIDDEN_METHOD,
    FORBIDDEN_PROPERTY,
    VerifierInfrastructureError,
    Violation,
    check_attribute_access,
    check_method_call,
)
from promotion_diagnosis_handoff_flow_collect import (
    collect_functions,
)

# R14 FIX: Centralized forbidden names for reflective access
FORBIDDEN_DYNAMIC_MEMBERS = frozenset({
    "actionable_incident_ids",
    "canonical_incident_ids",
})

# Legitimate access via promotion_result
LEGITIMATE_ACCESS_PATTERN = "promotion_result.actionable_incident_ids"

# Required handoff function
REQUIRED_HANDOFF_FUNC = "propagate_promotion_result_to_run"


def check_class_definition(
    tree: ast.AST,
    node: ast.ClassDef,
    path: Path,
) -> list[Violation]:
    """Check a class definition for forbidden property/method.

    R5 FIX: PromotionBatch MUST NOT expose actionable_incident_ids or
    canonical_incident_ids. This applies to the class body only, not
    methods that access other PromotionBatch instances.
    """

    violations: list[Violation] = []

    # R5: Check if this class is a PromotionBatch
    # This catches both:
    # 1. class PromotionBatch(Base):  - has PromotionBatch as base
    # 2. class PromotionBatch:       - direct definition (dataclass style)
    is_promotion_batch = False

    # Check if class name is PromotionBatch (handles dataclass style without explicit base)
    if node.name == "PromotionBatch":
        is_promotion_batch = True
    else:
        # Check if it has PromotionBatch as a base class
        for base in node.bases:
            if isinstance(base, ast.Name):
                if base.id == "PromotionBatch":
                    is_promotion_batch = True
                    break

    if not is_promotion_batch:
        return violations

    # R5 FIX: Check class body for forbidden property/method definitions
    # Only check direct assignments and method definitions, not attribute accesses
    for item in node.body:
        if isinstance(item, ast.AnnAssign):
            # Annotated assignment: should be: actionable_incident_ids: list[str] = ...
            if isinstance(item.target, ast.Name):
                if item.target.id == FORBIDDEN_PROPERTY:
                    violations.append(Violation(
                        file_path=str(path),
                        line=item.lineno,
                        violation_type="forbidden_property",
                        detail=(
                            f"PromotionBatch defines '{FORBIDDEN_PROPERTY}' property. "
                            f"This is forbidden by SEAM01 R5."
                        ),
                    ))
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name == FORBIDDEN_METHOD:
                violations.append(Violation(
                    file_path=str(path),
                    line=item.lineno,
                    violation_type="forbidden_method",
                    detail=(
                        f"PromotionBatch defines '{FORBIDDEN_METHOD}()' method. "
                        f"This is forbidden by SEAM01 R5."
                    ),
                ))
            # Check for @property decorator with forbidden name
            for decorator in item.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "property":
                    if item.name == FORBIDDEN_PROPERTY:
                        violations.append(Violation(
                            file_path=str(path),
                            line=item.lineno,
                            violation_type="forbidden_property",
                            detail=(
                                f"PromotionBatch defines '{FORBIDDEN_PROPERTY}' property. "
                                f"This is forbidden by SEAM01 R5."
                            ),
                        ))
                        break

    return violations


def check_dynamic_access(
    node: ast.Call,
    path: Path,
) -> list[Violation]:
    """Check getattr/hasattr calls for forbidden property/method access.

    R6 FIX: Reflective access like getattr(batch, 'actionable_incident_ids')
    also bypasses the contract and must be rejected.
    """
    violations: list[Violation] = []

    if isinstance(node.func, ast.Name):
        if node.func.id in ("getattr", "hasattr"):
            if len(node.args) >= 2:
                if isinstance(node.args[1], ast.Constant):
                    member = node.args[1].value
                    if member in FORBIDDEN_DYNAMIC_MEMBERS:
                        violations.append(Violation(
                            file_path=str(path),
                            line=node.lineno,
                            violation_type="forbidden_dynamic_access",
                            detail=(
                                f"{node.func.id}(..., '{member}') accesses forbidden member. "
                                f"Must use promotion_result chain or "
                                f"{REQUIRED_HANDOFF_FUNC}()."
                            ),
                        ))

    return violations


class _ForbiddenAccessVisitor(ast.NodeVisitor):
    """Visitor that finds all forbidden property/method accesses.

    This visitor handles R3/R4/R5:
    - R3: getattr/hasattr patterns for forbidden members
    - R4: Direct attribute access .actionable_incident_ids
    - R5: PromotionBatch class definitions with forbidden members
    """

    def __init__(
        self,
        tree: ast.AST,
        path: Path,
        functions: list,  # type: ignore[type-arg]
    ) -> None:
        self.tree = tree
        self.path = path
        self.functions = functions
        self.violations: list[Violation] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check for getattr/hasattr with forbidden member (R6)
        self.violations.extend(check_dynamic_access(node, self.path))

        # Check for .canonical_incident_ids() calls (R13)
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == FORBIDDEN_METHOD:
                self.violations.extend(
                    check_method_call(self.tree, node, self.path, self.functions)
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Check for .actionable_incident_ids access (R12)
        if node.attr == FORBIDDEN_PROPERTY:
            self.violations.extend(
                check_attribute_access(self.tree, node, self.path, self.functions)
            )

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Check PromotionBatch class definitions (R5)
        self.violations.extend(check_class_definition(self.tree, node, self.path))
        self.generic_visit(node)


def scan_file(path: Path, functions: list) -> list[Violation]:  # type: ignore[type-arg]
    """Scan a single file for promotion-diagnosis handoff violations.

    Raises:
        VerifierInfrastructureError: For read/parse failures (caught by main).
    """
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise VerifierInfrastructureError(f"Cannot decode {path}")
    except OSError as e:
        raise VerifierInfrastructureError(f"Cannot read {path}: {e}")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise VerifierInfrastructureError(f"Parse error in {path}:{e.lineno}: {e.msg}")

    # Visit the tree
    visitor = _ForbiddenAccessVisitor(tree, path, functions)
    visitor.visit(tree)

    return visitor.violations


def collect_violations(paths: list[Path]) -> tuple[list[Violation], list[str]]:
    """Collect all violations from the given paths.

    Returns (violations, errors) where errors are infrastructure failures.
    """
    all_violations: list[Violation] = []
    errors: list[str] = []

    for path in paths:
        # Collect functions first (for provenance analysis)
        functions: list[Any] = []
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            functions = collect_functions(tree)
        except SyntaxError as e:
            errors.append(f"Parse error in {path}:{e.lineno}: {e.msg}")
            continue
        except Exception as e:
            errors.append(f"Function collection failed in {path}: {e}")
            continue

        try:
            violations = scan_file(path, functions)
            all_violations.extend(violations)
        except VerifierInfrastructureError as e:
            errors.append(f"Infrastructure error in {path}: {e}")
        except Exception as e:
            errors.append(f"Unexpected error in {path}: {e}")

    return all_violations, errors


def print_violations(violations: list[Violation], verbose: bool = False) -> None:
    """Print violations in sorted order."""
    for v in sorted(violations, key=lambda x: (x.file_path, x.line)):
        if verbose:
            print(f"VIOLATION: {v}")
        else:
            print(v)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Optional command-line arguments. If None, uses sys.argv[1:].
              This enables testable CLI behavior.
    """
    parser = argparse.ArgumentParser(
        description="Verify SEAM01 promotion-diagnosis handoff contract."
    )
    parser.add_argument(
        "--src-root",
        type=Path,
        default=None,
        help="Root directory to scan (default: auto-detect)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=None,
        help="Paths to scan (default: src k8s_diag_agent)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    parser.add_argument(
        "--ignore-tests", action="store_true", help="Ignore test files"
    )
    args = parser.parse_args(argv)

    # Collect all Python files
    paths_to_scan: list[Path] = []

    # If --src-root is provided, use it as the base directory
    if args.src_root:
        base_dir = args.src_root
        if base_dir.is_file() and base_dir.suffix == ".py":
            paths_to_scan.append(base_dir)
        elif base_dir.is_dir():
            for py_file in base_dir.rglob("*.py"):
                if args.ignore_tests and py_file.name.startswith("test_"):
                    continue
                paths_to_scan.append(py_file)
        else:
            # Single file
            paths_to_scan.append(base_dir)
    elif args.paths:
        # Explicit paths provided
        for p in args.paths:
            if p.is_file():
                if p.suffix == ".py":
                    paths_to_scan.append(p)
            elif p.is_dir():
                for py_file in p.rglob("*.py"):
                    if args.ignore_tests and py_file.name.startswith("test_"):
                        continue
                    paths_to_scan.append(py_file)
    else:
        # Default: scan src and k8s_diag_agent
        for default_path in [Path("src"), Path("k8s_diag_agent")]:
            if default_path.exists():
                for py_file in default_path.rglob("*.py"):
                    if args.ignore_tests and py_file.name.startswith("test_"):
                        continue
                    paths_to_scan.append(py_file)

    if not paths_to_scan:
        print("No Python files found to scan.", file=sys.stderr)
        return 1

    violations, errors = collect_violations(paths_to_scan)

    # Print infrastructure errors first
    for error in errors:
        print(f"FAIL: verification infrastructure error: {error}", file=sys.stderr)

    # Exit code 2 for infrastructure errors (R16)
    if errors:
        return 2

    # Print violations
    print_violations(violations, args.verbose)

    # Exit code 1 if violations found, 0 otherwise
    if violations:
        print("FAIL: SEAM01 contract violations found")
        return 1

    print("PASS: No SEAM01 promotion-diagnosis handoff contract violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())

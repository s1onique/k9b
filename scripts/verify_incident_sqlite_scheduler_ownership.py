#!/usr/bin/env python3
"""Static verifier for incident SQLite scheduler ownership.

This script verifies that scheduler/health-loop modules do not directly import
or call SQLite store primitives, ensuring proper promotion via backend API.

Uses AST parsing to detect two-line patterns like:
    store = get_incident_store()
    store.promote_candidates(...)

Usage:
    python scripts/verify_incident_sqlite_scheduler_ownership.py

Exit codes:
    0: All checks passed
    1: Violations found

Integration:
    Gate target: make verify-incident-scheduler-backend-api

Test self-check:
    python scripts/verify_incident_sqlite_scheduler_ownership.py --self-test
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Patterns that indicate forbidden direct SQLite usage in scheduler promotion path
FORBIDDEN_PATTERNS = [
    # Direct SQLite store imports (scheduler-specific paths)
    (r"from.*incident_store_sqlite.*import", "Direct SQLiteIncidentStore import"),
    (r"import\s+sqlite3", "Direct sqlite3 module import"),
    (r"create_sqlite_store\s*\(", "Direct create_sqlite_store() call"),
    (r"SQLiteIncidentStore\s*\(", "Direct SQLiteIncidentStore instantiation"),
]

# Store variable names that are aliases for get_incident_store() result
STORE_VAR_ALIASES = [
    "store",
    "incident_store",
    "incident_store_instance",
    "store_instance",
]

# Forbidden method calls on store variables
FORBIDDEN_STORE_METHODS = [
    "promote_candidates",
    "promote_alert_signals",
    "promote",
]

# Paths that are allowed to use SQLite directly
ALLOWED_PATHS = [
    # Backend/internal handlers own SQLite
    r"src/k8s_diag_agent/ui/server_incident_internal",
    r"src/k8s_diag_agent/collect/incident_store_sqlite",
    # Provider role guards
    r"src/k8s_diag_agent/collect/incident_store_provider",
    # Tests are allowed
    r"tests/",
    # Incident promotion dispatcher is the correct path
    r"src/k8s_diag_agent/collect/incident_promotion_dispatch",
    # Candidate serialization
    r"src/k8s_diag_agent/collect/incident_candidate_serialization",
]

# Scheduler-specific paths that should NOT have direct SQLite access
SCHEDULER_PATHS = [
    r"src/k8s_diag_agent/health/",
    r"src/k8s_diag_agent/scheduler/",
]


class Violation(NamedTuple):
    """Represents a policy violation."""
    file_path: str
    line_number: int
    line_content: str
    violation_type: str


class StoreAssignmentTracker(ast.NodeVisitor):
    """AST visitor that tracks store variable assignments from get_incident_store()."""

    def __init__(self, filename: str):
        self.filename = filename
        self.store_vars: dict[str, int] = {}  # var_name -> line_number
        self.violations: list[Violation] = []
        self.current_line = 1

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track assignments like: store = get_incident_store()"""
        # Check if this is an assignment to a store-like variable
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                # Check if the value is a call to get_incident_store()
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        if node.value.func.id == "get_incident_store":
                            self.store_vars[var_name] = node.lineno
                    elif isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr == "get_incident_store":
                            self.store_vars[var_name] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for forbidden method calls on store variables."""
        # Check for chained calls like: get_incident_store().promote_candidates(...)
        if isinstance(node.func, ast.Attribute):
            # Check if called on a store variable
            if isinstance(node.func.value, ast.Call):
                if isinstance(node.func.value.func, ast.Name):
                    if node.func.value.func.id == "get_incident_store":
                        method_name = node.func.attr
                        if method_name in FORBIDDEN_STORE_METHODS:
                            self.violations.append(Violation(
                                file_path=self.filename,
                                line_number=node.lineno,
                                line_content=f"get_incident_store().{method_name}(...)",
                                violation_type="Direct store promotion via chained call",
                            ))
            # Check for method calls on known store variables
            elif isinstance(node.func.value, ast.Name):
                var_name = node.func.value.id
                if var_name in self.store_vars:
                    method_name = node.func.attr
                    if method_name in FORBIDDEN_STORE_METHODS:
                        self.violations.append(Violation(
                            file_path=self.filename,
                            line_number=node.lineno,
                            line_content=f"{var_name}.{method_name}(...)",
                            violation_type=f"Direct store.{method_name}() call after assignment",
                        ))
        self.generic_visit(node)


def is_allowed_path(file_path: str) -> bool:
    """Check if the file path is allowed to use SQLite directly."""
    for pattern in ALLOWED_PATHS:
        if re.search(pattern, file_path):
            return True
    return False


def is_scheduler_path(file_path: str) -> bool:
    """Check if the file is a scheduler/health-loop module."""
    for pattern in SCHEDULER_PATHS:
        if re.search(pattern, file_path):
            return True
    return False


def check_file_ast(file_path: Path) -> list[Violation]:
    """Check a single file using AST parsing for two-line store patterns.

    Args:
        file_path: Path to the Python file to check

    Returns:
        List of violations found
    """
    violations: list[Violation] = []

    if file_path.suffix != ".py":
        return violations

    if not is_scheduler_path(str(file_path)):
        return violations

    if is_allowed_path(str(file_path)):
        return violations

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)
        return violations

    # First pass: regex patterns
    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for pattern, violation_type in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                violations.append(Violation(
                    file_path=str(file_path),
                    line_number=line_num,
                    line_content=line.strip(),
                    violation_type=violation_type,
                ))

    # Second pass: AST for two-line store patterns
    try:
        tree = ast.parse(content, filename=str(file_path))
        tracker = StoreAssignmentTracker(str(file_path))
        tracker.visit(tree)
        violations.extend(tracker.violations)
    except SyntaxError as e:
        print(f"WARNING: Could not parse {file_path} for AST checks: {e}", file=sys.stderr)

    return violations


def check_directory(base_path: Path) -> list[Violation]:
    """Recursively check all Python files in a directory.

    Args:
        base_path: Base directory to check

    Returns:
        List of all violations found
    """
    violations = []

    for item in base_path.rglob("*.py"):
        # Skip test files and __pycache__
        if "__pycache__" in str(item):
            continue
        if item.name.startswith("test_") or item.name.endswith("_test.py"):
            continue

        violations.extend(check_file_ast(item))

    return violations


# ============================================================================
# Self-test fixtures for the verifier
# ============================================================================

SELF_TEST_CASES = [
    # Direct chained call should be rejected
    {
        "name": "direct chained call rejected",
        "code": """
from k8s_diag_agent.collect.incident_store import get_incident_store

def wrong_function():
    get_incident_store().promote_candidates(candidates, observed_at)
""",
        "expect_violation": True,
        "violation_type": "Direct store promotion via chained call",
    },
    # Two-line store assignment should be rejected
    {
        "name": "two-line store assignment rejected",
        "code": """
from k8s_diag_agent.collect.incident_store import get_incident_store

def wrong_function():
    store = get_incident_store()
    store.promote_candidates(candidates, observed_at)
""",
        "expect_violation": True,
        "violation_type": "Direct store.promote_candidates() call after assignment",
    },
    # Alias assignment should be rejected
    {
        "name": "alias assignment rejected",
        "code": """
from k8s_diag_agent.collect.incident_store import get_incident_store

def wrong_function():
    incident_store = get_incident_store()
    incident_store.promote_alert_signals(candidates, observed_at)
""",
        "expect_violation": True,
        "violation_type": "Direct store.promote_alert_signals() call after assignment",
    },
    # Dispatcher usage should be accepted
    {
        "name": "dispatcher usage accepted",
        "code": """
from k8s_diag_agent.collect.incident_promotion_dispatch import promote_candidates

def correct_function():
    promote_candidates(candidates, observed_at)
""",
        "expect_violation": False,
    },
    # Direct SQLite import should be rejected in scheduler path
    {
        "name": "direct sqlite import rejected in scheduler",
        "code": """
from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore

def some_function():
    pass
""",
        "expect_violation": True,
        "violation_type": "Direct SQLiteIncidentStore import",
    },
]


def run_self_test() -> bool:
    """Run self-test fixtures for the verifier."""
    print("Running self-test fixtures...")
    print("-" * 70)

    # Create a temporary directory structure that mimics scheduler path
    import tempfile
    temp_base = tempfile.mkdtemp()
    scheduler_dir = Path(temp_base) / "src" / "k8s_diag_agent" / "scheduler"
    scheduler_dir.mkdir(parents=True, exist_ok=True)

    all_passed = True
    for i, test_case in enumerate(SELF_TEST_CASES, 1):
        # Create a temporary file in the scheduler-like path
        temp_file = scheduler_dir / f"test_case_{i}.py"
        temp_file.write_text(str(test_case["code"]))

        try:
            violations = check_file_ast(temp_file)

            if test_case["expect_violation"]:
                if not violations:
                    print(f"FAIL [{i}]: {test_case['name']}")
                    print("  Expected violation but got none")
                    all_passed = False
                else:
                    found_type = violations[0].violation_type
                    expected_type = str(test_case.get("violation_type", ""))
                    if expected_type and expected_type not in found_type:
                        print(f"FAIL [{i}]: {test_case['name']}")
                        print(f"  Expected violation type '{test_case['violation_type']}'")
                        print(f"  Got: '{found_type}'")
                        all_passed = False
                    else:
                        print(f"PASS [{i}]: {test_case['name']}")
            else:
                if violations:
                    print(f"FAIL [{i}]: {test_case['name']}")
                    print("  Expected no violations but got:")
                    for v in violations:
                        print(f"    - {v.violation_type}")
                    all_passed = False
                else:
                    print(f"PASS [{i}]: {test_case['name']}")
        finally:
            temp_file.unlink()

    # Clean up temp directory
    import shutil
    shutil.rmtree(temp_base, ignore_errors=True)

    print("-" * 70)
    return all_passed


def main() -> int:
    """Main entry point."""
    # Check for self-test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        if run_self_test():
            print("\nAll self-test cases passed!")
            return 0
        else:
            print("\nSome self-test cases failed!")
            return 1

    # Determine project root
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent

    src_dir = project_root / "src"

    print("=" * 70)
    print("Incident SQLite Scheduler Ownership Verifier")
    print("=" * 70)
    print()
    print("Checking that scheduler/health-loop modules do not directly")
    print("access SQLite store primitives...")
    print()
    print("AST-based checks for:")
    print("  - Direct chained calls: get_incident_store().promote_candidates()")
    print("  - Two-line store assignment: store = get_incident_store(); store.promote_...")
    print("  - Alias assignments: incident_store = get_incident_store(); ...")
    print()

    violations = check_directory(src_dir)

    if not violations:
        print("PASSED: No policy violations found")
        print()
        print("Scheduler promotion paths correctly use incident_promotion_dispatch")
        print("instead of direct SQLite access.")
        return 0

    print(f"FAILED: Found {len(violations)} policy violation(s)")
    print()
    print("Violations:")
    print("-" * 70)

    for v in violations:
        print(f"  File: {v.file_path}")
        print(f"  Line: {v.line_number}")
        print(f"  Type: {v.violation_type}")
        print(f"  Code: {v.line_content}")
        print()

    print("-" * 70)
    print()
    print("Fix: Use incident_promotion_dispatch module for promotion instead")
    print("      of direct SQLite store access in scheduler/health-loop paths.")
    print()
    print("Correct usage:")
    print("  from k8s_diag_agent.collect.incident_promotion_dispatch import (")
    print("      promote_candidates,")
    print("      promote_alert_signals,")
    print("  )")

    return 1


if __name__ == "__main__":
    sys.exit(main())
